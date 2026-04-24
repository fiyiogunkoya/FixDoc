"""Tests for memory type classification and rendering preview."""

import pytest

from fixdoc.classifier import classify_memory_type, MEMORY_TYPES
from fixdoc.models import Fix
from fixdoc.rendering import (
    format_suggestion_preview,
    _strip_check_prefix,
    _extract_first_step,
    _count_steps,
)


# ===================================================================
# TestClassifyMemoryTypePlaybook
# ===================================================================


class TestClassifyMemoryTypePlaybook:
    def test_numbered_steps_three_or_more(self):
        resolution = "1. Stop the service\n2. Update the config\n3. Restart the service"
        assert classify_memory_type(resolution) == "playbook"

    def test_only_two_numbered_steps_not_playbook(self):
        resolution = "1. Stop the service\n2. Restart the service"
        assert classify_memory_type(resolution) != "playbook"

    def test_bullet_points_three_or_more(self):
        resolution = "- Stop the service\n- Update the config\n- Restart the service"
        assert classify_memory_type(resolution) == "playbook"

    def test_mixed_bullets_and_numbers(self):
        resolution = "1. Stop the service\n- Update the config\n* Restart the service"
        assert classify_memory_type(resolution) == "playbook"

    def test_step_phase_headers(self):
        resolution = "Step 1 stop\nStep 2 update\nStep 3 restart"
        assert classify_memory_type(resolution) == "playbook"


# ===================================================================
# TestClassifyMemoryTypeCheck
# ===================================================================


class TestClassifyMemoryTypeCheck:
    def test_starts_with_verify(self):
        assert classify_memory_type("Verify that IAM roles are correct") == "check"

    def test_starts_with_ensure(self):
        assert classify_memory_type("Ensure the bucket policy allows access") == "check"

    def test_starts_with_make_sure(self):
        assert classify_memory_type("Make sure the security group is attached") == "check"

    def test_short_text_with_verify_inside(self):
        resolution = "The fix is to verify the SG rules"
        assert len(resolution) < 120
        assert classify_memory_type(resolution) == "check"

    def test_long_text_with_verify_not_at_start(self):
        resolution = (
            "The problem was a misconfigured firewall rule. "
            "You should verify the ingress rules after applying the fix, "
            "but the real issue was the CIDR block overlap that caused "
            "packet drops on the internal network interface."
        )
        assert len(resolution) > 120
        assert classify_memory_type(resolution) != "check"


# ===================================================================
# TestClassifyMemoryTypeInsight
# ===================================================================


class TestClassifyMemoryTypeInsight:
    def test_root_cause_without_actionable_verb(self):
        assert classify_memory_type("Root cause was a stale provider lock") == "insight"

    def test_turns_out_phrase(self):
        assert classify_memory_type("Turns out the VPC peering was asymmetric") == "insight"

    def test_the_reason_phrase(self):
        assert classify_memory_type("The reason was a missing trust policy") == "insight"

    def test_actionable_verb_first_not_insight(self):
        resolution = "Add binding because the root cause was missing permissions"
        assert classify_memory_type(resolution) == "fix"

    def test_lesson_learned_phrase(self):
        assert classify_memory_type("Lesson learned: always pin provider versions") == "insight"


# ===================================================================
# TestClassifyMemoryTypeFix
# ===================================================================


class TestClassifyMemoryTypeFix:
    def test_plain_resolution(self):
        assert classify_memory_type("Added IAM role binding for the service account") == "fix"

    def test_empty_string(self):
        assert classify_memory_type("") == "fix"

    def test_actionable_resolution_with_because(self):
        resolution = "Update the CIDR block because the old one overlapped"
        assert classify_memory_type(resolution) == "fix"


# ===================================================================
# TestClassifyPrecedence
# ===================================================================


class TestClassifyPrecedence:
    def test_numbered_steps_plus_verify_keyword(self):
        """Playbook structure wins over check keyword."""
        resolution = (
            "Verify the following:\n"
            "1. Check IAM role\n"
            "2. Check bucket policy\n"
            "3. Check VPC endpoint"
        )
        assert classify_memory_type(resolution) == "playbook"

    def test_numbered_steps_plus_root_cause(self):
        """Playbook structure wins over insight phrase."""
        resolution = (
            "Root cause was drift. Fix steps:\n"
            "1. Import the resource\n"
            "2. Run terraform plan\n"
            "3. Apply the changes"
        )
        assert classify_memory_type(resolution) == "playbook"

    def test_verify_at_start_plus_because(self):
        """Check wins over insight."""
        resolution = "Verify the policy because the reason was missing permissions"
        assert classify_memory_type(resolution) == "check"


# ===================================================================
# TestFormatSuggestionPreview
# ===================================================================


