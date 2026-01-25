"""Tests for the error parser router."""

import pytest

from fixdoc.parsers.router import (
    detect_error_source,
    detect_and_parse,
    parse_single_error,
    summarize_errors,
    ErrorSource,
)
from fixdoc.parsers.terraform import TerraformError
from fixdoc.parsers.kubernetes import KubernetesError


class TestErrorSourceDetection:
    """Tests for automatic error source detection."""

    def test_detects_terraform_with_azure(self):
        text = """
        │ Error: creating Storage Account
        │   with azurerm_storage_account.main,
        │   on storage.tf line 1
        """
        assert detect_error_source(text) == ErrorSource.TERRAFORM

    def test_detects_terraform_with_aws(self):
        text = """
        │ Error: creating S3 Bucket
        │   with aws_s3_bucket.main,
        │   on storage.tf line 1
        """
        assert detect_error_source(text) == ErrorSource.TERRAFORM

    def test_detects_helm(self):
        text = """
        $ helm install myapp ./charts

        Error: INSTALLATION FAILED: cannot re-use a name
        """
        assert detect_error_source(text) == ErrorSource.HELM

    def test_detects_kubernetes_kubectl(self):
        text = """
        Error from server (Forbidden): error when creating "deployment.yaml"
        """
        assert detect_error_source(text) == ErrorSource.KUBERNETES

    def test_detects_kubernetes_pod_status(self):
        text = """
        NAME                    READY   STATUS             RESTARTS
        my-pod-abc123          0/1     ImagePullBackOff   0
        """
        assert detect_error_source(text) == ErrorSource.KUBERNETES

    def test_helm_takes_precedence_over_kubernetes(self):
        # Helm output contains Kubernetes-related content too
        text = """
        $ helm install myapp ./charts
        Error: INSTALLATION FAILED: pods "myapp" forbidden
        """
        # Should detect as Helm (which is a specialization of Kubernetes)
        assert detect_error_source(text) == ErrorSource.HELM

    def test_detects_unknown_for_random_text(self):
        text = "This is just some random text without any error patterns."
        assert detect_error_source(text) == ErrorSource.UNKNOWN


class TestUnifiedParsing:
    """Tests for the unified parsing function."""

    def test_parses_terraform_errors(self):
        text = """
        │ Error: creating Storage Account
        │ Code: "StorageAccountAlreadyTaken"
        │   with azurerm_storage_account.main,
        │   on storage.tf line 1
        """
        errors = detect_and_parse(text)

        assert len(errors) >= 1
        assert isinstance(errors[0], TerraformError)
        assert errors[0].error_type == "terraform"

    def test_parses_kubernetes_errors(self):
        text = """
        Error from server (Forbidden): error when creating "deployment.yaml":
        pods "api-server" is forbidden: exceeded quota
        """
        errors = detect_and_parse(text)

        assert len(errors) >= 1
        assert isinstance(errors[0], KubernetesError)
        assert errors[0].error_type == "kubernetes"

    def test_parses_helm_errors(self):
        text = """
        Error: INSTALLATION FAILED: cannot re-use a name that is still in use
        """
        errors = detect_and_parse(text)

        assert len(errors) >= 1
        # Helm errors are parsed as KubernetesError
        assert isinstance(errors[0], KubernetesError)

    def test_returns_empty_for_no_errors(self):
        text = "Everything is fine, no errors here."
        errors = detect_and_parse(text)
        assert errors == []

    def test_parses_multiple_terraform_errors(self):
        text = """
        │ Error: creating S3 Bucket (bucket1)
        │   with aws_s3_bucket.one,
        │   on main.tf line 1

        │ Error: creating S3 Bucket (bucket2)
        │   with aws_s3_bucket.two,
        │   on main.tf line 10
        """
        errors = detect_and_parse(text)

        assert len(errors) == 2


class TestSingleErrorParsing:
    """Tests for parsing single errors."""

    def test_returns_first_error(self):
        text = """
        │ Error: first error
        │   with aws_s3_bucket.one,
        │   on main.tf line 1

        │ Error: second error
        │   with aws_s3_bucket.two,
        │   on main.tf line 10
        """
        error = parse_single_error(text)

        assert error is not None
        assert "first" in error.error_message.lower() or error.resource_name == "one"

    def test_returns_none_for_no_errors(self):
        text = "No errors here."
        error = parse_single_error(text)
        assert error is None


