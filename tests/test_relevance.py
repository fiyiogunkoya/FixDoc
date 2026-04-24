"""Tests for fixdoc.relevance — attribute-first fix relevance matching."""

from datetime import datetime, timedelta, timezone

import pytest

from fixdoc.change_impact import ImpactNode, is_actionable_change
from fixdoc.models import Fix
from fixdoc.relevance import (
    CHANGE_DOMAINS,
    RelevanceMatcher,
    _extract_error_codes_from_text,
    _fix_matches_resource_type,
    _issue_family,
    _resource_family,
    format_match_narrative,
)
from fixdoc.storage import FixRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(address, resource_type, action, changed_attrs=None,
               attr_categories=None, fingerprint=None):
    """Create a ImpactNode with optional change fingerprint."""
    fp = fingerprint or {}
    if changed_attrs is not None:
        fp.setdefault("changed_attrs", list(changed_attrs))
        fp.setdefault("changed_attr_count", len(changed_attrs))
    if attr_categories is not None:
        fp.setdefault("attr_categories", set(attr_categories))
    fp.setdefault("action", action)
    fp.setdefault("sensitive_changed", False)
    return ImpactNode(address, resource_type, action, change_fingerprint=fp)


# ===================================================================
# TestPrimarySignals
# ===================================================================