class TestFormatSuggestionPreview:
    def test_fix_type_plain_truncation(self):
        fix = Fix(issue="test", resolution="A" * 100, memory_type="fix")
        preview = format_suggestion_preview(fix)
        assert preview == "A" * 60 + "..."
        assert not preview.startswith("Verify:")
        assert not preview.startswith("Context:")

    def test_check_type_verify_prefix(self):
        fix = Fix(issue="test", resolution="Ensure the SG is correct", memory_type="check")
        preview = format_suggestion_preview(fix)
        assert preview.startswith("Verify: ")
        # Should strip "Ensure" to avoid stutter
        assert "Ensure" not in preview

    def test_playbook_type_step_count(self):
        resolution = "1. Stop\n2. Update\n3. Restart"
        fix = Fix(issue="test", resolution=resolution, memory_type="playbook")
        preview = format_suggestion_preview(fix)
        assert "Playbook (3 steps):" in preview
        assert "Stop" in preview

    def test_insight_type_context_prefix(self):
        fix = Fix(issue="test", resolution="Root cause was drift", memory_type="insight")
        preview = format_suggestion_preview(fix)
        assert preview.startswith("Context: ")
        assert "Root cause" in preview

    def test_unknown_type_treated_as_fix(self):
        fix = Fix(issue="test", resolution="Some resolution", memory_type="unknown")
        preview = format_suggestion_preview(fix)
        assert preview == "Some resolution"

    def test_truncation_adds_ellipsis(self):
        fix = Fix(issue="test", resolution="A" * 200, memory_type="insight")
        preview = format_suggestion_preview(fix)
        assert preview.endswith("...")
        assert preview.startswith("Context: ")


# ===================================================================
# TestRenderingHelpers
# ===================================================================


class TestRenderingHelpers:
    def test_strip_check_prefix_verify(self):
        assert _strip_check_prefix("Verify that it works") == "that it works"

    def test_strip_check_prefix_ensure(self):
        assert _strip_check_prefix("Ensure: the policy exists") == "the policy exists"

    def test_strip_check_prefix_no_prefix(self):
        assert _strip_check_prefix("The bucket is public") == "The bucket is public"

    def test_extract_first_step_numbered(self):
        text = "1. Stop the service\n2. Update config"
        assert _extract_first_step(text) == "Stop the service"

    def test_extract_first_step_bullet(self):
        text = "- Stop the service\n- Update config"
        assert _extract_first_step(text) == "Stop the service"

    def test_count_steps(self):
        text = "1. A\n2. B\n- C\n* D"
        assert _count_steps(text) == 4

    def test_count_steps_no_steps(self):
        assert _count_steps("Just a plain text resolution") == 0


# ===================================================================
# TestMemoryTypesConstant
# ===================================================================


# ===================================================================
# TestClassifyHardenedPlaybook
# ===================================================================


class TestClassifyHardenedPlaybook:
    def test_playbook_prose_sequence_words(self):
        resolution = "Updated the SG, then restarted bastion, then tested SSH"
        assert classify_memory_type(resolution) == "playbook"

    def test_playbook_action_chain(self):
        resolution = (
            "Applied the fix, restarted the service, "
            "verified health checks, updated the runbook"
        )
        assert classify_memory_type(resolution) == "playbook"

    def test_playbook_mixed_prose_and_bullets(self):
        resolution = (
            "Updated the config then restarted the service.\n"
            "- Verified health checks passed"
        )
        # 2 sequence/action chain matches + 1 bullet = 3+ -> playbook
        assert classify_memory_type(resolution) == "playbook"


# ===================================================================
# TestClassifyHardenedCheck
# ===================================================================


class TestClassifyHardenedCheck:
    def test_check_past_tense_start(self):
        assert classify_memory_type("Confirmed DNS propagation completed") == "check"

    def test_check_verified_start(self):
        assert classify_memory_type("Verified the targets were healthy") == "check"

    def test_check_tested_start(self):
        assert classify_memory_type("Tested SSH access from VPN") == "check"

    def test_check_contains_pattern_short(self):
        resolution = "Ran kubectl rollout and confirmed that pods restarted"
        assert len(resolution) < 200
        assert classify_memory_type(resolution) == "check"

    def test_check_contains_pattern_long_stays_fix(self):
        resolution = (
            "The deployment pipeline was reconfigured to use a blue-green strategy. "
            "After rolling out the new version across all three availability zones, "
            "we confirmed that the health checks were passing on every target group. "
            "The load balancer was then switched over to the new target group and "
            "old instances were terminated after a 30-minute cooldown period."
        )
        assert len(resolution) >= 200
        assert classify_memory_type(resolution) != "check"


# ===================================================================
# TestClassifyHardenedInsight
# ===================================================================


class TestClassifyHardenedInsight:
    def test_insight_after_investigation(self):
        resolution = "After investigation, the failure was due to stale credentials"
        assert classify_memory_type(resolution) == "insight"

    def test_insight_traced_back_to(self):
        resolution = "Traced back to a race condition in the init container"
        assert classify_memory_type(resolution) == "insight"

    def test_insight_this_was_caused_by(self):
        resolution = "This was caused by a misconfigured NAT gateway"
        assert classify_memory_type(resolution) == "insight"

    def test_insight_upon_review(self):
        resolution = "Upon review, the subnet CIDR was overlapping with the peered VPC"
        assert classify_memory_type(resolution) == "insight"


class TestMemoryTypesConstant:
    def test_memory_types_set(self):
        assert MEMORY_TYPES == {"fix", "check", "playbook", "insight"}
