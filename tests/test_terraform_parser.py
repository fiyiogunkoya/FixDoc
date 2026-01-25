"""Comprehensive tests for the Terraform error parser."""

import pytest
from pathlib import Path

from fixdoc.parsers.terraform import TerraformParser, TerraformError
from fixdoc.parsers.base import CloudProvider, ErrorSeverity


# Get the fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "terraform"


class TestTerraformParserDetection:
    """Tests for error source detection."""

    def setup_method(self):
        self.parser = TerraformParser()

    def test_detects_terraform_output_with_error(self):
        text = """
        │ Error: creating Storage Account
        │   with azurerm_storage_account.main
        """
        assert self.parser.can_parse(text) is True

    def test_detects_terraform_with_aws_resource(self):
        text = "aws_s3_bucket.data: Creating..."
        assert self.parser.can_parse(text) is True

    def test_detects_terraform_with_azure_resource(self):
        text = "azurerm_storage_account.main: Creating..."
        assert self.parser.can_parse(text) is True

    def test_detects_terraform_with_gcp_resource(self):
        text = "google_compute_instance.main: Creating..."
        assert self.parser.can_parse(text) is True

    def test_detects_terraform_with_plan_output(self):
        text = "Plan: 5 to add, 2 to change, 1 to destroy."
        assert self.parser.can_parse(text) is True

    def test_does_not_detect_random_text(self):
        text = "Hello, this is just random text without terraform content."
        assert self.parser.can_parse(text) is False

    def test_does_not_detect_kubectl_output(self):
        text = "kubectl apply -f deployment.yaml\nError from server (Forbidden)"
        assert self.parser.can_parse(text) is False