class TestPrimarySignals:
    """Primary signals can surface a fix on their own."""

    def test_error_code_match(self, tmp_path):
        """Error code + resource type scores 150, confidence high."""
        repo = FixRepository(tmp_path)
        fix = Fix(
            issue="Error: InvalidInstanceType on aws_instance",
            resolution="Changed instance type to t3.micro",
            tags="aws_instance",
        )
        repo.save(fix)
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert result[0]["score"] >= 150
        assert result[0]["confidence"] == "high"
        assert result[0]["match_reason"]["signal"] == "error_code"

    def test_error_code_no_resource_context(self, tmp_path):
        """Error code WITHOUT resource type match does not score."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Error: BucketAlreadyExists on aws_s3_bucket",
            resolution="Changed bucket name",
            tags="aws_s3_bucket",
        ))
        node = _make_node("aws_iam_role.app", "aws_iam_role", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        for r in result:
            if r.get("match_reason", {}).get("signal") == "error_code":
                pytest.fail("Error code should not match without resource type context")

    def test_address_match(self, tmp_path):
        """Fix mentioning exact address scores 120, confidence high."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app ran out of capacity in us-east-1",
            resolution="Changed AZ to us-east-2",
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert result[0]["score"] >= 120
        assert result[0]["confidence"] == "high"
        assert result[0]["match_reason"]["signal"] == "address"

    def test_address_normalization(self, tmp_path):
        """Leaf address aws_instance.app matches module.web.aws_instance.app."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app had AMI issues",
            resolution="Updated AMI",
        ))
        node = _make_node("module.web.aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert result[0]["score"] >= 120

    def test_changed_attribute_match(self, tmp_path):
        """Changed attribute + resource type scores 100."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Security group ingress rules were too permissive",
            resolution="Restricted ingress to VPC CIDR only",
            tags="aws_security_group",
        ))
        node = _make_node(
            "aws_security_group.web", "aws_security_group", "update",
            changed_attrs=["ingress"],
            attr_categories={"networking"},
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert result[0]["score"] >= 100
        assert result[0]["match_reason"]["signal"] == "changed_attribute"
        assert result[0]["match_reason"]["detail"] == "ingress"

    def test_change_domain_match_iam_trust(self, tmp_path):
        """IAM trust boundary domain scores 85.

        Fix must NOT mention the changed attribute literally (otherwise
        changed_attribute at 100 takes priority over change_domain at 85).
        """
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="IAM role trust was too broad allowing wildcard principal",
            resolution="Restricted to specific service principal",
            tags="aws_iam_role",
        ))
        node = _make_node(
            "aws_iam_role.app", "aws_iam_role", "update",
            changed_attrs=["policy_arn"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert result[0]["match_reason"]["signal"] == "change_domain"
        assert result[0]["match_reason"]["detail"] == "iam_trust_boundary"
        base = 85
        assert result[0]["score"] >= base

    def test_change_domain_match_network_perimeter(self, tmp_path):
        """Network perimeter domain scores 80."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Security group egress was wide open",
            resolution="Restricted egress to specific CIDRs",
            tags="aws_security_group",
        ))
        node = _make_node(
            "aws_security_group.web", "aws_security_group", "update",
            changed_attrs=["ingress"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        # Should match on network_perimeter domain
        mr = result[0]["match_reason"]
        assert mr["signal"] in ("change_domain", "changed_attribute")

    def test_change_domain_capacity_sizing(self, tmp_path):
        """Capacity sizing domain scores 70."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Instance ran out of memory after resize",
            resolution="Changed instance_type to a larger size",
            tags="aws_instance",
        ))
        node = _make_node(
            "aws_db_instance.main", "aws_db_instance", "update",
            changed_attrs=["instance_class"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        mr = result[0]["match_reason"]
        assert mr["signal"] == "change_domain"
        assert mr["detail"] == "capacity_sizing"

    def test_attribute_category_match(self, tmp_path):
        """Attribute category + resource type scores 80."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="VPC connectivity issue",
            resolution="Fixed route table",
            tags="aws_security_group,networking",
        ))
        node = _make_node(
            "aws_security_group.web", "aws_security_group", "update",
            changed_attrs=["egress"],
            attr_categories={"networking"},
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert result[0]["score"] >= 80

    def test_domain_tightness_iam_higher_than_capacity(self, tmp_path):
        """iam_trust_boundary (85) scores higher than capacity_sizing (70)."""
        assert CHANGE_DOMAINS["iam_trust_boundary"]["score"] == 85
        assert CHANGE_DOMAINS["capacity_sizing"]["score"] == 70
        assert CHANGE_DOMAINS["iam_trust_boundary"]["score"] > CHANGE_DOMAINS["capacity_sizing"]["score"]


# ===================================================================
# TestSecondaryBooters
# ===================================================================


class TestSecondaryBoosters:
    """Secondary boosters add to primary match, never standalone."""

    def test_type_text_never_surfaces(self, tmp_path):
        """type_text (was 20) is suppressed — fix should NOT surface."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_s3_bucket versioning broke after update",
            resolution="Re-enabled versioning",
            tags="storage",  # No resource type tag, just text mention
        ))
        node = _make_node("aws_s3_bucket.data", "aws_s3_bucket", "create")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # Should NOT surface — type_text is suppressed
        assert len(result) == 0

    def test_standalone_type_tag_never_surfaces(self, tmp_path):
        """Standalone type_tag (was 40) is suppressed — fix should NOT surface."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Some random unrelated fix",
            resolution="Fixed it somehow",
            tags="aws_s3_bucket",
        ))
        node = _make_node("aws_s3_bucket.data", "aws_s3_bucket", "create")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # Should NOT surface — standalone type_tag is suppressed
        assert len(result) == 0

    def test_standalone_type_action_never_surfaces(self, tmp_path):
        """Standalone type_action (was 60) is suppressed."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Failed to delete aws_s3_bucket - not empty",
            resolution="Empty bucket first",
            tags="aws_s3_bucket",
        ))
        node = _make_node("aws_s3_bucket.data", "aws_s3_bucket", "delete")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # Should NOT surface standalone — only as booster
        assert len(result) == 0

    def test_type_tag_boosts_primary(self, tmp_path):
        """type_tag adds +15 to a primary match (not standalone)."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app had issues with ingress rules",
            resolution="Fixed ingress",
            tags="aws_instance",
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        # Address match (120) + type_tag (+15) + recency (+30) = 165
        supporting = result[0]["match_reason"]["supporting_signals"]
        tag_signals = [s for s in supporting if s["signal"] == "type_tag"]
        assert len(tag_signals) >= 1

    def test_recency_bonus(self, tmp_path):
        """Recent fix (< 90 days) gets +30."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app capacity issue",
            resolution="Changed AZ",
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        supporting = result[0]["match_reason"]["supporting_signals"]
        recency = [s for s in supporting if s["signal"] == "recency"]
        assert len(recency) >= 1

    def test_module_path_bonus(self, tmp_path):
        """Same module path gets +20."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="module.networking vpc routing issue",
            resolution="Fixed route table in module.networking",
            tags="aws_vpc",
        ))
        node = _make_node(
            "module.networking.aws_vpc.main", "aws_vpc", "update",
            changed_attrs=["route_table_id"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        supporting = result[0]["match_reason"]["supporting_signals"]
        module_signals = [s for s in supporting if s["signal"] == "module_path"]
        assert len(module_signals) >= 1

    def test_resource_family_bonus(self, tmp_path):
        """aws_iam_role fix gets +15 for aws_iam_policy change."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_iam_policy.main had overly broad permissions for assume_role_policy",
            resolution="Scoped down to specific actions",
            tags="aws_iam_policy",
        ))
        node = _make_node(
            "aws_iam_role.app", "aws_iam_role", "update",
            changed_attrs=["assume_role_policy"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        supporting = result[0]["match_reason"]["supporting_signals"]
        family_signals = [s for s in supporting if s["signal"] == "resource_family"]
        assert len(family_signals) >= 1
        assert family_signals[0]["detail"] == "aws_iam"


# ===================================================================
# TestDedupClustering
# ===================================================================


class TestDedupClustering:
    """Query-time dedup clusters near-duplicate fixes."""

    def test_similar_fixes_clustered(self, tmp_path):
        """4 similar fixes (same issue pattern) -> 1 result + count."""
        repo = FixRepository(tmp_path)
        for i in range(4):
            repo.save(Fix(
                issue=f"aws_instance.app ran out of capacity in us-east-1 attempt {i}",
                resolution=f"Changed AZ to different zone {i}",
            ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) == 1
        assert result[0]["similar_count"] == 3  # +3 similar

    def test_distinct_issues_not_collapsed(self, tmp_path):
        """Same resource+attr but different issue text -> separate results."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_security_group.web cidr_blocks had duplicate ingress rule causing TF error",
            resolution="Removed duplicate rule",
            tags="aws_security_group",
        ))
        repo.save(Fix(
            issue="aws_security_group.web missing deployment permission for egress update",
            resolution="Added IAM permission for SG modifications",
            tags="aws_security_group",
        ))
        node = _make_node(
            "aws_security_group.web", "aws_security_group", "update",
            changed_attrs=["ingress", "egress"],
            attr_categories={"networking"},
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # Distinct issues should NOT be collapsed
        assert len(result) == 2

    def test_dedup_tiebreak_highest_score(self, tmp_path):
        """Highest score wins in cluster."""
        repo = FixRepository(tmp_path)
        # Both have address match — same issue family (identical text pattern)
        repo.save(Fix(
            issue="aws_instance.app out of capacity in region",
            resolution="Changed AZ fix 1",
        ))
        repo.save(Fix(
            issue="aws_instance.app out of capacity in region",
            resolution="Changed AZ fix 2",
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) == 1
        assert result[0]["score"] >= 120

    def test_dedup_tiebreak_recency(self, tmp_path):
        """When scores tie, most recent fix wins."""
        repo = FixRepository(tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()
        repo.save(Fix(
            issue="aws_instance.app broke during deploy",
            resolution="Old fix",
            created_at=old_ts,
        ))
        repo.save(Fix(
            issue="aws_instance.app broke during deploy",
            resolution="New fix",
            created_at=new_ts,
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) == 1
        assert result[0]["resolution"] == "New fix"


# ===================================================================
# TestDomainMatching
# ===================================================================


class TestDomainMatching:
    """Domain matching tests."""

    def test_cross_domain_no_match(self, tmp_path):
        """Fix in iam_trust_boundary doesn't match network_perimeter change."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="IAM role had overly broad policy with assume_role_policy wildcard",
            resolution="Restricted trust policy",
            tags="aws_iam_role",
        ))
        # Changing a security group (network perimeter), not IAM
        node = _make_node(
            "aws_security_group.web", "aws_security_group", "update",
            changed_attrs=["ingress"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # Should NOT match — different domain
        for r in result:
            mr = r.get("match_reason", {})
            if mr.get("signal") == "change_domain":
                assert mr.get("detail") != "iam_trust_boundary", \
                    "IAM fix should not match network perimeter change"

    def test_domain_requires_attribute_overlap(self, tmp_path):
        """Domain match requires changed attribute in domain's attributes set."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="Encryption issue with kms_key_id",
            resolution="Fixed KMS key reference",
            tags="aws_kms_key",
        ))
        # Node changes 'name' which is NOT in encryption_keying domain
        node = _make_node(
            "aws_kms_key.main", "aws_kms_key", "update",
            changed_attrs=["name"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # kms_key_id is a domain attr, but 'name' is not
        for r in result:
            mr = r.get("match_reason", {})
            if mr.get("signal") == "change_domain":
                assert mr.get("detail") != "encryption_keying"

    def test_domain_fix_must_relate_to_domain(self, tmp_path):
        """Fix must have resource type in domain families OR mention domain attr."""
        repo = FixRepository(tmp_path)
        # Fix about random topic, no IAM mention
        repo.save(Fix(
            issue="DNS resolution failed for web app",
            resolution="Updated Route53 record",
            tags="aws_route53_record",
        ))
        node = _make_node(
            "aws_iam_role.app", "aws_iam_role", "update",
            changed_attrs=["assume_role_policy"],
        )
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        # DNS fix should not match IAM domain change
        for r in result:
            mr = r.get("match_reason", {})
            if mr.get("signal") == "change_domain":
                assert mr.get("detail") != "iam_trust_boundary"


# ===================================================================
# TestNarrativeTemplates
# ===================================================================


class TestNarrativeTemplates:
    """Template rendering for each signal type."""

    def test_error_code_narrative(self):
        match = {
            "match_reason": {
                "signal": "error_code",
                "detail": "InvalidInstanceType",
                "resource_type": "aws_instance",
            },
            "issue": "InvalidInstanceType error",
            "resolution": "Changed instance type",
        }
        text = format_match_narrative(match)
        assert "Previously encountered" in text
        assert "InvalidInstanceType" in text

    def test_address_narrative(self):
        match = {
            "match_reason": {
                "signal": "address",
                "detail": "aws_instance.app",
                "resource_type": "aws_instance",
            },
            "issue": "capacity issue",
            "resolution": "Changed AZ",
        }
        text = format_match_narrative(match)
        assert "exact resource" in text
        assert "aws_instance.app" in text

    def test_changed_attribute_narrative(self):
        match = {
            "match_reason": {
                "signal": "changed_attribute",
                "detail": "ingress",
                "resource_type": "aws_security_group",
            },
            "issue": "Ingress rules issue",
            "resolution": "Restricted ingress to VPC CIDR only",
        }
        text = format_match_narrative(match)
        assert "ingress" in text
        assert "changed previously" in text
        assert "resolved it by" in text

    def test_change_domain_narrative(self):
        match = {
            "match_reason": {
                "signal": "change_domain",
                "detail": "network_perimeter",
                "resource_type": "aws_security_group",
            },
            "issue": "Firewall rules were misconfigured",
            "resolution": "Fixed firewall",
        }
        text = format_match_narrative(match)
        assert "overlaps with" in text
        assert "network perimeter" in text

    def test_attribute_category_narrative(self):
        match = {
            "match_reason": {
                "signal": "attribute_category",
                "detail": "networking",
                "resource_type": "aws_security_group",
            },
            "issue": "Networking configuration was wrong",
            "resolution": "Fixed config",
        }
        text = format_match_narrative(match)
        assert "networking" in text

    def test_presentation_honesty_domain_uses_overlaps(self):
        """Domain matches use 'overlaps with' language, not 'previously encountered'."""
        match = {
            "match_reason": {
                "signal": "change_domain",
                "detail": "iam_trust_boundary",
                "resource_type": "aws_iam_role",
            },
            "issue": "IAM trust issue",
            "resolution": "Fixed it",
        }
        text = format_match_narrative(match)
        assert "overlaps" in text.lower()
        assert "previously encountered" not in text.lower()

    def test_presentation_honesty_error_code_uses_definitive(self):
        """Error code matches use definitive 'Previously encountered' language."""
        match = {
            "match_reason": {
                "signal": "error_code",
                "detail": "BucketAlreadyExists",
                "resource_type": "aws_s3_bucket",
            },
            "issue": "Bucket error",
            "resolution": "Changed name",
        }
        text = format_match_narrative(match)
        assert "Previously encountered" in text

    def test_resolution_truncated(self):
        """Resolution text is truncated at 100 chars."""
        long_resolution = "x" * 200
        match = {
            "match_reason": {
                "signal": "changed_attribute",
                "detail": "ingress",
                "resource_type": "aws_security_group",
            },
            "issue": "Ingress issue",
            "resolution": long_resolution,
        }
        text = format_match_narrative(match)
        # The template includes resolution_summary which is truncated
        assert "..." in text


# ===================================================================
# TestHelpers
# ===================================================================


class TestHelpers:
    """Test helper functions."""

    def test_resource_family(self):
        assert _resource_family("aws_iam_role") == "aws_iam"
        assert _resource_family("aws_s3_bucket") == "aws_s3"
        assert _resource_family("azurerm_role_assignment") == "azurerm_role"

    def test_resource_family_short(self):
        """Single-part resource type returns None (no family)."""
        assert _resource_family("aws") is None

    def test_issue_family_same_text(self):
        """Same issue text produces same family hash."""
        h1 = _issue_family("S3 bucket had wrong ACL")
        h2 = _issue_family("S3 bucket had wrong ACL")
        assert h1 == h2

    def test_issue_family_different_text(self):
        """Different issue text produces different family hash."""
        h1 = _issue_family("S3 bucket had wrong ACL")
        h2 = _issue_family("IAM role had overly broad permissions")
        assert h1 != h2

    def test_extract_error_codes(self):
        codes = _extract_error_codes_from_text("Error: InvalidInstanceType")
        assert "invalidinstancetype" in codes

    def test_fix_matches_resource_type_tag(self):
        fix = Fix(issue="test", resolution="test", tags="aws_instance")
        assert _fix_matches_resource_type(fix, "aws_instance")

    def test_fix_matches_resource_type_text(self):
        fix = Fix(issue="aws_instance failed", resolution="fixed")
        assert _fix_matches_resource_type(fix, "aws_instance")


# ===================================================================
# TestMatchReasonStructure
# ===================================================================


class TestMatchReasonStructure:
    """Verify match_reason dict structure from RelevanceMatcher."""

    def test_match_reason_has_required_keys(self, tmp_path):
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app capacity issue",
            resolution="Changed AZ",
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        mr = result[0]["match_reason"]
        assert "signal" in mr
        assert "detail" in mr
        assert "resource_type" in mr
        assert "confidence" in mr
        assert "supporting_signals" in mr
        assert isinstance(mr["supporting_signals"], list)

    def test_result_has_new_fields(self, tmp_path):
        """Result entries have domain, similar_count, narrative fields."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app had issues",
            resolution="Fixed it",
        ))
        node = _make_node("aws_instance.app", "aws_instance", "update")
        matcher = RelevanceMatcher(repo.list_all())
        result = matcher.match([node])
        assert len(result) >= 1
        assert "domain" in result[0]
        assert "similar_count" in result[0]
        assert "narrative" in result[0]
        assert isinstance(result[0]["narrative"], str)
        assert len(result[0]["narrative"]) > 0


# ===================================================================
# TestIntegrationWithChangeImpact
# ===================================================================


class TestIntegrationWithChangeImpact:
    """Test that find_relevant_fixes in change_impact delegates correctly."""

    def test_find_relevant_fixes_uses_matcher(self, tmp_path):
        """change_impact.find_relevant_fixes delegates to RelevanceMatcher."""
        from fixdoc.change_impact import find_relevant_fixes
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="aws_instance.app capacity issue",
            resolution="Changed AZ",
        ))
        node = ImpactNode("aws_instance.app", "aws_instance", "update")
        result = find_relevant_fixes([node], repo)
        assert len(result) >= 1
        # Should have new fields from RelevanceMatcher
        assert "narrative" in result[0]
        assert "similar_count" in result[0]

    def test_empty_repo(self, tmp_path):
        from fixdoc.change_impact import find_relevant_fixes
        repo = FixRepository(tmp_path)
        node = ImpactNode("aws_s3_bucket.data", "aws_s3_bucket", "create")
        result = find_relevant_fixes([node], repo)
        assert result == []

    def test_max_total_cap(self, tmp_path):
        """Respects max_total cap."""
        from fixdoc.change_impact import find_relevant_fixes
        repo = FixRepository(tmp_path)
        for i in range(10):
            repo.save(Fix(
                issue=f"aws_instance.app_{i} specific error {i} with unique text {i * 1000}",
                resolution=f"Fix {i}",
            ))
        # Create nodes that match the addresses
        nodes = [
            ImpactNode(f"aws_instance.app_{i}", "aws_instance", "update")
            for i in range(10)
        ]
        result = find_relevant_fixes(nodes, repo, max_total=3)
        assert len(result) <= 3


# ===================================================================
# TestChangeDomains
# ===================================================================


class TestChangeDomains:
    """Verify CHANGE_DOMAINS structure."""

    def test_all_domains_have_required_keys(self):
        for name, domain in CHANGE_DOMAINS.items():
            assert "attributes" in domain, f"{name} missing attributes"
            assert "resource_families" in domain, f"{name} missing resource_families"
            assert "score" in domain, f"{name} missing score"
            assert "risk_label" in domain, f"{name} missing risk_label"

    def test_domain_scores_in_range(self):
        for name, domain in CHANGE_DOMAINS.items():
            assert 70 <= domain["score"] <= 85, f"{name} score out of range: {domain['score']}"

    def test_eight_domains_exist(self):
        assert len(CHANGE_DOMAINS) == 8

    def test_iam_trust_boundary_score(self):
        assert CHANGE_DOMAINS["iam_trust_boundary"]["score"] == 85

    def test_secret_access_score(self):
        assert CHANGE_DOMAINS["secret_access"]["score"] == 85

    def test_capacity_sizing_score(self):
        assert CHANGE_DOMAINS["capacity_sizing"]["score"] == 70

    def test_network_attachment_score(self):
        assert CHANGE_DOMAINS["network_attachment"]["score"] == 70
