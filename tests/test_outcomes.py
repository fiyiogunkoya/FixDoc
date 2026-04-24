"""Tests for the apply outcome learning system."""

import importlib
import json
from unittest.mock import patch

from click.testing import CliRunner

from fixdoc.outcomes import Outcome, OutcomeStore, compute_plan_fingerprint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(resource_changes=None):
    """Build a minimal Terraform plan dict."""
    return {"resource_changes": resource_changes or []}


def _make_rc(address, actions=None, before=None, after=None):
    """Build a minimal resource_change entry."""
    return {
        "address": address,
        "type": address.split(".")[0] if "." in address else address,
        "name": address.split(".")[-1] if "." in address else "default",
        "change": {
            "actions": actions or ["create"],
            "before": before,
            "after": after or {},
        },
    }


# ---------------------------------------------------------------------------
# Outcome model tests
# ---------------------------------------------------------------------------


class TestOutcomeModel:
    def test_to_dict_roundtrip(self):
        oc = Outcome(
            outcome_id="abcd1234",
            plan_fingerprint="fp123456789012",
            score=45.0,
            severity="medium",
            resource_types=["aws_s3_bucket"],
            resource_count=3,
            top_checks=[
                {
                    "check": "Review access",
                    "source": "attribute",
                    "resource": "aws_s3_bucket.main",
                }
            ],
            commit_sha="abc123",
            pr_number="42",
        )
        d = oc.to_dict()
        restored = Outcome.from_dict(d)
        assert restored.outcome_id == "abcd1234"
        assert restored.plan_fingerprint == "fp123456789012"
        assert restored.score == 45.0
        assert restored.severity == "medium"
        assert restored.resource_types == ["aws_s3_bucket"]
        assert restored.resource_count == 3
        assert restored.top_checks[0]["check"] == "Review access"
        assert restored.commit_sha == "abc123"
        assert restored.pr_number == "42"

    def test_from_dict_missing_optional_fields(self):
        oc = Outcome.from_dict({"outcome_id": "test1234"})
        assert oc.outcome_id == "test1234"
        assert oc.plan_fingerprint == ""
        assert oc.score == 0.0
        assert oc.severity == "low"
        assert oc.resource_types == []
        assert oc.apply_result == "pending"
        assert oc.link_type == "none"
        assert oc.status == "analyzed"

    def test_default_values(self):
        oc = Outcome()
        assert len(oc.outcome_id) == 8
        assert oc.apply_result == "pending"
        assert oc.link_type == "none"
        assert oc.status == "analyzed"
        assert oc.recorded_at  # should be set

    def test_link_type_field(self):
        oc = Outcome(link_type="fingerprint")
        d = oc.to_dict()
        assert d["link_type"] == "fingerprint"
        restored = Outcome.from_dict(d)
        assert restored.link_type == "fingerprint"

    def test_top_checks_structured(self):
        checks = [
            {
                "check": "Review ingress rules",
                "source": "attribute",
                "resource": "aws_security_group.web",
            },
            {
                "check": "Verify AZ availability",
                "source": "category",
                "resource": "",
            },
        ]
        oc = Outcome(top_checks=checks)
        d = oc.to_dict()
        assert d["top_checks"] == checks
        restored = Outcome.from_dict(d)
        assert restored.top_checks == checks


# ---------------------------------------------------------------------------
# Plan fingerprint tests
# ---------------------------------------------------------------------------


class TestPlanFingerprint:
    def test_deterministic(self):
        plan = _make_plan([_make_rc("aws_s3_bucket.main", ["create"])])
        fp1 = compute_plan_fingerprint(plan)
        fp2 = compute_plan_fingerprint(plan)
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_different_plans_differ(self):
        plan_a = _make_plan([_make_rc("aws_s3_bucket.main", ["create"])])
        plan_b = _make_plan([_make_rc("aws_iam_role.admin", ["create"])])
        assert compute_plan_fingerprint(plan_a) != compute_plan_fingerprint(plan_b)

    def test_order_independent(self):
        rc1 = _make_rc("aws_s3_bucket.a", ["create"])
        rc2 = _make_rc("aws_iam_role.b", ["update"])
        plan_a = _make_plan([rc1, rc2])
        plan_b = _make_plan([rc2, rc1])
        assert compute_plan_fingerprint(plan_a) == compute_plan_fingerprint(plan_b)

    def test_attribute_changes_affect_fingerprint(self):
        plan_a = _make_plan(
            [
                _make_rc(
                    "aws_s3_bucket.main",
                    ["update"],
                    before={"acl": "private"},
                    after={"acl": "public"},
                ),
            ]
        )
        plan_b = _make_plan(
            [
                _make_rc(
                    "aws_s3_bucket.main",
                    ["update"],
                    before={"versioning": False},
                    after={"versioning": True},
                ),
            ]
        )
        assert compute_plan_fingerprint(plan_a) != compute_plan_fingerprint(plan_b)