class TestErrorSummarization:
    """Tests for error summarization."""

    def test_summarize_no_errors(self):
        summary = summarize_errors([])
        assert summary == "No errors found"

    def test_summarize_single_error(self):
        errors = detect_and_parse("""
        │ Error: test error
        │   with aws_s3_bucket.test,
        │   on main.tf line 1
        """)

        if errors:
            summary = summarize_errors(errors)
            assert "1" in summary
            assert "terraform" in summary.lower() or "error" in summary.lower()

    def test_summarize_multiple_terraform_errors(self):
        errors = detect_and_parse("""
        │ Error: first
        │   with aws_s3_bucket.one, on main.tf line 1

        │ Error: second
        │   with aws_s3_bucket.two, on main.tf line 10
        """)

        if errors and len(errors) > 1:
            summary = summarize_errors(errors)
            assert "2" in summary or "errors" in summary


class TestMixedErrors:
    """Tests for handling potentially mixed error sources."""

    def test_handles_ambiguous_content(self):
        # Content that could match multiple parsers
        text = """
        Error: something went wrong
        This is a general error message
        """
        # Should not crash
        errors = detect_and_parse(text)
        # Result depends on detection heuristics


class TestIntegration:
    """Integration tests with real-world-like scenarios."""

    def test_aws_terraform_full_workflow(self):
        text = """
        Terraform will perform the following actions:

          # aws_s3_bucket.logs will be created
          # aws_iam_role.lambda will be created

        Plan: 2 to add, 0 to change, 0 to destroy.

        aws_s3_bucket.logs: Creating...
        aws_iam_role.lambda: Creating...
        aws_iam_role.lambda: Creation complete after 2s [id=lambda-role]
        aws_s3_bucket.logs: Creating...

        │ Error: creating Amazon S3 (Simple Storage) Bucket (company-logs-bucket):
        │ api error BucketAlreadyExists: The requested bucket name is not available.
        │
        │   with aws_s3_bucket.logs,
        │   on storage.tf line 15, in resource "aws_s3_bucket" "logs":
        │   15: resource "aws_s3_bucket" "logs" {
        """
        source = detect_error_source(text)
        assert source == ErrorSource.TERRAFORM

        errors = detect_and_parse(text)
        assert len(errors) == 1
        assert errors[0].resource_type == "aws_s3_bucket"
        assert errors[0].error_code == "BucketAlreadyExists"

    def test_kubernetes_deployment_failure(self):
        text = """
        $ kubectl apply -f deployment.yaml
        deployment.apps/api-server created

        $ kubectl get pods -n production
        NAME                          READY   STATUS             RESTARTS   AGE
        api-server-5d8f9c7b6-m2n3o   0/1     ImagePullBackOff   0          30s

        $ kubectl describe pod api-server-5d8f9c7b6-m2n3o -n production
        Events:
          Type     Reason     Age   From               Message
          ----     ------     ----  ----               -------
          Warning  Failed     30s   kubelet            Failed to pull image "myregistry.io/api:v1"
          Warning  Failed     30s   kubelet            Error: ErrImagePull
        """
        source = detect_error_source(text)
        assert source == ErrorSource.KUBERNETES

        errors = detect_and_parse(text)
        assert len(errors) >= 1
        # Should detect ImagePullBackOff or ErrImagePull
        assert any(e.error_code in ("ImagePullBackOff", "ErrImagePull") for e in errors)

    def test_helm_deployment_with_k8s_error(self):
        text = """
        $ helm install myapp ./charts/myapp -n production

        Error: INSTALLATION FAILED: 1 error occurred:
            * Deployment.apps "myapp-api" is forbidden: exceeded quota

        NOTES:
        Thank you for installing myapp.
        """
        source = detect_error_source(text)
        assert source == ErrorSource.HELM

        errors = detect_and_parse(text)
        assert len(errors) >= 1
        # Should extract the quota error
        assert any("quota" in e.error_message.lower() for e in errors)