class TestAWSErrorParsing:
    """Tests for AWS-specific error parsing."""

    def setup_method(self):
        self.parser = TerraformParser()

    def test_parse_s3_bucket_already_exists(self):
        text = """
        aws_s3_bucket.data: Creating...

        │ Error: creating Amazon S3 (Simple Storage) Bucket (my-company-data-bucket):
        │ operation error S3: CreateBucket, https response error StatusCode: 409,
        │ RequestID: ABC123DEF456, HostID: xyz789,
        │ api error BucketAlreadyExists: The requested bucket name is not available.
        │ The bucket namespace is shared by all users of the system.
        │
        │   with aws_s3_bucket.data,
        │   on storage/main.tf line 1, in resource "aws_s3_bucket" "data":
        │    1: resource "aws_s3_bucket" "data" {
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AWS
        assert error.resource_type == "aws_s3_bucket"
        assert error.resource_name == "data"
        assert error.error_code == "BucketAlreadyExists"
        assert error.file == "storage/main.tf"
        assert error.line == 1
        assert "BucketAlreadyExists" in error.short_error()

    def test_parse_iam_access_denied(self):
        text = """
        │ Error: creating Lambda Function (data-processor): AccessDeniedException:
        │ User: arn:aws:iam::123456789012:user/terraform-ci is not authorized to perform:
        │ iam:PassRole on resource: arn:aws:iam::123456789012:role/lambda-processor-role
        │
        │   with aws_lambda_function.processor,
        │   on modules/lambda/main.tf line 45, in resource "aws_lambda_function" "processor":
        │   45: resource "aws_lambda_function" "processor" {
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AWS
        assert error.resource_type == "aws_lambda_function"
        # Accept either AccessDenied or AccessDeniedException
        assert error.error_code in ("AccessDenied", "AccessDeniedException")
        assert "iam:PassRole" in error.error_message or "PassRole" in error.raw_output

    def test_parse_ec2_capacity_error(self):
        text = """
        │ Error: creating EC2 Instance: InsufficientInstanceCapacity:
        │ We currently do not have sufficient p4d.24xlarge capacity in the
        │ Availability Zone you requested (us-east-1a).
        │
        │   with aws_instance.ml_training,
        │   on compute/ml.tf line 1, in resource "aws_instance" "ml_training":
        │    1: resource "aws_instance" "ml_training" {
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AWS
        assert error.resource_type == "aws_instance"
        assert "InsufficientInstanceCapacity" in error.error_code or "capacity" in error.error_message.lower()

    def test_generates_aws_suggestions(self):
        text = """
        aws_s3_bucket.test: Creating...

        │ Error: creating Amazon S3 Bucket (my-bucket):
        │ api error BucketAlreadyExists: The requested bucket name is not available.
        │
        │   with aws_s3_bucket.test,
        │   on main.tf line 1, in resource "aws_s3_bucket" "test":
        │    1: resource "aws_s3_bucket" "test" {
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AWS
        # Should have suggestions for BucketAlreadyExists
        assert len(error.suggestions) > 0
        assert any("unique" in s.lower() or "different name" in s.lower() for s in error.suggestions)


class TestAzureErrorParsing:
    """Tests for Azure-specific error parsing."""

    def setup_method(self):
        self.parser = TerraformParser()

    def test_parse_storage_account_exists(self):
        text = """
        │ Error: creating Storage Account (Subscription: "12345678-1234-1234-1234-123456789abc"
        │ Resource Group Name: "rg-data-prod"
        │ Storage Account Name: "stcompanydata"):
        │
        │ Code: "StorageAccountAlreadyTaken"
        │ Message: "The storage account named stcompanydata is already taken."
        │
        │   with azurerm_storage_account.main,
        │   on storage/main.tf line 1, in resource "azurerm_storage_account" "main":
        │    1: resource "azurerm_storage_account" "main" {
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AZURE
        assert error.resource_type == "azurerm_storage_account"
        assert error.error_code == "StorageAccountAlreadyTaken"

    def test_parse_vm_sku_not_available(self):
        text = """
        │ Error: creating Linux Virtual Machine
        │
        │ Code: "SkuNotAvailable"
        │ Message: "The requested VM size Standard_NC24ads_A100_v4 is not available"
        │
        │   with azurerm_linux_virtual_machine.ml,
        │   on compute/ml.tf line 15
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AZURE
        assert error.error_code == "SkuNotAvailable"

    def test_parse_keyvault_soft_delete_conflict(self):
        text = """
        │ Error: creating Key Vault
        │
        │ Code: "ConflictError"
        │ Message: "A vault with the same name already exists in deleted state."
        │
        │   with azurerm_key_vault.main,
        │   on security/keyvault.tf line 1
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        error = errors[0]
        assert error.cloud_provider == CloudProvider.AZURE
        assert error.error_code == "ConflictError"


class TestMultipleErrors:
    """Tests for parsing multiple errors from single output."""

    def setup_method(self):
        self.parser = TerraformParser()

    def test_parse_multiple_errors(self):
        text = """
        │ Error: creating ELBv2 Application Load Balancer (prod-api-alb):
        │ InvalidSubnet: VPC vpc-0abc123def456789a has no internet gateway
        │
        │   with module.app.aws_lb.main,
        │   on modules/app/alb.tf line 1

        │ Error: creating RDS DB Instance (prod-postgres): InvalidParameterValue:
        │ IAM Database Authentication is not supported
        │
        │   with module.database.aws_db_instance.main,
        │   on modules/database/main.tf line 15
        """
        errors = self.parser.parse(text)

        assert len(errors) == 2
        assert errors[0].resource_type == "aws_lb"
        assert errors[1].resource_type == "aws_db_instance"

    def test_deduplicates_errors_by_address(self):
        text = """
        │ Error: creating S3 Bucket (test-bucket): BucketAlreadyExists
        │   with aws_s3_bucket.test,
        │   on main.tf line 1

        │ Error: creating S3 Bucket (test-bucket): BucketAlreadyExists
        │   with aws_s3_bucket.test,
        │   on main.tf line 1
        """
        errors = self.parser.parse(text)

        # Should deduplicate
        assert len(errors) == 1


class TestTagGeneration:
    """Tests for automatic tag generation."""

    def setup_method(self):
        self.parser = TerraformParser()

    def test_generates_resource_type_tag(self):
        text = """
        aws_s3_bucket.test: Creating...

        │ Error: test error
        │   with aws_s3_bucket.test,
        │   on main.tf line 1, in resource "aws_s3_bucket" "test":
        """
        errors = self.parser.parse(text)

        assert len(errors) == 1
        tags = errors[0].generate_tags()
        assert "aws_s3_bucket" in tags

    def test_generates_cloud_provider_tag(self):
        text = """
        aws_s3_bucket.test: Creating...

        │ Error: test error
        │   with aws_s3_bucket.test,
        │   on main.tf line 1, in resource "aws_s3_bucket" "test":
        """
        errors = self.parser.parse(text)
        tags = errors[0].generate_tags()
        assert "aws" in tags

    def test_generates_error_code_tag(self):
        text = """
        │ Error: BucketAlreadyExists: test
        │   with aws_s3_bucket.test,
        │   on main.tf line 1
        """
        errors = self.parser.parse(text)
        tags = errors[0].generate_tags()
        assert "BucketAlreadyExists" in tags


class TestFixtureFiles:
    """Tests using the comprehensive fixture files."""

    def setup_method(self):
        self.parser = TerraformParser()

    @pytest.mark.skipif(not FIXTURES_DIR.exists(), reason="Fixtures not found")
    def test_parse_aws_iam_permission_errors(self):
        fixture_file = FIXTURES_DIR / "aws" / "iam_permission_errors.txt"
        if not fixture_file.exists():
            pytest.skip("Fixture file not found")

        content = fixture_file.read_text()
        # Split by fixture separator
        test_cases = content.split("---FIXTURE_SEPARATOR---")

        for i, case in enumerate(test_cases):
            if "Error:" not in case:
                continue

            errors = self.parser.parse(case)
            assert len(errors) >= 1, f"Failed to parse test case {i + 1}"
            assert errors[0].cloud_provider == CloudProvider.AWS

    @pytest.mark.skipif(not FIXTURES_DIR.exists(), reason="Fixtures not found")
    def test_parse_aws_s3_errors(self):
        fixture_file = FIXTURES_DIR / "aws" / "s3_errors.txt"
        if not fixture_file.exists():
            pytest.skip("Fixture file not found")

        content = fixture_file.read_text()
        test_cases = content.split("---FIXTURE_SEPARATOR---")

        for i, case in enumerate(test_cases):
            if "Error:" not in case:
                continue

            errors = self.parser.parse(case)
            assert len(errors) >= 1, f"Failed to parse S3 test case {i + 1}"
            # Should identify as AWS
            assert errors[0].cloud_provider == CloudProvider.AWS

    @pytest.mark.skipif(not FIXTURES_DIR.exists(), reason="Fixtures not found")
    def test_parse_aws_multi_error_complex(self):
        fixture_file = FIXTURES_DIR / "aws" / "multi_error_complex.txt"
        if not fixture_file.exists():
            pytest.skip("Fixture file not found")

        content = fixture_file.read_text()
        test_cases = content.split("---FIXTURE_SEPARATOR---")

        # Test case 1 should have 5 errors
        if len(test_cases) >= 1:
            errors = self.parser.parse(test_cases[0])
            # The first test case has multiple errors
            assert len(errors) >= 3, "Should parse multiple errors from complex output"

    @pytest.mark.skipif(not FIXTURES_DIR.exists(), reason="Fixtures not found")
    def test_parse_azure_comprehensive_errors(self):
        fixture_file = FIXTURES_DIR / "azure" / "comprehensive_errors.txt"
        if not fixture_file.exists():
            pytest.skip("Fixture file not found")

        content = fixture_file.read_text()
        test_cases = content.split("---FIXTURE_SEPARATOR---")

        for i, case in enumerate(test_cases):
            if "Error:" not in case:
                continue

            errors = self.parser.parse(case)
            assert len(errors) >= 1, f"Failed to parse Azure test case {i + 1}"
            assert errors[0].cloud_provider == CloudProvider.AZURE


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def setup_method(self):
        self.parser = TerraformParser()

    def test_handles_empty_input(self):
        errors = self.parser.parse("")
        assert errors == []

    def test_handles_no_errors_in_output(self):
        text = """
        Terraform will perform the following actions:

        Plan: 5 to add, 0 to change, 0 to destroy.

        Apply complete!
        """
        errors = self.parser.parse(text)
        assert errors == []

    def test_handles_malformed_resource_address(self):
        text = """
        │ Error: Something went wrong
        │ No resource address provided
        """
        errors = self.parser.parse(text)
        # Should still parse but with unknown resource
        assert len(errors) == 1
        assert errors[0].resource_type == "unknown"

    def test_handles_unicode_in_error(self):
        text = """
        │ Error: creating resource "名前"
        │   with aws_s3_bucket.test,
        │   on main.tf line 1
        """
        errors = self.parser.parse(text)
        assert len(errors) == 1

    def test_truncates_very_long_error_message(self):
        long_message = "A" * 1000
        text = f"""
        │ Error: {long_message}
        │   with aws_s3_bucket.test,
        │   on main.tf line 1
        """
        errors = self.parser.parse(text)
        assert len(errors) == 1
        assert len(errors[0].error_message) <= 500