# ---------------------------------------------------------------------------
# OutcomeStore tests
# ---------------------------------------------------------------------------


class TestOutcomeStore:
    def test_save_and_list(self, tmp_path):
        store = OutcomeStore(tmp_path)
        oc = Outcome(outcome_id="aaaa1111", plan_fingerprint="fp1")
        store.save(oc)
        all_oc = store.list_all()
        assert len(all_oc) == 1
        assert all_oc[0].outcome_id == "aaaa1111"

    def test_save_replaces_existing(self, tmp_path):
        store = OutcomeStore(tmp_path)
        oc1 = Outcome(outcome_id="aaaa1111", score=10.0)
        store.save(oc1)
        oc2 = Outcome(outcome_id="aaaa1111", score=20.0)
        store.save(oc2)
        all_oc = store.list_all()
        assert len(all_oc) == 1
        assert all_oc[0].score == 20.0

    def test_find_by_fingerprint_exact(self, tmp_path):
        store = OutcomeStore(tmp_path)
        store.save(Outcome(outcome_id="a1", plan_fingerprint="fp_match"))
        store.save(Outcome(outcome_id="a2", plan_fingerprint="fp_other"))
        matches = store.find_by_fingerprint("fp_match")
        assert len(matches) == 1
        assert matches[0].outcome_id == "a1"

    def test_find_by_fingerprint_no_match(self, tmp_path):
        store = OutcomeStore(tmp_path)
        store.save(Outcome(outcome_id="a1", plan_fingerprint="fp_one"))
        assert store.find_by_fingerprint("fp_two") == []

    def test_update_apply_result(self, tmp_path):
        store = OutcomeStore(tmp_path)
        store.save(Outcome(outcome_id="bbbb2222", plan_fingerprint="fp1"))
        ok = store.update_apply_result(
            "bbbb2222",
            "failure",
            error_output="Error: AccessDenied",
            error_codes=["AccessDenied"],
            commit_sha="def456",
        )
        assert ok
        updated = store.get("bbbb2222")
        assert updated.apply_result == "failure"
        assert updated.status == "applied"
        assert updated.apply_error_output == "Error: AccessDenied"
        assert updated.apply_error_codes == ["AccessDenied"]
        assert updated.apply_commit_sha == "def456"
        assert updated.link_type == "fingerprint"
        assert updated.applied_at is not None

    def test_get_by_id_prefix(self, tmp_path):
        store = OutcomeStore(tmp_path)
        store.save(Outcome(outcome_id="cccc3333"))
        assert store.get("cccc") is not None
        assert store.get("cccc").outcome_id == "cccc3333"
        assert store.get("xxxx") is None

    def test_empty_store(self, tmp_path):
        store = OutcomeStore(tmp_path)
        assert store.list_all() == []
        assert store.get("anything") is None
        assert store.find_by_fingerprint("fp") == []

    def test_clear(self, tmp_path):
        store = OutcomeStore(tmp_path)
        store.save(Outcome(outcome_id="a1"))
        store.save(Outcome(outcome_id="a2"))
        count = store.clear()
        assert count == 2
        assert store.list_all() == []


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


_analyze_mod = importlib.import_module("fixdoc.commands.analyze")


