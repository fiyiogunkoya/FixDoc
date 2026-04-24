"""Tests for the memory-worthiness classifier."""

import pytest
from unittest.mock import MagicMock

from fixdoc.classifier import (
    _classify_http_status_code,
    _resource_type_from_address,
    classify_entry,
    count_similar_recurrences,
    RECURRENCE_PROMOTION_THRESHOLD,
)
from fixdoc.pending import PendingEntry


def _entry(
    error_id="e1",
    error_code=None,
    kind="resource",
    resource_address=None,
    short_message="some error",
    **kwargs,
):
    """Create a PendingEntry for testing."""
    return PendingEntry(
        error_id=error_id,
        error_type="terraform",
        short_message=short_message,
        error_excerpt="full error text",
        tags="",
        error_code=error_code,
        kind=kind,
        resource_address=resource_address,
        **kwargs,
    )


# ===================================================================
# TestResourceTypeFromAddress
# ===================================================================


class TestResourceTypeFromAddress:
    def test_aws_resource(self):
        assert _resource_type_from_address("aws_iam_role.app") == "aws_iam_role"

    def test_module_prefix_aws(self):
        assert _resource_type_from_address("module.app.aws_s3_bucket.data") == "aws_s3_bucket"

    def test_variable(self):
        assert _resource_type_from_address("variable.foo") == "variable"

    def test_none(self):
        assert _resource_type_from_address(None) is None

    def test_terraform_init(self):
        assert _resource_type_from_address("terraform.init") == "terraform"


# ===================================================================
# TestClassifyEntryKindBased
# ===================================================================


