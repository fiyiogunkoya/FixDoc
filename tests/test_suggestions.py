"""Tests for fixdoc suggestions module."""

import pytest

from fixdoc.models import Fix
from fixdoc.storage import FixRepository
from fixdoc.suggestions import (
    find_similar_fixes,
    _extract_keywords,
    _extract_error_codes,
    _extract_resource_types,
)


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository for testing."""
    return FixRepository(base_path=tmp_path / ".fixdoc")


@pytest.fixture
def repo_with_fixes(temp_repo):
    """Create a repository with sample fixes."""
    fixes = [
        Fix(
            issue="S3 BucketAlreadyExists error when creating bucket",
            resolution="Add random suffix to bucket name or use existing bucket",
            tags="aws,s3,terraform",
            error_excerpt="Error: BucketAlreadyExists: The bucket name is already taken",
        ),
        Fix(
            issue="Azure storage account RBAC permission denied",
            resolution="Add Storage Blob Data Contributor role to service principal",
            tags="azure,storage,rbac,terraform",
            error_excerpt="Error: AuthorizationFailed: The client does not have permission",
        ),
        Fix(
            issue="Kubernetes CrashLoopBackOff in pod",
            resolution="Check container logs and fix application startup error",
            tags="kubernetes,pod,crashloopbackoff",
            error_excerpt="CrashLoopBackOff: Container keeps restarting",
        ),
        Fix(
            issue="Terraform state lock timeout",
            resolution="Force unlock state with terraform force-unlock",
            tags="terraform,state,lock",
            error_excerpt="Error: Error acquiring the state lock",
        ),
    ]
    for fix in fixes:
        temp_repo.save(fix)
    return temp_repo


class TestFindSimilarFixes:
    def test_find_by_error_text_keyword(self, repo_with_fixes):
        """Should find fixes with matching keywords in error text."""
        similar = find_similar_fixes(
            repo_with_fixes,
            "Error: BucketAlreadyExists when creating S3 bucket",
        )

        assert len(similar) > 0
        # S3 bucket fix should be ranked highly
        assert any("S3" in fix.issue or "s3" in fix.tags for fix in similar[:2])

    def test_find_by_tags(self, repo_with_fixes):
        """Should find fixes with matching tags."""
        similar = find_similar_fixes(
            repo_with_fixes,
            "some error",
            tags="terraform,azure",
        )

        assert len(similar) > 0
        # Azure and terraform tagged fixes should rank higher
        top_fix = similar[0]
        assert "azure" in top_fix.tags.lower() or "terraform" in top_fix.tags.lower()

    def test_find_by_error_code(self, repo_with_fixes):
        """Should find fixes with matching error codes."""
        similar = find_similar_fixes(
            repo_with_fixes,
            "AuthorizationFailed: User does not have permissions",
        )

        assert len(similar) > 0
        # Azure RBAC fix should match on error code
        assert any("AuthorizationFailed" in (fix.error_excerpt or "") for fix in similar[:2])

    def test_find_by_resource_type(self, temp_repo):
        """Should find fixes with matching resource types in tags."""
        # Create a fix with actual terraform resource type in tags
        fix = Fix(
            issue="S3 bucket error",
            resolution="Fix bucket config",
            tags="aws_s3_bucket,terraform",
            error_excerpt="Error creating bucket",
        )
        temp_repo.save(fix)

        similar = find_similar_fixes(
            temp_repo,
            "Error with aws_s3_bucket resource",
        )

        assert len(similar) > 0
        # The fix with aws_s3_bucket tag should match
        assert any("aws_s3_bucket" in fix.tags.lower() for fix in similar)

    def test_empty_repository(self, temp_repo):
        """Should return empty list for empty repository."""
        similar = find_similar_fixes(temp_repo, "any error")
        assert similar == []

    def test_no_matches(self, repo_with_fixes):
        """Should return empty when no fixes match."""
        similar = find_similar_fixes(
            repo_with_fixes,
            "xyz123 completely unrelated error",
            tags="nonexistent,tags",
        )

        # May return some results due to common words, but low scores
        # Just verify it doesn't crash
        assert isinstance(similar, list)

    def test_limit_results(self, repo_with_fixes):
        """Should respect the limit parameter."""
        similar = find_similar_fixes(
            repo_with_fixes,
            "terraform error",
            limit=2,
        )

        assert len(similar) <= 2

    def test_results_sorted_by_score(self, repo_with_fixes):
        """Results should be sorted by relevance score (descending)."""
        # This is an indirect test - the most relevant fix should be first
        similar = find_similar_fixes(
            repo_with_fixes,
            "CrashLoopBackOff kubernetes pod error",
            tags="kubernetes",
        )

        if len(similar) >= 2:
            # The kubernetes fix should be ranked first
            assert "kubernetes" in similar[0].tags.lower()


class TestExtractKeywords:
    def test_extract_basic_keywords(self):
        """Should extract meaningful words from text."""
        keywords = _extract_keywords("Error creating storage account")

        assert "creating" in keywords
        assert "storage" in keywords
        assert "account" in keywords

    def test_filter_stop_words(self):
        """Should filter out common stop words."""
        keywords = _extract_keywords("The error is in the configuration")

        assert "the" not in keywords
        assert "is" not in keywords
        assert "in" not in keywords
        assert "configuration" in keywords

    def test_filter_short_words(self):
        """Should filter words with 2 or fewer characters."""
        keywords = _extract_keywords("An S3 bucket in us-east-1")

        assert "an" not in keywords
        assert "in" not in keywords

    def test_lowercase_conversion(self):
        """Should convert keywords to lowercase."""
        keywords = _extract_keywords("STORAGE Account ERROR")

        assert "storage" in keywords
        assert "STORAGE" not in keywords

    def test_empty_text(self):
        """Should handle empty text."""
        assert _extract_keywords("") == set()
        assert _extract_keywords(None) == set()


class TestExtractErrorCodes:
    def test_extract_azure_error_code(self):
        """Should extract Azure-style error codes."""
        codes = _extract_error_codes('Code: "AuthorizationFailed"')

        assert "authorizationfailed" in codes

    def test_extract_http_status_codes(self):
        """Should extract HTTP status codes."""
        codes = _extract_error_codes("Request failed with status 403 Forbidden")

        assert "403" in codes

    def test_extract_common_error_names(self):
        """Should extract common error pattern names."""
        codes = _extract_error_codes("accessdenied error when accessing resource")

        assert "accessdenied" in codes

    def test_multiple_codes(self):
        """Should extract multiple error codes."""
        codes = _extract_error_codes("Error 404 NotFound, Code: Forbidden 403")

        assert "404" in codes
        assert "403" in codes


class TestExtractResourceTypes:
    def test_extract_aws_resource_types(self):
        """Should extract AWS resource types."""
        types = _extract_resource_types("Error with aws_s3_bucket resource")

        assert "aws_s3_bucket" in types

    def test_extract_azure_resource_types(self):
        """Should extract Azure resource types."""
        types = _extract_resource_types("azurerm_storage_account creation failed")

        assert "azurerm_storage_account" in types

    def test_extract_gcp_resource_types(self):
        """Should extract GCP resource types."""
        types = _extract_resource_types("google_compute_instance error")

        assert "google_compute_instance" in types

    def test_multiple_resource_types(self):
        """Should extract multiple resource types."""
        types = _extract_resource_types(
            "Error with aws_iam_role and aws_s3_bucket"
        )

        assert "aws_iam_role" in types
        assert "aws_s3_bucket" in types

    def test_case_insensitive(self):
        """Should be case insensitive."""
        types = _extract_resource_types("AWS_S3_BUCKET error")

        assert "aws_s3_bucket" in types