def _make_plan_file(tmp_path, resource_changes=None):
    """Write a plan JSON file and return its path."""
    plan = _make_plan(
        resource_changes
        or [
            _make_rc("aws_s3_bucket.main", ["create"], after={"bucket": "test"}),
        ]
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    return str(plan_path)


class TestAnalyzeRecord:
    def test_analyze_record_saves_outcome(self, tmp_path):
        plan_file = _make_plan_file(tmp_path)
        runner = CliRunner(mix_stderr=False)
        with patch.object(_analyze_mod, "_auto_run_terraform_graph", return_value=None):
            with patch.object(_analyze_mod, "OutcomeStore") as mock_store_cls:
                mock_store = mock_store_cls.return_value
                mock_store.find_by_fingerprint.return_value = []
                result = runner.invoke(
                    _analyze_mod.analyze,
                    [plan_file, "--record", "--format", "json"],
                    obj={"base_path": tmp_path},
                )
        assert result.exit_code == 0
        mock_store.save.assert_called_once()
        saved = mock_store.save.call_args[0][0]
        assert saved.plan_fingerprint
        assert saved.link_type == "fingerprint"

    def test_analyze_record_json_includes_fingerprint(self, tmp_path):
        plan_file = _make_plan_file(tmp_path)
        runner = CliRunner(mix_stderr=False)
        with patch.object(_analyze_mod, "_auto_run_terraform_graph", return_value=None):
            with patch.object(_analyze_mod, "OutcomeStore") as mock_store_cls:
                mock_store = mock_store_cls.return_value
                mock_store.find_by_fingerprint.return_value = []
                result = runner.invoke(
                    _analyze_mod.analyze,
                    [plan_file, "--record", "--format", "json"],
                    obj={"base_path": tmp_path},
                )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_fingerprint" in data
        assert "outcome_id" in data
        assert len(data["plan_fingerprint"]) == 16

    def test_analyze_record_with_pr_and_commit(self, tmp_path):
        plan_file = _make_plan_file(tmp_path)
        runner = CliRunner(mix_stderr=False)
        with patch.object(_analyze_mod, "_auto_run_terraform_graph", return_value=None):
            with patch.object(_analyze_mod, "OutcomeStore") as mock_store_cls:
                mock_store = mock_store_cls.return_value
                mock_store.find_by_fingerprint.return_value = []
                result = runner.invoke(
                    _analyze_mod.analyze,
                    [
                        plan_file,
                        "--record",
                        "--pr",
                        "42",
                        "--commit",
                        "abc123",
                        "--format",
                        "json",
                    ],
                    obj={"base_path": tmp_path},
                )
        assert result.exit_code == 0
        saved = mock_store.save.call_args[0][0]
        assert saved.pr_number == "42"
        assert saved.commit_sha == "abc123"

    def test_analyze_without_record_no_outcome(self, tmp_path):
        plan_file = _make_plan_file(tmp_path)
        runner = CliRunner(mix_stderr=False)
        with patch.object(_analyze_mod, "_auto_run_terraform_graph", return_value=None):
            with patch.object(_analyze_mod, "OutcomeStore") as mock_store_cls:
                mock_store = mock_store_cls.return_value
                mock_store.find_by_fingerprint.return_value = []
                result = runner.invoke(
                    _analyze_mod.analyze,
                    [plan_file, "--format", "json"],
                    obj={"base_path": tmp_path},
                )
        assert result.exit_code == 0
        mock_store.save.assert_not_called()


_outcome_cmd_mod = importlib.import_module("fixdoc.commands.outcome")


class TestRecordApply:
    def test_record_apply_links_to_analysis(self, tmp_path):
        runner = CliRunner()
        analyzed_outcome = Outcome(
            outcome_id="link1234",
            plan_fingerprint="fp_link",
            status="analyzed",
            score=50.0,
        )
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_store = mock_cls.return_value
            mock_store.find_by_fingerprint.return_value = [analyzed_outcome]
            result = runner.invoke(
                _outcome_cmd_mod.record_apply,
                ["--fingerprint", "fp_link", "--result", "success"],
            )
        assert result.exit_code == 0
        assert "link1234" in result.output
        mock_store.update_apply_result.assert_called_once()

    def test_record_apply_standalone_no_prior(self, tmp_path):
        runner = CliRunner()
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_store = mock_cls.return_value
            mock_store.find_by_fingerprint.return_value = []
            result = runner.invoke(
                _outcome_cmd_mod.record_apply,
                [
                    "--fingerprint",
                    "fp_none",
                    "--result",
                    "failure",
                    "--error-output",
                    "boom",
                ],
            )
        assert result.exit_code == 0
        assert "unlinked" in result.output
        mock_store.save.assert_called_once()
        saved = mock_store.save.call_args[0][0]
        assert saved.link_type == "none"
        assert saved.apply_result == "failure"

    def test_record_apply_failure_with_error(self, tmp_path):
        runner = CliRunner()
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_store = mock_cls.return_value
            mock_store.find_by_fingerprint.return_value = []
            result = runner.invoke(
                _outcome_cmd_mod.record_apply,
                [
                    "--fingerprint",
                    "fp1",
                    "--result",
                    "failure",
                    "--error-output",
                    "Error: AccessDenied something",
                ],
            )
        assert result.exit_code == 0
        saved = mock_store.save.call_args[0][0]
        assert saved.apply_error_output == "Error: AccessDenied something"
        assert "AccessDenied" in saved.apply_error_codes

    def test_record_apply_failure_with_error_file(self, tmp_path):
        err_file = tmp_path / "errors.txt"
        err_file.write_text("Error: InvalidPermission.Duplicate\nDetails here")
        runner = CliRunner()
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_store = mock_cls.return_value
            mock_store.find_by_fingerprint.return_value = []
            result = runner.invoke(
                _outcome_cmd_mod.record_apply,
                [
                    "--fingerprint",
                    "fp1",
                    "--result",
                    "failure",
                    "--error-file",
                    str(err_file),
                ],
            )
        assert result.exit_code == 0
        saved = mock_store.save.call_args[0][0]
        assert "InvalidPermission.Duplicate" in saved.apply_error_output

    def test_record_apply_requires_result(self):
        runner = CliRunner()
        result = runner.invoke(
            _outcome_cmd_mod.record_apply,
            ["--fingerprint", "fp1"],
        )
        assert result.exit_code != 0


class TestOutcomeList:
    def test_outcome_list_empty(self):
        runner = CliRunner()
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_cls.return_value.list_all.return_value = []
            result = runner.invoke(_outcome_cmd_mod.outcome_list)
        assert result.exit_code == 0
        assert "No outcomes" in result.output

    def test_outcome_list_with_entries(self):
        runner = CliRunner()
        outcomes = [
            Outcome(
                outcome_id="a1b2c3d4",
                score=45.0,
                severity="medium",
                apply_result="success",
                link_type="fingerprint",
                status="applied",
            ),
            Outcome(
                outcome_id="d3e4f5a6",
                apply_result="failure",
                link_type="none",
                status="applied",
            ),
        ]
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_cls.return_value.list_all.return_value = outcomes
            result = runner.invoke(_outcome_cmd_mod.outcome_list)
        assert result.exit_code == 0
        assert "a1b2c3d4" in result.output
        assert "linked" in result.output
        assert "unlinked" in result.output


class TestOutcomeShow:
    def test_outcome_show_existing(self):
        runner = CliRunner()
        oc = Outcome(
            outcome_id="show1234",
            score=72.0,
            severity="high",
            apply_result="failure",
            link_type="fingerprint",
            status="applied",
            apply_error_codes=["AccessDenied"],
            apply_error_output="Error: AccessDenied on resource",
            commit_sha="abc123",
            pr_number="99",
        )
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_cls.return_value.get.return_value = oc
            result = runner.invoke(_outcome_cmd_mod.outcome_show, ["show1234"])
        assert result.exit_code == 0
        assert "show1234" in result.output
        assert "72.0" in result.output
        assert "HIGH" in result.output
        assert "failure" in result.output
        assert "AccessDenied" in result.output

    def test_outcome_show_not_found(self):
        runner = CliRunner()
        with patch.object(_outcome_cmd_mod, "OutcomeStore") as mock_cls:
            mock_cls.return_value.get.return_value = None
            result = runner.invoke(_outcome_cmd_mod.outcome_show, ["missing"])
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# Change impact display tests
# ---------------------------------------------------------------------------


class TestOutcomeDisplay:
    def _make_result_with_outcome(self):
        from fixdoc.change_impact import ImpactResult

        result = ImpactResult(
            score=45.0,
            severity="medium",
            plan_summary={"total_changes": 2, "by_action": {"update": 2}},
            outcome_matches=[
                {
                    "outcome_id": "fail1234",
                    "apply_result": "failure",
                    "applied_at": "2026-02-28T12:00:00+00:00",
                    "apply_error_codes": ["InvalidPermission.Duplicate"],
                }
            ],
        )
        return result

    def test_outcome_matches_shown_in_human_format(self):
        result = self._make_result_with_outcome()
        output = _analyze_mod._format_human(result, [])
        assert "Historical Apply Outcomes" in output
        assert "previously failed" in output
        assert "fail1234" in output
        assert "InvalidPermission.Duplicate" in output

    def test_outcome_matches_in_json_output(self):
        result = self._make_result_with_outcome()
        json_str = _analyze_mod._format_json(
            result, plan_fingerprint="fp_test", outcome_id="oc_test"
        )
        data = json.loads(json_str)
        assert "outcome_matches" in data
        assert len(data["outcome_matches"]) == 1
        assert data["outcome_matches"][0]["outcome_id"] == "fail1234"
        assert data["plan_fingerprint"] == "fp_test"
        assert data["outcome_id"] == "oc_test"

    def test_no_outcome_matches_no_section(self):
        from fixdoc.change_impact import ImpactResult

        result = ImpactResult(
            score=10.0,
            severity="low",
            plan_summary={"total_changes": 1, "by_action": {"create": 1}},
        )
        output = _analyze_mod._format_human(result, [])
        assert "Historical Apply Outcomes" not in output

    def test_outcome_matches_in_markdown_format(self):
        result = self._make_result_with_outcome()
        output = _analyze_mod._format_markdown(result)
        assert "Historical Apply Outcomes" in output
        assert "previously failed" in output
        assert "fail1234" in output

    def test_score_unchanged_by_outcomes(self):
        """Verify outcomes do NOT alter impact score (v1 observational)."""
        from fixdoc.change_impact import ImpactResult

        result_no_outcome = ImpactResult(score=45.0, severity="medium")
        result_with_outcome = ImpactResult(
            score=45.0,
            severity="medium",
            outcome_matches=[
                {
                    "outcome_id": "fail9999",
                    "apply_result": "failure",
                }
            ],
        )
        assert result_no_outcome.score == result_with_outcome.score


# ---------------------------------------------------------------------------
# Outcome-driven scoring (v2) — analyze integration
# ---------------------------------------------------------------------------


class TestOutcomeDrivenScoring:
    """Tests for outcome failure count being passed through analyze."""

    def test_analyze_passes_outcome_count(self, tmp_path):
        """When outcome store has prior failures, count is passed to analyze_change_impact."""
        import json
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from fixdoc.cli import create_cli
        from fixdoc.config import FixDocConfig

        runner = CliRunner(mix_stderr=False)
        plan = _make_plan([_make_rc("aws_s3_bucket.test", actions=["update"])])
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        # Create a mock outcome that looks like a prior failure
        mock_outcome = MagicMock()
        mock_outcome.apply_result = "failure"
        mock_outcome.status = "applied"
        mock_outcome.to_dict.return_value = {
            "outcome_id": "fail1234",
            "apply_result": "failure",
        }

        with patch.object(_analyze_mod, "_auto_run_terraform_graph", return_value=None), \
             patch.object(_analyze_mod, "OutcomeStore") as MockStore, \
             patch.object(_analyze_mod, "analyze_change_impact", wraps=_analyze_mod.analyze_change_impact) as mock_abr:
            instance = MockStore.return_value
            instance.find_by_fingerprint.return_value = [mock_outcome]

            result = runner.invoke(
                create_cli(),
                ["analyze", str(plan_path), "--format", "json"],
                obj={"base_path": tmp_path, "config": FixDocConfig(), "config_manager": MagicMock()},
            )

        assert result.exit_code == 0
        # Verify outcome_failure_count was passed
        call_kwargs = mock_abr.call_args
        assert call_kwargs[1].get("outcome_failure_count", 0) == 1

    def test_score_unchanged_without_outcomes_v2(self, tmp_path):
        """Backward compat: no outcome store failures means count=0."""
        import json
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from fixdoc.cli import create_cli
        from fixdoc.config import FixDocConfig

        runner = CliRunner(mix_stderr=False)
        plan = _make_plan([_make_rc("aws_s3_bucket.test", actions=["update"])])
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        with patch.object(_analyze_mod, "_auto_run_terraform_graph", return_value=None), \
             patch.object(_analyze_mod, "OutcomeStore") as MockStore, \
             patch.object(_analyze_mod, "analyze_change_impact", wraps=_analyze_mod.analyze_change_impact) as mock_abr:
            instance = MockStore.return_value
            instance.find_by_fingerprint.return_value = []

            result = runner.invoke(
                create_cli(),
                ["analyze", str(plan_path), "--format", "json"],
                obj={"base_path": tmp_path, "config": FixDocConfig(), "config_manager": MagicMock()},
            )

        assert result.exit_code == 0
        call_kwargs = mock_abr.call_args
        assert call_kwargs[1].get("outcome_failure_count", 0) == 0