class TestClassifyEntryKindBased:
    def test_terraform_config_is_self_explanatory(self):
        entry = _entry(kind="terraform_config")
        assert classify_entry(entry) == "self_explanatory"

    def test_terraform_init_is_self_explanatory(self):
        entry = _entry(kind="terraform_init")
        assert classify_entry(entry) == "self_explanatory"

    def test_resource_kind_no_code_is_memory_worthy(self):
        entry = _entry(kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_none_kind_no_code_is_self_explanatory(self):
        entry = _entry(kind=None)
        assert classify_entry(entry) == "self_explanatory"


# ===================================================================
# TestClassifyEntryCodeSets
# ===================================================================


class TestClassifyEntryCodeSets:
    def test_access_denied_memory_worthy(self):
        entry = _entry(error_code="AccessDenied", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_bucket_already_exists_memory_worthy(self):
        entry = _entry(error_code="BucketAlreadyExists", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_crash_loop_backoff_memory_worthy(self):
        entry = _entry(error_code="CrashLoopBackOff", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_image_pull_backoff_memory_worthy(self):
        entry = _entry(error_code="ImagePullBackOff", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_limit_exceeded_memory_worthy(self):
        entry = _entry(error_code="LimitExceeded", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_missing_required_variable_on_resource_is_self_explanatory(self):
        """Code in _SELF_EXPLANATORY_CODES overrides resource default."""
        entry = _entry(error_code="MissingRequiredVariable", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_default_value_on_resource_is_self_explanatory(self):
        entry = _entry(error_code="InvalidDefaultValue", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_unknown_code_on_resource_is_memory_worthy(self):
        entry = _entry(error_code="SomeUnknownCode", kind="resource")
        assert classify_entry(entry) == "memory_worthy"


# ===================================================================
# TestClassifyEntryRecurrence
# ===================================================================


class TestClassifyEntryRecurrence:
    def _mock_store(self, entries):
        store = MagicMock()
        store.list_all.return_value = entries
        return store

    def test_three_recurrences_promotes_terraform_config(self):
        """3+ similar recurrences promotes terraform_config to memory_worthy."""
        entry = _entry(
            error_id="new",
            error_code="InvalidDefaultValue",
            kind="terraform_config",
            resource_address="variable.foo",
        )
        others = [
            _entry(
                error_id=f"old_{i}",
                error_code="InvalidDefaultValue",
                kind="terraform_config",
                resource_address="variable.bar",
            )
            for i in range(3)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "memory_worthy"

    def test_two_recurrences_stays_self_explanatory(self):
        entry = _entry(
            error_id="new",
            error_code="InvalidDefaultValue",
            kind="terraform_config",
            resource_address="variable.foo",
        )
        others = [
            _entry(
                error_id=f"old_{i}",
                error_code="InvalidDefaultValue",
                kind="terraform_config",
                resource_address="variable.bar",
            )
            for i in range(2)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "self_explanatory"

    def test_exact_threshold_promotes(self):
        entry = _entry(
            error_id="new",
            error_code="AccessDenied",
            kind="terraform_config",
            resource_address="aws_iam_role.app",
        )
        others = [
            _entry(
                error_id=f"old_{i}",
                error_code="AccessDenied",
                resource_address="aws_iam_role.other",
            )
            for i in range(RECURRENCE_PROMOTION_THRESHOLD)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "memory_worthy"

    def test_store_none_skips_recurrence(self):
        """store=None skips recurrence check, uses kind/code rules."""
        entry = _entry(kind="terraform_config", error_code="InvalidDefaultValue")
        assert classify_entry(entry, store=None) == "self_explanatory"

    def test_matches_on_same_code_and_resource_type(self):
        entry = _entry(
            error_id="new",
            error_code="AccessDenied",
            kind="terraform_config",
            resource_address="aws_iam_role.app",
        )
        # Same code + same resource type prefix
        others = [
            _entry(
                error_id=f"old_{i}",
                error_code="AccessDenied",
                resource_address=f"aws_iam_role.svc_{i}",
            )
            for i in range(3)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "memory_worthy"

    def test_excludes_self_from_count(self):
        entry = _entry(
            error_id="same_id",
            error_code="AccessDenied",
            kind="terraform_config",
            resource_address="aws_iam_role.app",
        )
        # Include the entry itself + 2 others = only 2 matches (below threshold)
        others = [entry] + [
            _entry(
                error_id=f"old_{i}",
                error_code="AccessDenied",
                resource_address=f"aws_iam_role.svc_{i}",
            )
            for i in range(2)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "self_explanatory"


# ===================================================================
# TestCountSimilarRecurrences
# ===================================================================


class TestCountSimilarRecurrences:
    def _mock_store(self, entries):
        store = MagicMock()
        store.list_all.return_value = entries
        return store

    def test_matches_same_code_and_resource_type(self):
        entry = _entry(
            error_id="new",
            error_code="AccessDenied",
            resource_address="aws_iam_role.app",
        )
        others = [
            _entry(
                error_id="old_1",
                error_code="AccessDenied",
                resource_address="aws_iam_role.other",
            ),
            _entry(
                error_id="old_2",
                error_code="AccessDenied",
                resource_address="aws_iam_role.svc",
            ),
        ]
        store = self._mock_store(others)
        assert count_similar_recurrences(entry, store) == 2

    def test_different_code_no_match(self):
        entry = _entry(
            error_id="new",
            error_code="AccessDenied",
            resource_address="aws_iam_role.app",
        )
        others = [
            _entry(
                error_id="old_1",
                error_code="BucketAlreadyExists",
                resource_address="aws_iam_role.other",
            ),
        ]
        store = self._mock_store(others)
        assert count_similar_recurrences(entry, store) == 0

    def test_different_resource_type_no_match(self):
        entry = _entry(
            error_id="new",
            error_code="AccessDenied",
            resource_address="aws_iam_role.app",
        )
        others = [
            _entry(
                error_id="old_1",
                error_code="AccessDenied",
                resource_address="aws_s3_bucket.data",
            ),
        ]
        store = self._mock_store(others)
        assert count_similar_recurrences(entry, store) == 0

    def test_fallback_no_error_code(self):
        entry = _entry(
            error_id="new",
            error_code=None,
            kind="resource",
            short_message="Error creating bucket",
        )
        others = [
            _entry(
                error_id="old_1",
                error_code=None,
                kind="resource",
                short_message="Error deleting something",
            ),
            _entry(
                error_id="old_2",
                error_code=None,
                kind="resource",
                short_message="Error updating other",
            ),
        ]
        store = self._mock_store(others)
        assert count_similar_recurrences(entry, store) == 2

    def test_excludes_self(self):
        entry = _entry(
            error_id="same_id",
            error_code="AccessDenied",
            resource_address="aws_iam_role.app",
        )
        others = [entry]  # Only self in the store
        store = self._mock_store(others)
        assert count_similar_recurrences(entry, store) == 0

    def test_includes_superseded_and_self_explanatory(self):
        entry = _entry(
            error_id="new",
            error_code="AccessDenied",
            resource_address="aws_iam_role.app",
        )
        store = MagicMock()
        store.list_all.return_value = [
            _entry(
                error_id="old_1",
                error_code="AccessDenied",
                resource_address="aws_iam_role.other",
                status="superseded",
                worthiness="self_explanatory",
            ),
        ]
        assert count_similar_recurrences(entry, store) == 1
        store.list_all.assert_called_once_with(
            include_superseded=True, include_self_explanatory=True
        )


# ===================================================================
# TestClassifyPrecedence
# ===================================================================


class TestClassifyPrecedence:
    def _mock_store(self, entries):
        store = MagicMock()
        store.list_all.return_value = entries
        return store

    def test_recurrence_beats_kind_override(self):
        """Even terraform_config is promoted if enough recurrences."""
        entry = _entry(
            error_id="new",
            error_code="InvalidDefaultValue",
            kind="terraform_config",
            resource_address="variable.foo",
        )
        others = [
            _entry(
                error_id=f"old_{i}",
                error_code="InvalidDefaultValue",
                kind="terraform_config",
                resource_address="variable.bar",
            )
            for i in range(3)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "memory_worthy"

    def test_kind_returns_before_code_check(self):
        """terraform_config with a self_explanatory code returns at kind step."""
        entry = _entry(
            error_code="MissingRequiredVariable",
            kind="terraform_config",
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_memory_worthy_code_on_resource(self):
        entry = _entry(error_code="AccessDenied", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_self_explanatory_code_overrides_resource_default(self):
        entry = _entry(error_code="UnsupportedArgument", kind="resource")
        assert classify_entry(entry) == "self_explanatory"


# ===================================================================
# TestMessageHeuristic — step 3.5
# ===================================================================


class TestMessageHeuristic:
    """Tests for message-based self-explanatory classification."""

    def test_invalid_cidr_self_explanatory(self):
        """'not a valid CIDR block' is self-explanatory even on a resource."""
        entry = _entry(
            kind="resource",
            resource_address="aws_security_group.bad_cidr",
            short_message='"10.0.0.0/33" is not a valid CIDR block: invalid CIDR address',
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_json_policy_self_explanatory(self):
        """'contains an invalid JSON policy' is self-explanatory."""
        entry = _entry(
            kind="resource",
            resource_address="aws_iam_role.bad_policy",
            short_message='"assume_role_policy" contains an invalid JSON policy: not a JSON object',
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_arn_self_explanatory(self):
        entry = _entry(
            kind="resource",
            short_message="invalid ARN: arn:aws:iam::123",
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_expected_type_self_explanatory(self):
        entry = _entry(
            kind="resource",
            short_message='Inappropriate value for attribute "cidr_block": expected type string',
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_memory_worthy_code_overrides_message_heuristic(self):
        """A memory-worthy error code still wins over a self-explanatory message."""
        entry = _entry(
            kind="resource",
            error_code="AccessDenied",
            short_message="invalid json in the response",
        )
        assert classify_entry(entry) == "memory_worthy"

    def test_normal_resource_error_unaffected(self):
        """Normal resource errors without matching patterns stay memory_worthy."""
        entry = _entry(
            kind="resource",
            resource_address="aws_s3_bucket.data",
            short_message="creating S3 Bucket: BucketAlreadyExists",
        )
        assert classify_entry(entry) == "memory_worthy"

    def test_recurrence_overrides_message_heuristic(self):
        """Recurrence promotion still wins over self-explanatory message."""
        store = MagicMock()
        store.list_all.return_value = [
            _entry(error_id=f"e{i}", short_message='"10.0.0.0/33" is not a valid CIDR block')
            for i in range(RECURRENCE_PROMOTION_THRESHOLD)
        ]
        entry = _entry(
            error_id="new",
            kind="resource",
            short_message='"10.0.0.0/33" is not a valid CIDR block',
        )
        assert classify_entry(entry, store) == "memory_worthy"


# ===================================================================
# TestNewSelfExplanatoryCodes — Gap 1 + Gap 2
# ===================================================================


class TestNewSelfExplanatoryCodes:
    def test_validation_exception_self_explanatory(self):
        entry = _entry(error_code="ValidationException", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_parameter_value_self_explanatory(self):
        entry = _entry(error_code="InvalidParameterValue", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_parameter_combination_self_explanatory(self):
        entry = _entry(error_code="InvalidParameterCombination", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_parameter_azure_self_explanatory(self):
        entry = _entry(error_code="InvalidParameter", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_argument_gcp_self_explanatory(self):
        entry = _entry(error_code="InvalidArgument", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_invalid_k8s_self_explanatory(self):
        entry = _entry(error_code="Invalid", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_chart_not_found_helm_self_explanatory(self):
        entry = _entry(error_code="ChartNotFound", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_forbidden_k8s_memory_worthy(self):
        entry = _entry(error_code="Forbidden", kind="resource")
        assert classify_entry(entry) == "memory_worthy"


# ===================================================================
# TestExpandedMessagePatterns — Gap 3
# ===================================================================


class TestExpandedMessagePatterns:
    def test_already_exists(self):
        entry = _entry(kind="resource", short_message="Security group already exists")
        assert classify_entry(entry) == "self_explanatory"

    def test_syntax_error(self):
        entry = _entry(kind="resource", short_message="syntax error in configuration")
        assert classify_entry(entry) == "self_explanatory"

    def test_type_mismatch(self):
        entry = _entry(kind="resource", short_message="type mismatch: expected string")
        assert classify_entry(entry) == "self_explanatory"

    def test_is_required(self):
        entry = _entry(kind="resource", short_message='field "name" is required')
        assert classify_entry(entry) == "self_explanatory"

    def test_is_not_defined(self):
        entry = _entry(kind="resource", short_message="variable foo is not defined")
        assert classify_entry(entry) == "self_explanatory"

    def test_does_not_exist(self):
        entry = _entry(kind="resource", short_message="subnet does not exist")
        assert classify_entry(entry) == "self_explanatory"

    def test_could_not_find(self):
        entry = _entry(kind="resource", short_message="could not find module foobar")
        assert classify_entry(entry) == "self_explanatory"

    def test_malformed(self):
        entry = _entry(kind="resource", short_message="malformed policy document")
        assert classify_entry(entry) == "self_explanatory"

    def test_duplicate(self):
        entry = _entry(kind="resource", short_message="duplicate key in map")
        assert classify_entry(entry) == "self_explanatory"

    def test_out_of_range(self):
        entry = _entry(kind="resource", short_message="port 99999 is out of range")
        assert classify_entry(entry) == "self_explanatory"


# ===================================================================
# TestHttpStatusCodes — Gap 4
# ===================================================================


class TestHttpStatusCodes:
    def test_403_forbidden_memory_worthy(self):
        entry = _entry(error_code="403Forbidden", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_401_unauthorized_memory_worthy(self):
        entry = _entry(error_code="401Unauthorized", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_429_too_many_requests_memory_worthy(self):
        entry = _entry(error_code="429TooManyRequests", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_409_conflict_memory_worthy(self):
        entry = _entry(error_code="409Conflict", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_400_bad_request_self_explanatory(self):
        entry = _entry(error_code="400BadRequest", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_404_not_found_self_explanatory(self):
        entry = _entry(error_code="404NotFound", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_422_unprocessable_self_explanatory(self):
        entry = _entry(error_code="422UnprocessableEntity", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_non_http_code_returns_none(self):
        assert _classify_http_status_code("AccessDenied") is None


# ===================================================================
# TestCodeOverridesMessage — precedence between code and message
# ===================================================================


class TestCodeOverridesMessage:
    def test_bucket_already_exists_code_beats_message(self):
        """BucketAlreadyExists code + 'already exists' message -> memory_worthy."""
        entry = _entry(
            error_code="BucketAlreadyExists",
            kind="resource",
            short_message="bucket already exists",
        )
        assert classify_entry(entry) == "memory_worthy"

    def test_access_denied_code_beats_message(self):
        """AccessDenied code + 'does not exist' message -> memory_worthy."""
        entry = _entry(
            error_code="AccessDenied",
            kind="resource",
            short_message="resource does not exist",
        )
        assert classify_entry(entry) == "memory_worthy"

    def test_validation_exception_on_resource(self):
        """ValidationException code on resource -> self_explanatory."""
        entry = _entry(error_code="ValidationException", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_no_code_already_exists_message(self):
        """No code + 'already exists' message on resource -> self_explanatory."""
        entry = _entry(
            kind="resource",
            short_message="Security group already exists",
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_recurrence_beats_already_exists_message(self):
        """3+ recurrences + 'already exists' message -> memory_worthy."""
        store = MagicMock()
        store.list_all.return_value = [
            _entry(error_id=f"e{i}", short_message="SG already exists")
            for i in range(RECURRENCE_PROMOTION_THRESHOLD)
        ]
        entry = _entry(
            error_id="new",
            kind="resource",
            short_message="SG already exists",
        )
        assert classify_entry(entry, store) == "memory_worthy"

    def test_forbidden_code_on_resource(self):
        """Forbidden code on resource -> memory_worthy."""
        entry = _entry(error_code="Forbidden", kind="resource")
        assert classify_entry(entry) == "memory_worthy"


# ===================================================================
# TestStepOrderPreservation — verifies full classification order
# ===================================================================


class TestStepOrderPreservation:
    def _mock_store(self, entries):
        store = MagicMock()
        store.list_all.return_value = entries
        return store

    def test_recurrence_beats_self_explanatory_code(self):
        """3+ recurrences -> memory_worthy even with self-explanatory code."""
        entry = _entry(
            error_id="new",
            error_code="ValidationException",
            kind="resource",
            resource_address="aws_s3_bucket.data",
        )
        others = [
            _entry(
                error_id=f"old_{i}",
                error_code="ValidationException",
                resource_address=f"aws_s3_bucket.other_{i}",
            )
            for i in range(3)
        ]
        store = self._mock_store(others)
        assert classify_entry(entry, store) == "memory_worthy"

    def test_kind_override_beats_memory_worthy_code(self):
        """terraform_config -> self_explanatory even with memory-worthy code."""
        entry = _entry(
            error_code="AccessDenied",
            kind="terraform_config",
        )
        assert classify_entry(entry) == "self_explanatory"

    def test_memory_worthy_code_beats_message(self):
        """Memory-worthy code wins over self-explanatory message."""
        entry = _entry(
            error_code="Forbidden",
            kind="resource",
            short_message="resource does not exist",
        )
        assert classify_entry(entry) == "memory_worthy"

    def test_self_explanatory_code_beats_resource_default(self):
        """Self-explanatory code wins over resource default."""
        entry = _entry(error_code="InvalidArgument", kind="resource")
        assert classify_entry(entry) == "self_explanatory"

    def test_memory_worthy_code_not_overridden_by_http(self):
        """Known memory-worthy code is checked before HTTP handler."""
        entry = _entry(error_code="AccessDenied", kind="resource")
        assert classify_entry(entry) == "memory_worthy"

    def test_message_heuristic_fires_after_http_status(self):
        """HTTP status takes precedence; message heuristic fires for non-HTTP codes."""
        entry = _entry(
            kind="resource",
            error_code="SomeUnknownCode",
            short_message="resource already exists",
        )
        # Unknown code not in any set, not HTTP -> falls to message heuristic
        assert classify_entry(entry) == "self_explanatory"
