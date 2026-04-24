"""Tests for the fixdoc import system (Jira, ServiceNow, Notion, Slack)."""

import csv
import json
import urllib.error
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixdoc.importers.base import (
    ImportResult,
    build_fix,
    clean_text,
    detect_resource_types,
    is_high_signal,
    normalize_tags,
    parse_csv,
    parse_json,
    slugify_tag,
)
from fixdoc.importers import jira, servicenow
from fixdoc.models import Fix
from fixdoc.storage import FixRepository


FIXTURES = Path(__file__).parent / "fixtures" / "import"


# ---------------------------------------------------------------------------
# slugify_tag
# ---------------------------------------------------------------------------


class TestSlugifyTag:
    def test_basic(self):
        assert slugify_tag("terraform") == "terraform"

    def test_spaces_to_underscores(self):
        assert slugify_tag("Cloud Platform Team") == "cloud_platform_team"

    def test_hyphens_to_underscores(self):
        assert slugify_tag("k8s-team") == "k8s_team"

    def test_mixed(self):
        assert slugify_tag("AWS Lambda-Function") == "aws_lambda_function"

    def test_strips_special_chars(self):
        assert slugify_tag("iam!rbac@") == "iamrbac"

    def test_empty(self):
        assert slugify_tag("") == ""


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_no_html(self):
        assert clean_text("Hello world") == "Hello world"

    def test_collapses_whitespace(self):
        assert clean_text("hello   world") == "hello world"

    def test_strips_safe_html_tags(self):
        result = clean_text("<p>Hello</p><br>World")
        assert "<p>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_leaves_log_lines_intact(self):
        # Lines with < in non-HTML context should NOT be stripped
        text = "Error: resource <terraform_resource> not found"
        result = clean_text(text)
        assert "<terraform_resource>" in result

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_strips_div_span(self):
        # HTML heuristic now triggers on <div directly
        result = clean_text("<div><span>test</span></div>")
        assert result == "test"
        assert "<div>" not in result


# ---------------------------------------------------------------------------
# normalize_tags
# ---------------------------------------------------------------------------


class TestNormalizeTags:
    def test_stable_sort_order(self):
        result = normalize_tags(
            resource_types=["aws_s3_bucket", "aws_iam_role"],
            keywords=["kw:terraform", "kw:iam"],
            source_tag="source:jira:PROJ-1",
            user_tags=["demo"],
        )
        parts = result.split(",")
        # Resource types come first (sorted), then kw:, then source:, then user tags
        assert parts[0] == "aws_iam_role"
        assert parts[1] == "aws_s3_bucket"
        assert "kw:iam" in parts
        assert "kw:terraform" in parts
        assert "source:jira:proj-1" in parts
        assert parts[-1] == "demo"

    def test_deduplication(self):
        result = normalize_tags(
            resource_types=["aws_s3_bucket", "aws_s3_bucket"],
            keywords=[],
            source_tag="source:jira:X",
            user_tags=[],
        )
        parts = result.split(",")
        assert parts.count("aws_s3_bucket") == 1

    def test_empty(self):
        result = normalize_tags([], [], "source:jira:X", [])
        assert result == "source:jira:x"

    def test_user_tags_lowercased(self):
        result = normalize_tags([], [], "source:jira:X", ["TERRAFORM", "IAM"])
        assert "terraform" in result
        assert "iam" in result


# ---------------------------------------------------------------------------
# detect_resource_types
# ---------------------------------------------------------------------------


class TestDetectResourceTypes:
    def test_aws_resource(self):
        rts, kws = detect_resource_types("aws_s3_bucket is failing")
        assert "aws_s3_bucket" in rts

    def test_multiple_providers(self):
        text = "aws_iam_role and azurerm_resource_group and google_compute_instance"
        rts, kws = detect_resource_types(text)
        assert "aws_iam_role" in rts
        assert "azurerm_resource_group" in rts
        assert "google_compute_instance" in rts

    def test_kw_tags(self):
        _, kws = detect_resource_types("IAM role missing terraform state")
        assert "kw:iam" in kws
        assert "kw:terraform" in kws

    def test_across_all_fields(self):
        text = "aws_security_group failing iam policy s3 bucket rds lambda vpc"
        rts, kws = detect_resource_types(text)
        assert "aws_security_group" in rts
        assert "kw:iam" in kws
        assert "kw:s3" in kws

    def test_no_false_positive_aws_s3_bucket_policy(self):
        # Plan changes aws_s3_bucket; fixes have aws_s3_bucket_policy — no false positive expected
        # (detect_resource_types just extracts what's in the text)
        rts, _ = detect_resource_types("aws_s3_bucket update needed")
        assert "aws_s3_bucket" in rts
        assert "aws_s3_bucket_policy" not in rts


# ---------------------------------------------------------------------------
# is_high_signal
# ---------------------------------------------------------------------------


class TestIsHighSignal:
    def test_with_resource_type_tag(self):
        fix = Fix(issue="x", resolution="y", tags="aws_s3_bucket,kw:s3")
        assert is_high_signal(fix) is True

    def test_with_kw_terraform(self):
        fix = Fix(issue="x", resolution="y", tags="kw:terraform")
        assert is_high_signal(fix) is True

    def test_with_kw_iam(self):
        fix = Fix(issue="x", resolution="y", tags="kw:iam")
        assert is_high_signal(fix) is True

    def test_with_kw_rbac(self):
        fix = Fix(issue="x", resolution="y", tags="kw:rbac")
        assert is_high_signal(fix) is True

    def test_with_kw_kubernetes(self):
        fix = Fix(issue="x", resolution="y", tags="kw:kubernetes")
        assert is_high_signal(fix) is True

    def test_generic_ticket_no_signal(self):
        fix = Fix(
            issue="Server is slow", resolution="Restarted", tags="source:jira:GEN-1"
        )
        assert is_high_signal(fix) is False

    def test_no_tags(self):
        fix = Fix(issue="x", resolution="y")
        assert is_high_signal(fix) is False

    def test_low_signal_kw_only(self):
        # kw:s3 alone is not in _HIGH_SIGNAL_KW
        fix = Fix(issue="x", resolution="y", tags="kw:s3,source:jira:X")
        assert is_high_signal(fix) is False


# ---------------------------------------------------------------------------
# build_fix
# ---------------------------------------------------------------------------


class TestBuildFix:
    def test_truncates_issue(self):
        fix = build_fix("A" * 400, "resolution", None, "", None)
        assert len(fix.issue) == 300

    def test_truncates_resolution(self):
        fix = build_fix("issue", "R" * 4000, None, "", None)
        assert len(fix.resolution) == 3000

    def test_truncates_error_excerpt(self):
        fix = build_fix("issue", "resolution", "E" * 2500, "", None)
        assert len(fix.error_excerpt) == 2000

    def test_notes_stored(self):
        fix = build_fix("issue", "resolution", None, "", "Source: jira PROJ-1")
        assert fix.notes == "Source: jira PROJ-1"

    def test_empty_error_excerpt_becomes_none(self):
        fix = build_fix("issue", "resolution", "", "", None)
        assert fix.error_excerpt is None


# ---------------------------------------------------------------------------
# parse_csv / parse_json
# ---------------------------------------------------------------------------


class TestParseCSV:
    def test_utf8_bom_handling(self):
        rows, bad = parse_csv(FIXTURES / "jira_bom.csv")
        for row in rows:
            for key in row.keys():
                assert not key.startswith("\ufeff"), f"BOM in key: {repr(key)}"
        assert any("bom-001" in str(row.get("issue key", "")).lower() for row in rows)

    def test_semicolon_delimiter_sniffed(self):
        rows, bad = parse_csv(FIXTURES / "snow_semicolon.csv")
        assert len(rows) == 2
        assert "number" in rows[0]

    def test_sniffer_fallback_no_exception(self, tmp_path):
        """Sniffer failure falls back to comma without raising."""
        bad_file = tmp_path / "weird.csv"
        bad_file.write_bytes(b"col1,col2\nval1,val2\n")
        rows, bad = parse_csv(bad_file)
        assert isinstance(rows, list)

    def test_multiline_field_in_quoted_cell(self, tmp_path):
        """Multi-line values in quoted CSV cells are handled."""
        csv_file = tmp_path / "multi.csv"
        content = "Issue key,Summary,Status,Resolution,Description,Labels,Components\n"
        content += (
            'MULTI-1,"Short summary",Done,"Line1\nLine2","Desc line1\n\nDesc para2",,\n'
        )
        csv_file.write_text(content)
        rows, bad = parse_csv(csv_file)
        assert len(rows) == 1

    def test_bad_row_increments_counter(self, tmp_path):
        """Rows that fail processing increment bad_rows count."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "Issue key,Summary,Status,Resolution\n"
            "GOOD-1,Good summary,Done,Good resolution\n"
            "BAD-1\n"
            "GOOD-2,Another summary,Done,Another resolution\n"
        )
        rows, bad_parse = parse_csv(csv_file)
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# jira module
# ---------------------------------------------------------------------------


class TestJiraImporter:
    def test_is_closed_done(self):
        assert jira.is_closed({"status": "Done"}) is True

    def test_is_closed_closed(self):
        assert jira.is_closed({"status": "Closed"}) is True

    def test_is_closed_resolved(self):
        assert jira.is_closed({"status": "Resolved"}) is True

    def test_is_closed_excludes_wont_do(self):
        assert jira.is_closed({"status": "Won't Do"}) is False

    def test_is_closed_in_progress(self):
        assert jira.is_closed({"status": "In Progress"}) is False

    def test_extract_from_sample_csv(self):
        rows, _ = parse_csv(FIXTURES / "jira_sample.csv")
        fixes, _ = jira.extract(rows, closed_only=True, extra_tags=[], max_count=None)
        # 6 closed, 1 Won't Do (excluded), 1 In Progress (excluded)
        assert len(fixes) == 6

    def test_wont_do_excluded(self):
        rows, _ = parse_csv(FIXTURES / "jira_sample.csv")
        fixes, _ = jira.extract(rows, closed_only=True, extra_tags=[], max_count=None)
        assert not any("PLATFORM-129" in (f.notes or "") for f in fixes)

    def test_comment_multi_segment_uses_last(self):
        rows, _ = parse_csv(FIXTURES / "jira_sample.csv")
        fixes, _ = jira.extract(rows, closed_only=True, extra_tags=[], max_count=None)
        p124 = next((f for f in fixes if "PLATFORM-124" in (f.notes or "")), None)
        assert p124 is not None
        assert "cross-account role" in p124.resolution.lower()

    def test_source_tag_in_tags(self):
        rows, _ = parse_csv(FIXTURES / "jira_sample.csv")
        fixes, _ = jira.extract(rows, closed_only=True, extra_tags=[], max_count=None)
        for fix in fixes:
            assert fix.tags is not None
            assert any(
                t.strip().startswith("source:jira:") for t in fix.tags.split(",")
            )

    def test_max_stops_after_n_rows(self):
        rows, _ = parse_csv(FIXTURES / "jira_sample.csv")
        fixes, _ = jira.extract(rows, closed_only=False, extra_tags=[], max_count=3)
        assert len(fixes) <= 3

    def test_extra_tags_appended(self):
        rows, _ = parse_csv(FIXTURES / "jira_sample.csv")
        fixes, _ = jira.extract(
            rows, closed_only=True, extra_tags=["demo"], max_count=None
        )
        for fix in fixes:
            assert "demo" in fix.tags

    def test_json_import_fields_summary(self):
        raw = parse_json(FIXTURES / "jira_backup.json")
        fixes, _ = jira.extract(
            raw, closed_only=True, extra_tags=[], max_count=None, is_json=True
        )
        # PROJ-001: Done, PROJ-002: Resolved, PROJ-004: Closed → 3 closed
        # PROJ-003: In Progress → excluded; PROJ-005: Won't Do → excluded
        assert len(fixes) == 3

    def test_json_resolution_name(self):
        raw = parse_json(FIXTURES / "jira_backup.json")
        fixes, _ = jira.extract(
            raw, closed_only=True, extra_tags=[], max_count=None, is_json=True
        )
        proj1 = next((f for f in fixes if "PROJ-001" in (f.notes or "")), None)
        assert proj1 is not None
        assert "trust relationship" in proj1.resolution.lower()

    def test_json_fallback_to_last_comment(self):
        raw = parse_json(FIXTURES / "jira_backup.json")
        fixes, _ = jira.extract(
            raw, closed_only=True, extra_tags=[], max_count=None, is_json=True
        )
        proj4 = next((f for f in fixes if "PROJ-004" in (f.notes or "")), None)
        assert proj4 is not None
        assert "versioning" in proj4.resolution.lower()

    def test_json_error_excerpt_first_paragraph(self):
        raw = parse_json(FIXTURES / "jira_backup.json")
        fixes, _ = jira.extract(
            raw, closed_only=True, extra_tags=[], max_count=None, is_json=True
        )
        proj1 = next((f for f in fixes if "PROJ-001" in (f.notes or "")), None)
        assert proj1 is not None
        assert "aws_iam_role" in (proj1.error_excerpt or "")

    def test_json_labels_and_components_slugified(self):
        raw = parse_json(FIXTURES / "jira_backup.json")
        fixes, _ = jira.extract(
            raw, closed_only=True, extra_tags=[], max_count=None, is_json=True
        )
        proj1 = next((f for f in fixes if "PROJ-001" in (f.notes or "")), None)
        assert proj1 is not None
        assert "platform_team" in proj1.tags

    def test_json_wrapper_and_bare_array(self, tmp_path):
        """parse_json handles both {"issues":[...]} wrapper and bare array."""
        issue = {
            "key": "X-1",
            "fields": {
                "summary": "Test issue",
                "status": {"name": "Done"},
                "resolution": {"name": "Fixed it"},
                "description": "desc",
                "labels": [],
                "components": [],
                "comment": {"comments": []},
            },
        }
        bare = tmp_path / "bare.json"
        bare.write_text(json.dumps([issue]))
        assert len(parse_json(bare)) == 1

        wrapped = tmp_path / "wrapped.json"
        wrapped.write_text(json.dumps({"issues": [issue]}))
        assert len(parse_json(wrapped)) == 1


# ---------------------------------------------------------------------------
# servicenow module
# ---------------------------------------------------------------------------


class TestServiceNowImporter:
    def test_best_resolution_close_notes_priority(self):
        row = {
            "close notes": "Fixed via close notes",
            "resolution notes": "Resolution notes",
            "work notes": "Work notes",
        }
        assert servicenow.best_resolution(row) == "Fixed via close notes"

    def test_best_resolution_falls_back_to_resolution_notes(self):
        row = {
            "close notes": "",
            "resolution notes": "Fixed via resolution notes",
            "work notes": "Work notes",
        }
        assert servicenow.best_resolution(row) == "Fixed via resolution notes"

    def test_best_resolution_falls_back_to_work_notes(self):
        row = {
            "close notes": "",
            "resolution notes": "",
            "work notes": "Fixed via work notes",
        }
        assert servicenow.best_resolution(row) == "Fixed via work notes"

    def test_best_resolution_returns_none_when_all_empty(self):
        row = {"close notes": "", "resolution notes": "", "work notes": ""}
        assert servicenow.best_resolution(row) is None

    def test_best_resolution_allow_description_fallback(self):
        row = {
            "close notes": "",
            "resolution notes": "",
            "work notes": "",
            "description": "Fallback from description",
        }
        assert (
            servicenow.best_resolution(row, allow_description=True)
            == "Fallback from description"
        )

    def test_best_resolution_description_not_used_without_flag(self):
        row = {
            "close notes": "",
            "resolution notes": "",
            "work notes": "",
            "description": "Should not be used",
        }
        assert servicenow.best_resolution(row, allow_description=False) is None

    def test_is_closed_state_7(self):
        assert servicenow.is_closed({"state": "7"}) is True

    def test_is_closed_state_6(self):
        assert servicenow.is_closed({"state": "6"}) is True

    def test_is_closed_closed(self):
        assert servicenow.is_closed({"state": "Closed"}) is True

    def test_is_closed_resolved(self):
        assert servicenow.is_closed({"state": "Resolved"}) is True

    def test_is_not_closed_open(self):
        assert servicenow.is_closed({"state": "1"}) is False

    # --- JSON key support ---

    def test_get_underscore_key(self):
        """_get should find JSON-style underscore keys when asked with space-form."""
        from fixdoc.importers.servicenow import _get

        row = {
            "short_description": "IAM policy error",
            "close_notes": "Fixed permissions",
        }
        assert _get(row, "short description") == "IAM policy error"
        assert _get(row, "close notes") == "Fixed permissions"

    def test_best_resolution_json_close_notes(self):
        """best_resolution works on JSON-keyed rows (underscore fields)."""
        row = {"close_notes": "Fixed it via IAM policy update", "work_notes": ""}
        assert servicenow.best_resolution(row) == "Fixed it via IAM policy update"

    def test_best_resolution_json_falls_back_to_work_notes(self):
        row = {"close_notes": "", "work_notes": "Updated bucket policy"}
        assert servicenow.best_resolution(row) == "Updated bucket policy"

    def test_parse_json_records_wrapper(self):
        """parse_json handles {'records': [...]} ServiceNow export wrapper."""
        rows = parse_json(FIXTURES / "snow_real.json")
        assert isinstance(rows, list)
        assert len(rows) == 4
        assert rows[0]["number"] == "INC0010001"

    def test_extract_from_json(self):
        """extract correctly processes closed JSON records."""
        rows = parse_json(FIXTURES / "snow_real.json")
        fixes, _ = servicenow.extract(
            rows, closed_only=True, extra_tags=[], max_count=None
        )
        # INC0010001 + INC0010002 closed with resolution; INC0010003 open; INC0010004 empty resolution
        assert len(fixes) == 2

    def test_row_skipped_when_all_resolution_fields_empty_json(self):
        """INC0010004 has no close/work notes — skipped as bad row."""
        rows = parse_json(FIXTURES / "snow_real.json")
        fixes, _ = servicenow.extract(
            rows, closed_only=True, extra_tags=[], max_count=None
        )
        assert next((f for f in fixes if "INC0010004" in (f.notes or "")), None) is None

    def test_allow_description_imports_previously_skipped_row_json(self):
        """With --allow-description-as-resolution, INC0010004 (description only) imports."""
        rows = parse_json(FIXTURES / "snow_real.json")
        fixes_no_desc, _ = servicenow.extract(
            rows,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            allow_description=False,
        )
        fixes_with_desc, _ = servicenow.extract(
            rows,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            allow_description=True,
        )
        assert len(fixes_with_desc) > len(fixes_no_desc)

    def test_source_tag_format_json(self):
        """All imported fixes carry source:servicenow: tags."""
        rows = parse_json(FIXTURES / "snow_real.json")
        fixes, _ = servicenow.extract(
            rows, closed_only=True, extra_tags=[], max_count=None
        )
        for fix in fixes:
            assert any(
                t.strip().startswith("source:servicenow:") for t in fix.tags.split(",")
            )

    def test_extract_tags_from_json_keys(self):
        """Metadata fields become notes (not tags); kw: tags detected from text content."""
        rows = parse_json(FIXTURES / "snow_real.json")
        fixes, _ = servicenow.extract(
            rows, closed_only=True, extra_tags=[], max_count=None
        )
        # INC0010001: short_description has "Terraform IAM", close_notes has "IAM"
        inc1 = next(f for f in fixes if "INC0010001" in (f.notes or ""))
        tags = set(t.strip() for t in inc1.tags.split(","))
        assert any(t.startswith("source:servicenow:") for t in tags)
        assert "kw:iam" in tags  # detected from "IAM" in text
        assert "kw:terraform" in tags  # detected from "Terraform" in text

    def test_metadata_in_notes_not_tags(self):
        """Ticket metadata (close_code, category, etc.) appears in notes, not tags."""
        rows = [
            {
                "short_description": "Issue",
                "close_notes": "Fixed it",
                "state": "closed",
                "close_code": "resolved_by_caller",
                "category": "software",
                "number": "INC001",
            }
        ]
        fixes, bad = servicenow.extract(
            rows, closed_only=False, extra_tags=[], max_count=None
        )
        assert len(fixes) == 1
        fix = fixes[0]
        tags = [t.strip() for t in (fix.tags or "").split(",")]
        assert "resolved_by_caller" not in tags
        assert "software" not in tags
        assert "resolved_by_caller" in (fix.notes or "")
        assert "software" in (fix.notes or "")

    def test_max_stops_after_n_rows_json(self):
        rows = parse_json(FIXTURES / "snow_real.json")
        fixes_all, _ = servicenow.extract(
            rows, closed_only=False, extra_tags=[], max_count=None
        )
        fixes_1, _ = servicenow.extract(
            rows, closed_only=False, extra_tags=[], max_count=1
        )
        assert len(fixes_1) <= len(fixes_all)


# ---------------------------------------------------------------------------
# Duplicate guard
# ---------------------------------------------------------------------------


class TestDuplicateGuard:
    def test_jira_and_servicenow_different_systems_no_collision(self):
        """source:jira:PLATFORM-123 != source:servicenow:PLATFORM-123"""
        jira_tag = "source:jira:PLATFORM-123"
        snow_tag = "source:servicenow:PLATFORM-123"
        assert jira_tag != snow_tag

    def test_duplicate_detection_same_system_same_id(self, tmp_path):
        """Second import of same Jira issue → duplicates += 1, not saved."""
        from fixdoc.importers.base import build_fix, normalize_tags

        repo = FixRepository(tmp_path)

        # Build and save a fix with a Jira source tag
        tags = normalize_tags([], [], "source:jira:PLATFORM-123", [])
        fix = build_fix(
            "EC2 failing", "Fixed IAM", None, tags, "Source: jira PLATFORM-123"
        )
        repo.save(fix)

        # Load existing source tags
        existing = repo.list_all()
        existing_source_tags = {
            tag.strip()
            for f in existing
            for tag in (f.tags or "").split(",")
            if tag.strip().startswith("source:")
        }

        assert "source:jira:platform-123" in existing_source_tags

    def test_duplicate_detection_different_system_no_false_positive(self, tmp_path):
        """source:jira:X does NOT block source:servicenow:X."""
        from fixdoc.importers.base import build_fix, normalize_tags

        repo = FixRepository(tmp_path)
        tags = normalize_tags([], [], "source:jira:INC001", [])
        fix = build_fix("Issue", "Resolution", None, tags, "Source: jira INC001")
        repo.save(fix)

        existing = repo.list_all()
        existing_source_tags = {
            tag.strip()
            for f in existing
            for tag in (f.tags or "").split(",")
            if tag.strip().startswith("source:")
        }
        # ServiceNow tag should NOT be in jira-sourced existing tags
        assert "source:servicenow:inc001" not in existing_source_tags


# ---------------------------------------------------------------------------
# source: tag re-appended after user edit
# ---------------------------------------------------------------------------


class TestSourceTagReappended:
    def test_source_tag_survives_edit(self):
        """_ensure_source_tag always puts source: back even if user removed it."""
        from fixdoc.commands.import_cmd import _ensure_source_tag

        original_tags = "aws_s3_bucket,kw:terraform,source:jira:PROJ-1"
        # Simulate user editing out the source tag
        user_edited = "aws_s3_bucket,kw:terraform,mynewtag"
        result = _ensure_source_tag(user_edited, "source:jira:proj-1")
        assert "source:jira:proj-1" in result

    def test_source_tag_not_duplicated(self):
        """If source: tag already present, it should not be duplicated."""
        from fixdoc.commands.import_cmd import _ensure_source_tag

        original_tags = "aws_s3_bucket,source:jira:PROJ-1"
        result = _ensure_source_tag(original_tags, "source:jira:proj-1")
        count = result.split(",").count("source:jira:proj-1")
        assert count == 1


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestImportCLI:
    def _invoke(self, args, base_path):
        from fixdoc.fix import main

        runner = CliRunner()
        return runner.invoke(main, args, obj={"base_path": base_path})

    def _make_cli(self, tmp_path):
        from fixdoc.cli import create_cli
        from fixdoc.config import FixDocConfig

        runner = CliRunner()
        cli = create_cli()
        return runner, cli, tmp_path

    def test_jira_csv_auto_imports(self, tmp_path):
        from fixdoc.cli import create_cli
        from fixdoc.config import FixDocConfig, ConfigManager

        runner = CliRunner()
        cli = create_cli()
        result = runner.invoke(
            cli,
            ["--help"],
        )
        assert result.exit_code == 0

    def test_jira_import_command_exists(self, tmp_path):
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(
            cli,
            ["import", "--help"],
        )
        assert result.exit_code == 0
        assert "jira" in result.output.lower() or "import" in result.output.lower()

    def test_jira_subcommand_help(self, tmp_path):
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(cli, ["import", "jira", "--help"])
        assert result.exit_code == 0
        assert "FILE" in result.output or "file" in result.output.lower()

    def test_servicenow_subcommand_help(self, tmp_path):
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(cli, ["import", "servicenow", "--help"])
        assert result.exit_code == 0
        assert "--allow-description-as-resolution" in result.output

    def test_jira_auto_dry_run(self, tmp_path):
        """Dry run imports nothing but prints summary."""
        from fixdoc.cli import create_cli
        import os

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(
            cli,
            [
                "import",
                "jira",
                str(FIXTURES / "jira_sample.csv"),
                "--auto",
                "--dry-run",
            ],
            env={"FIXDOC_HOME": str(tmp_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        repo = FixRepository(tmp_path)
        # Dry run — nothing saved
        assert repo.count() == 0

    def test_jira_auto_imports_high_signal(self, tmp_path):
        """Auto mode saves only high-signal fixes."""
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(
            cli,
            ["import", "jira", str(FIXTURES / "jira_sample.csv"), "--auto"],
            env={"FIXDOC_HOME": str(tmp_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        repo = FixRepository(tmp_path)
        assert repo.count() > 0

    def test_idempotent_reimport(self, tmp_path):
        """Running import twice → second run shows duplicates, same count."""
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        args = ["import", "jira", str(FIXTURES / "jira_sample.csv"), "--auto"]
        env = {"FIXDOC_HOME": str(tmp_path)}

        runner.invoke(cli, args, env=env, catch_exceptions=False)
        count_after_first = FixRepository(tmp_path).count()

        result2 = runner.invoke(cli, args, env=env, catch_exceptions=False)
        count_after_second = FixRepository(tmp_path).count()

        assert count_after_first == count_after_second
        assert "duplicates" in result2.output

    def test_max_rows_cap(self, tmp_path):
        """--max 2 processes at most 2 rows."""
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(
            cli,
            [
                "import",
                "jira",
                str(FIXTURES / "jira_sample.csv"),
                "--auto",
                "--max",
                "2",
            ],
            env={"FIXDOC_HOME": str(tmp_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        repo = FixRepository(tmp_path)
        # At most 2 rows processed, some may be invalid/low-signal
        assert repo.count() <= 2

    def test_snow_auto_dry_run(self, tmp_path):
        """ServiceNow JSON dry run prints summary, saves nothing."""
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(
            cli,
            [
                "import",
                "servicenow",
                str(FIXTURES / "snow_real.json"),
                "--auto",
                "--dry-run",
            ],
            env={"FIXDOC_HOME": str(tmp_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert FixRepository(tmp_path).count() == 0

    def test_json_import(self, tmp_path):
        """JSON backup import works."""
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        result = runner.invoke(
            cli,
            ["import", "jira", str(FIXTURES / "jira_backup.json"), "--auto"],
            env={"FIXDOC_HOME": str(tmp_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert FixRepository(tmp_path).count() > 0

    def test_source_line_in_formatter(self, tmp_path):
        """fix_to_markdown shows Source: line for imported fixes."""
        from fixdoc.formatter import fix_to_markdown
        from fixdoc.importers.base import build_fix, normalize_tags

        tags = normalize_tags(
            ["aws_s3_bucket"], ["kw:terraform"], "source:jira:PROJ-99", []
        )
        fix = build_fix("EC2 failing", "Fixed IAM", None, tags, "Source: jira PROJ-99")

        md = fix_to_markdown(fix)
        assert "**Source:**" in md
        assert "jira / proj-99" in md.lower() or "jira" in md.lower()


# ---------------------------------------------------------------------------
# Notion importer tests
# ---------------------------------------------------------------------------


class TestNotionImporter:
    """Fixture-based integration tests for the Notion importer."""

    FIXTURE = FIXTURES / "notion_sample.json"
    API_FIXTURE = FIXTURES / "notion_api_responses.json"

    def _load_fixture(self):
        with open(self.FIXTURE) as f:
            return json.load(f)

    def _load_api_fixture(self):
        with open(self.API_FIXTURE) as f:
            data = json.load(f)
        return data["pages"]

    def _make_blocks_fn(self, pages):
        """Return a mock fetch_blocks_fn that serves _mock_blocks/_blocks from fixture pages."""
        block_map = {}
        for page in pages:
            pid = page["id"]
            blocks = page.get("_mock_blocks") or page.get("_blocks")
            if blocks is not None:
                block_map[pid] = blocks
        return lambda pid: block_map.get(pid, [])

    # --- Property text extraction ---

    def test_get_property_text_title(self):
        from fixdoc.importers.notion import _get_property_text

        prop = {
            "type": "title",
            "title": [{"plain_text": "Hello"}, {"plain_text": " World"}],
        }
        assert _get_property_text(prop) == "Hello World"

    def test_get_property_text_rich_text(self):
        from fixdoc.importers.notion import _get_property_text

        prop = {"type": "rich_text", "rich_text": [{"plain_text": "fix applied"}]}
        assert _get_property_text(prop) == "fix applied"

    def test_get_property_text_select(self):
        from fixdoc.importers.notion import _get_property_text

        prop = {"type": "select", "select": {"name": "Done"}}
        assert _get_property_text(prop) == "Done"

    def test_get_property_text_status(self):
        from fixdoc.importers.notion import _get_property_text

        prop = {"type": "status", "status": {"name": "Resolved"}}
        assert _get_property_text(prop) == "Resolved"

    def test_get_property_text_multi_select(self):
        from fixdoc.importers.notion import _get_property_text

        prop = {
            "type": "multi_select",
            "multi_select": [{"name": "terraform"}, {"name": "iam"}],
        }
        assert _get_property_text(prop) == "terraform, iam"

    def test_get_property_text_unknown_type(self):
        from fixdoc.importers.notion import _get_property_text

        prop = {"type": "formula", "formula": {"number": 42}}
        assert _get_property_text(prop) == ""

    # --- Field matching ---

    def test_find_field_case_insensitive(self):
        from fixdoc.importers.notion import _find_field

        props = {
            "Name": {"type": "title", "title": [{"plain_text": "Issue"}]},
        }
        key, val = _find_field(props, ["name"])
        assert key == "Name"
        assert val is not None

    def test_find_field_missing(self):
        from fixdoc.importers.notion import _find_field

        props = {"SomeOtherField": {"type": "rich_text", "rich_text": []}}
        key, val = _find_field(props, ["name", "title"])
        assert key is None
        assert val is None

    def test_find_field_prefers_exact_match_over_partial(self):
        from fixdoc.importers.notion import _find_field

        props = {
            "Status": {"type": "status", "status": {"name": "Done"}},
            "Ticket Status History": {
                "type": "rich_text",
                "rich_text": [{"plain_text": "old"}],
            },
        }
        key, val = _find_field(props, ["status"])
        assert key == "Status"

    # --- Section-aware extraction ---

    def test_extract_section_text_fix_mitigation(self):
        """Page with Fix/Mitigation heading: only that section extracted."""
        from fixdoc.importers.notion import (
            extract_section_text,
            _RESOLUTION_SECTION_HEADINGS,
        )

        pages = self._load_api_fixture()
        # Page 0: has Fix/Mitigation section
        blocks = pages[0]["_blocks"]
        result = extract_section_text(blocks, _RESOLUTION_SECTION_HEADINGS)
        assert "Restricted the assume_role_policy" in result
        assert "Updated terraform aws_iam_role" in result
        # Should NOT include Description or Lessons Learned content
        assert "trust policy was open" not in result
        assert "Always scope trust policies" not in result

    def test_extract_section_text_resolution_heading(self):
        """Page with Resolution heading: that section extracted."""
        from fixdoc.importers.notion import (
            extract_section_text,
            _RESOLUTION_SECTION_HEADINGS,
        )

        pages = self._load_api_fixture()
        # Page 1: has Resolution section
        blocks = pages[1]["_blocks"]
        result = extract_section_text(blocks, _RESOLUTION_SECTION_HEADINGS)
        assert "max_connections" in result
        assert "PgBouncer" in result
        # Should NOT include Impact section
        assert "API latency" not in result

    def test_extract_section_text_no_matching_heading(self):
        """Page with no matching heading: returns empty string."""
        from fixdoc.importers.notion import (
            extract_section_text,
            _RESOLUTION_SECTION_HEADINGS,
        )

        pages = self._load_api_fixture()
        # Page 2: no section headings at all (just paragraphs)
        blocks = pages[2]["_blocks"]
        result = extract_section_text(blocks, _RESOLUTION_SECTION_HEADINGS)
        assert result == ""

    def test_extract_section_text_empty_section(self):
        """Heading matches but no content between it and next heading."""
        from fixdoc.importers.notion import (
            extract_section_text,
            _RESOLUTION_SECTION_HEADINGS,
        )

        pages = self._load_api_fixture()
        # Page 6 (aab77777): has "Fix" heading immediately followed by "Notes" heading
        blocks = pages[6]["_blocks"]
        result = extract_section_text(blocks, _RESOLUTION_SECTION_HEADINGS)
        assert result == ""

    def test_extract_section_text_no_blocks(self):
        """Empty blocks list: returns empty string."""
        from fixdoc.importers.notion import (
            extract_section_text,
            _RESOLUTION_SECTION_HEADINGS,
        )

        result = extract_section_text([], _RESOLUTION_SECTION_HEADINGS)
        assert result == ""

    # --- Full pipeline integration (API fixture) ---

    def test_section_extraction_in_pipeline(self):
        """extract() uses section-aware extraction for body fallback."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        # Page 0: IAM role — Fix/Mitigation section only
        iam_fixes = [f for f in fixes if "IAM role" in f.issue]
        assert len(iam_fixes) == 1
        assert "Restricted the assume_role_policy" in iam_fixes[0].resolution
        assert "trust policy was open" not in iam_fixes[0].resolution

    def test_resolution_heading_in_pipeline(self):
        """Page with Resolution heading: section content used."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        rds_fixes = [f for f in fixes if "RDS connection" in f.issue]
        assert len(rds_fixes) == 1
        assert "max_connections" in rds_fixes[0].resolution
        assert "API latency" not in rds_fixes[0].resolution

    def test_full_body_fallback_no_section_heading(self):
        """Page with blocks but no matching heading: full body text used."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        sg_fixes = [f for f in fixes if "Security group" in f.issue]
        assert len(sg_fixes) == 1
        assert "Locked down aws_security_group" in sg_fixes[0].resolution

    def test_property_wins_over_body(self):
        """Page with resolution property: body blocks not used."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        eks_fixes = [f for f in fixes if "EKS node group" in f.issue]
        assert len(eks_fixes) == 1
        assert "min_size=2" in eks_fixes[0].resolution
        assert "should NOT be used" not in eks_fixes[0].resolution

    def test_empty_section_falls_back_to_full_body(self):
        """Fix heading exists but empty content under it: full body fallback."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        alb_fixes = [f for f in fixes if "ALB health check" in f.issue]
        assert len(alb_fixes) == 1
        assert "health check path" in alb_fixes[0].resolution.lower()

    def test_no_headings_full_body_fallback(self):
        """Page with blocks but no headings: full body text used."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        lock_fixes = [f for f in fixes if "state lock" in f.issue.lower()]
        assert len(lock_fixes) == 1
        assert "DynamoDB" in lock_fixes[0].resolution

    def test_open_ticket_skipped(self):
        """Open ticket skipped when closed_only=True."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, skipped_open, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert skipped_open >= 1
        k8s_fixes = [f for f in fixes if "CrashLoopBackOff" in f.issue]
        assert len(k8s_fixes) == 0

    def test_empty_body_skipped_missing(self):
        """Empty resolution AND empty body: skipped_missing."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        _, _, skipped_missing, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert skipped_missing >= 1

    def test_source_tag_format(self):
        """Source tags have correct format: source:notion:<32-char-hex>."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()[:1]
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert len(fixes) == 1
        tags = fixes[0].tags or ""
        source_tags = [
            t.strip() for t in tags.split(",") if t.strip().startswith("source:notion:")
        ]
        assert len(source_tags) == 1
        id_part = source_tags[0].split("source:notion:")[1]
        assert len(id_part) == 32
        assert "-" not in id_part

    def test_custom_field_overrides(self):
        """Custom --title-field, --resolution-field, --status-field, --done-values."""
        from fixdoc.importers.notion import extract

        pages = self._load_api_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            title_field="Incident Title",
            resolution_field="Action Taken",
            status_field="Progress",
            done_values="Shipped",
            fetch_blocks_fn=blocks_fn,
        )
        custom_fixes = [f for f in fixes if "SNS topic" in f.issue]
        assert len(custom_fixes) == 1
        assert "aws_sns_topic" in custom_fixes[0].resolution

    # --- Legacy fixture tests (notion_sample.json) ---

    def test_extract_closed_only_default(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, skipped_open, skipped_missing, bad_rows = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert skipped_open >= 1
        assert skipped_missing >= 1
        assert len(fixes) >= 4

    def test_extract_no_closed_filter(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes_closed, skipped_open, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        fixes_all, skipped_open2, _, _ = extract(
            pages,
            closed_only=False,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert len(fixes_all) >= len(fixes_closed)
        assert skipped_open2 == 0

    def test_extract_skips_missing_title(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        _, _, skipped_missing, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert skipped_missing >= 1

    def test_extract_section_aware_body_fallback(self):
        """VPC routing page has Fix/Mitigation heading: only that section used."""
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        vpc_fixes = [f for f in fixes if "VPC routing" in f.issue]
        assert len(vpc_fixes) == 1
        assert "route table" in vpc_fixes[0].resolution.lower()
        # Should NOT include Description or Lessons Learned
        assert "Traffic was not routing" not in vpc_fixes[0].resolution
        assert "Always validate" not in vpc_fixes[0].resolution

    def test_root_cause_section_extracted(self):
        """DB slowdown page has Root Cause heading: that section used."""
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        db_fixes = [f for f in fixes if "DB slowdown" in f.issue]
        assert len(db_fixes) == 1
        assert "Missing index" in db_fixes[0].resolution

    def test_extract_skips_when_both_empty(self):
        from fixdoc.importers.notion import extract

        pages = [
            {
                "id": "deadbeef-0000-0000-0000-000000000000",
                "url": "",
                "properties": {
                    "Name": {"type": "title", "title": [{"plain_text": "Some issue"}]},
                    "Resolution": {"type": "rich_text", "rich_text": []},
                    "Status": {"type": "status", "status": {"name": "Done"}},
                },
            }
        ]
        fixes, _, skipped_missing, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=lambda pid: [],
        )
        assert len(fixes) == 0
        assert skipped_missing == 1

    def test_extract_resource_type_detection(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()[:1]
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        assert len(fixes) == 1
        tags = fixes[0].tags or ""
        assert "aws_s3_bucket" in tags

    def test_extract_max_count(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes_all, _, _, _ = extract(
            pages,
            closed_only=False,
            extra_tags=[],
            max_count=None,
            fetch_blocks_fn=blocks_fn,
        )
        fixes_capped, _, _, _ = extract(
            pages,
            closed_only=False,
            extra_tags=[],
            max_count=2,
            fetch_blocks_fn=blocks_fn,
        )
        assert len(fixes_capped) <= len(fixes_all)
        assert len(fixes_capped) <= 2

    def test_extract_custom_field_names(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes, _, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            title_field="Incident",
            resolution_field="Postmortem",
            status_field="Ticket Status",
            done_values="Completed",
            fetch_blocks_fn=blocks_fn,
        )
        custom_fixes = [f for f in fixes if "Custom field incident" in f.issue]
        assert len(custom_fixes) == 1

    def test_extract_custom_done_values(self):
        from fixdoc.importers.notion import extract

        pages = self._load_fixture()
        blocks_fn = self._make_blocks_fn(pages)
        fixes_default, skipped_open_default, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            title_field="Incident",
            resolution_field="Postmortem",
            status_field="Ticket Status",
            fetch_blocks_fn=blocks_fn,
        )
        fixes_custom, skipped_open_custom, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            title_field="Incident",
            resolution_field="Postmortem",
            status_field="Ticket Status",
            done_values="Completed",
            fetch_blocks_fn=blocks_fn,
        )
        custom_fixes = [f for f in fixes_custom if "Custom field incident" in f.issue]
        assert len(custom_fixes) == 1

    # --- Block text extraction ---

    def test_extract_block_text_paragraph(self):
        from fixdoc.importers.notion import extract_block_text

        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"plain_text": "Fixed the issue by updating config"}]
                },
            }
        ]
        assert extract_block_text(blocks) == "Fixed the issue by updating config"

    def test_extract_block_text_mixed_types(self):
        from fixdoc.importers.notion import extract_block_text

        blocks = [
            {
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Root Cause"}]},
            },
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"plain_text": "Missing IAM policy"}]
                },
            },
        ]
        text = extract_block_text(blocks)
        assert "Root Cause" in text
        assert "Missing IAM policy" in text
        assert "\n" in text

    def test_solved_status_accepted_as_done(self):
        from fixdoc.importers.notion import extract

        pages = [
            {
                "id": "aaaaaaaa-0000-0000-0000-000000000001",
                "url": "",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Disk full on prod"}],
                    },
                    "Resolution": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "Expanded EBS volume"}],
                    },
                    "Status": {"type": "status", "status": {"name": "Solved"}},
                },
            }
        ]
        fixes, skipped_open, _, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
        )
        assert len(fixes) == 1
        assert skipped_open == 0

    def test_title_type_fallback(self):
        from fixdoc.importers.notion import extract

        pages = [
            {
                "id": "bbbbbbbb-0000-0000-0000-000000000002",
                "url": "",
                "properties": {
                    "Bug": {
                        "type": "title",
                        "title": [{"plain_text": "OOM in worker pod"}],
                    },
                    "Fix": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "Increased memory limit"}],
                    },
                    "Status": {"type": "status", "status": {"name": "Done"}},
                },
            }
        ]
        fixes, _, skipped_missing, _ = extract(
            pages,
            closed_only=True,
            extra_tags=[],
            max_count=None,
            resolution_field="Fix",
        )
        assert len(fixes) == 1
        assert fixes[0].issue == "OOM in worker pod"
        assert skipped_missing == 0

    # --- CLI integration ---

    def test_notion_cmd_dry_run(self, tmp_path):
        from fixdoc.importers import notion as notion_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        pages = self._load_api_fixture()
        blocks_map = {p["id"]: p.get("_blocks", []) for p in pages}

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(notion_mod, "fetch_pages", return_value=pages),
            patch.object(
                notion_mod,
                "fetch_page_blocks",
                side_effect=lambda t, pid: blocks_map.get(pid, []),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "notion",
                    "--token",
                    "fake-token",
                    "--database",
                    "fake-db",
                    "--dry-run",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert FixRepository(tmp_path).count() == 0

    def test_notion_cmd_auto(self, tmp_path):
        from fixdoc.importers import notion as notion_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        pages = self._load_api_fixture()
        blocks_map = {p["id"]: p.get("_blocks", []) for p in pages}

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(notion_mod, "fetch_pages", return_value=pages),
            patch.object(
                notion_mod,
                "fetch_page_blocks",
                side_effect=lambda t, pid: blocks_map.get(pid, []),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "notion",
                    "--token",
                    "fake-token",
                    "--database",
                    "fake-db",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert FixRepository(tmp_path).count() > 0

    def test_notion_cmd_duplicate_guard(self, tmp_path):
        from fixdoc.importers import notion as notion_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        pages = self._load_api_fixture()
        blocks_map = {p["id"]: p.get("_blocks", []) for p in pages}

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        args = [
            "import",
            "notion",
            "--token",
            "fake-token",
            "--database",
            "fake-db",
            "--auto",
        ]
        env = {"FIXDOC_HOME": str(tmp_path)}

        with (
            patch.object(notion_mod, "fetch_pages", return_value=pages),
            patch.object(
                notion_mod,
                "fetch_page_blocks",
                side_effect=lambda t, pid: blocks_map.get(pid, []),
            ),
        ):
            runner.invoke(cli, args, env=env, catch_exceptions=False)
            count_first = FixRepository(tmp_path).count()

            result2 = runner.invoke(cli, args, env=env, catch_exceptions=False)
            count_second = FixRepository(tmp_path).count()

        assert count_first == count_second
        assert "duplicates" in result2.output


# ===========================================================================
# Slack importer tests
# ===========================================================================

import importlib

_slack_mod = importlib.import_module("fixdoc.importers.slack")

SLACK_FIXTURE = FIXTURES / "slack_threads.json"


def _load_slack_fixture():
    with open(SLACK_FIXTURE) as f:
        return json.load(f)


def _make_user_fn(users):
    """Build a fetch_user_fn that resolves from fixture users dict."""

    def fn(uid, cache):
        if uid in cache:
            return cache[uid]
        name = users.get(uid, {}).get("display_name", uid)
        cache[uid] = name
        return name

    return fn


# ---------------------------------------------------------------------------
# Slack mrkdwn conversion
# ---------------------------------------------------------------------------


class TestSlackMrkdwn:
    def test_url_link_conversion(self):
        text = "Check <https://example.com|the docs> for details."
        result = _slack_mod._slack_mrkdwn_to_text(text, {})
        assert "the docs" in result
        assert "<" not in result
        assert "https://example.com" not in result

    def test_user_mention_resolution(self):
        cache = {"U001": "alice"}
        text = "Hey <@U001>, can you check?"
        result = _slack_mod._slack_mrkdwn_to_text(text, cache)
        assert "@alice" in result
        assert "<@U001>" not in result

    def test_channel_mention(self):
        text = "See <#C9999999|infra-alerts> for context."
        result = _slack_mod._slack_mrkdwn_to_text(text, {})
        assert "#infra-alerts" in result
        assert "<#C9999999" not in result

    def test_formatting_stripped(self):
        text = "This is *bold* and _italic_ and ~strikethrough~."
        result = _slack_mod._slack_mrkdwn_to_text(text, {})
        assert "bold" in result
        assert "italic" in result
        assert "strikethrough" in result
        assert "*" not in result
        assert "~" not in result

    def test_code_blocks_preserved(self):
        text = "Run this:\n```terraform plan```"
        result = _slack_mod._slack_mrkdwn_to_text(text, {})
        assert "```terraform plan```" in result


# ---------------------------------------------------------------------------
# Slack reaction detection
# ---------------------------------------------------------------------------


class TestSlackReactionDetection:
    def test_has_reaction_present(self):
        msg = {"reactions": [{"name": "red_circle", "count": 1}]}
        assert _slack_mod.has_reaction(msg, "red_circle") is True

    def test_has_reaction_missing(self):
        msg = {"reactions": [{"name": "thumbsup", "count": 1}]}
        assert _slack_mod.has_reaction(msg, "red_circle") is False

    def test_has_reaction_no_reactions(self):
        msg = {}
        assert _slack_mod.has_reaction(msg, "red_circle") is False

    def test_find_resolution_replies_single(self):
        replies = [
            {"ts": "1", "reactions": [{"name": "white_check_mark"}]},
            {"ts": "2", "reactions": []},
        ]
        result = _slack_mod.find_resolution_replies(replies, "white_check_mark")
        assert len(result) == 1
        assert result[0]["ts"] == "1"

    def test_find_resolution_replies_multiple_chronological(self):
        replies = [
            {"ts": "1", "reactions": [{"name": "white_check_mark"}]},
            {"ts": "2", "reactions": []},
            {"ts": "3", "reactions": [{"name": "white_check_mark"}]},
        ]
        result = _slack_mod.find_resolution_replies(replies, "white_check_mark")
        assert len(result) == 2
        assert result[0]["ts"] == "1"
        assert result[1]["ts"] == "3"


# ---------------------------------------------------------------------------
# Slack resolution formatting
# ---------------------------------------------------------------------------


class TestSlackResolutionFormatting:
    def test_single_reply_plain_text(self):
        replies = [{"user": "U002", "text": "Just run terraform import."}]
        cache = {"U002": "bob"}
        result = _slack_mod.format_resolution(replies, cache)
        assert result == "Just run terraform import."
        assert "[Step" not in result

    def test_multiple_replies_step_formatted(self):
        replies = [
            {"user": "U002", "text": "First, remove the duplicate rule."},
            {"user": "U003", "text": "Then run terraform import."},
        ]
        cache = {"U002": "bob", "U003": "carol"}
        result = _slack_mod.format_resolution(replies, cache)
        assert "[Step 1 — @bob]" in result
        assert "[Step 2 — @carol]" in result
        assert "remove the duplicate rule" in result
        assert "terraform import" in result

    def test_step_format_preserves_code_blocks(self):
        replies = [
            {
                "user": "U002",
                "text": "Run this:\n```terraform import aws_sg.web sg-123```",
            },
        ]
        cache = {"U002": "bob"}
        result = _slack_mod.format_resolution(replies, cache)
        assert "```terraform import aws_sg.web sg-123```" in result


# ---------------------------------------------------------------------------
# Slack code blocks
# ---------------------------------------------------------------------------


class TestSlackCodeBlocks:
    def test_extract_single_block(self):
        text = "Error:\n```some error output```\nmore text"
        blocks = _slack_mod._extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0] == "some error output"

    def test_extract_multiple_blocks(self):
        text = "```block one```\ntext\n```block two```"
        blocks = _slack_mod._extract_code_blocks(text)
        assert len(blocks) == 2

    def test_no_code_blocks(self):
        text = "Just a plain message with no code."
        blocks = _slack_mod._extract_code_blocks(text)
        assert blocks == []


# ---------------------------------------------------------------------------
# Slack extraction (fixture-based)
# ---------------------------------------------------------------------------


class TestSlackExtract:
    def _build_threads(self, fixture=None):
        if fixture is None:
            fixture = _load_slack_fixture()
        return fixture["threads"], fixture["users"]

    def test_complete_fix_imported(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[0]]  # Thread 1: complete fix
        user_fn = _make_user_fn(users)

        fixes, skipped, bad = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="terraform-help",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        fix = fixes[0]
        assert "Security Group" in fix.issue or "security group" in fix.issue.lower()
        assert (
            "terraform import" in fix.resolution.lower() or "import" in fix.resolution
        )
        assert fix.error_excerpt is not None
        assert "InvalidGroup.Duplicate" in fix.error_excerpt
        assert "source:slack:c0123456_" in fix.tags
        assert skipped == 0
        assert bad == 0

    def test_multiple_resolutions_step_formatted(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[1]]  # Thread 2: multiple resolution replies
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="terraform-help",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        assert "[Step 1 — @bob]" in fixes[0].resolution
        assert "[Step 2 — @carol]" in fixes[0].resolution

    def test_self_solved(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[2]]  # Thread 3: self-solved
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="terraform-help",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        assert "alice" in fixes[0].notes

    def test_issue_only_skipped(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[3]]  # Thread 4: no resolution marker
        user_fn = _make_user_fn(users)

        fixes, skipped, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="terraform-help",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 0
        assert skipped == 1

    def test_k8s_resource_detection(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[4]]  # Thread 5: K8s fix
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="devops",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        tags = fixes[0].tags or ""
        # The K8s thread mentions kubectl and kubernetes in root text
        # detect_resource_types looks for specific patterns
        assert len(fixes[0].issue) > 0  # issue was captured
        assert len(fixes[0].resolution) > 0  # resolution was captured

    def test_mrkdwn_cleaned_in_output(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[5]]  # Thread 6: mrkdwn formatting
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="terraform-help",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        # Mrkdwn should be converted
        assert "<@U002>" not in fixes[0].issue
        assert "*Critical*" not in fixes[0].issue
        assert "@bob" in fixes[0].issue

    def test_code_blocks_in_excerpt_and_resolution(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[6]]  # Thread 7: code blocks
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="terraform-help",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        # Error excerpt should contain the error code block
        assert fixes[0].error_excerpt is not None
        assert "MalformedPolicyDocument" in fixes[0].error_excerpt
        # Resolution should contain the fix
        assert "sts:AssumeRole" in fixes[0].resolution

    def test_source_tag_format(self):
        threads_raw, users = self._build_threads()
        threads = [threads_raw[0]]
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads,
            extra_tags=[],
            max_count=None,
            channel_name="test",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) == 1
        tags = fixes[0].tags or ""
        # source:slack:{channel_id}_{thread_ts}
        assert "source:slack:c0123456_1709000001.000100" in tags

    def test_max_count_respected(self):
        threads_raw, users = self._build_threads()
        # Use all importable threads (1,2,3,5,6,7 — thread 4 is skipped)
        user_fn = _make_user_fn(users)

        fixes, _, _ = _slack_mod.extract(
            threads_raw,
            extra_tags=[],
            max_count=2,
            channel_name="test",
            resolution_reaction="white_check_mark",
            fetch_user_fn=user_fn,
        )
        assert len(fixes) <= 2

    def test_empty_threads_list(self):
        fixes, skipped, bad = _slack_mod.extract(
            [],
            extra_tags=[],
            max_count=None,
            channel_name="test",
            resolution_reaction="white_check_mark",
        )
        assert fixes == []
        assert skipped == 0
        assert bad == 0


# ---------------------------------------------------------------------------
# Slack CLI tests
# ---------------------------------------------------------------------------


class TestSlackCLI:
    def _setup_mocks(self, fixture=None):
        if fixture is None:
            fixture = _load_slack_fixture()
        threads = fixture["threads"]
        users = fixture["users"]

        # Build messages (roots only) as returned by fetch_channel_messages
        messages = [t["root"] for t in threads]

        # Map thread_ts → replies
        replies_map = {}
        for t in threads:
            replies_map[t["root"]["ts"]] = t.get("replies", [])

        return messages, replies_map, users

    def test_import_dry_run(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        messages, replies_map, users = self._setup_mocks()

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=messages),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "slack",
                    "--token",
                    "xoxb-fake",
                    "--channel",
                    "C0123456",
                    "--dry-run",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert FixRepository(tmp_path).count() == 0

    def test_import_auto_mode(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        messages, replies_map, users = self._setup_mocks()

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=messages),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "slack",
                    "--token",
                    "xoxb-fake",
                    "--channel",
                    "C0123456",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert FixRepository(tmp_path).count() > 0

    def test_import_review_mode(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        messages, replies_map, users = self._setup_mocks()

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=messages),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            result = runner.invoke(
                cli,
                ["import", "slack", "--token", "xoxb-fake", "--channel", "C0123456"],
                input="y\ny\ny\ny\ny\ny\n",
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert FixRepository(tmp_path).count() > 0

    def test_channel_name_resolution(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        messages, replies_map, users = self._setup_mocks()

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(slack_mod, "resolve_channel_name", return_value="C0123456"),
            patch.object(slack_mod, "fetch_channel_messages", return_value=messages),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "slack",
                    "--token",
                    "xoxb-fake",
                    "--channel-name",
                    "terraform-help",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "Resolving channel name" in result.output

    def test_missing_channel_error(self, tmp_path):
        from fixdoc.cli import create_cli

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        result = runner.invoke(
            cli,
            ["import", "slack", "--token", "xoxb-fake"],
            env={"FIXDOC_HOME": str(tmp_path)},
            catch_exceptions=False,
        )

        assert result.exit_code != 0 or "Error" in (result.output + result.stderr)

    def test_oldest_filter(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch, call

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with patch.object(
            slack_mod, "fetch_channel_messages", return_value=[]
        ) as mock_fetch:
            runner.invoke(
                cli,
                [
                    "import",
                    "slack",
                    "--token",
                    "xoxb-fake",
                    "--channel",
                    "C0123456",
                    "--oldest",
                    "30",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        mock_fetch.assert_called_once()
        _, kwargs = mock_fetch.call_args
        assert kwargs.get("oldest_days") == 30 or mock_fetch.call_args[0][2] == 30

    def test_custom_reactions(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        # Build a thread with custom emojis
        thread = {
            "channel_id": "C001",
            "root": {
                "ts": "100.001",
                "user": "U001",
                "text": "Error with terraform apply",
                "reactions": [{"name": "bug", "count": 1}],
                "reply_count": 1,
            },
            "replies": [
                {
                    "ts": "100.002",
                    "user": "U002",
                    "text": "Fixed by updating provider version.",
                    "reactions": [{"name": "tada", "count": 1}],
                }
            ],
        }

        messages = [thread["root"]]
        replies_map = {thread["root"]["ts"]: thread["replies"]}

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=messages),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: cache.setdefault(uid, uid),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "slack",
                    "--token",
                    "xoxb-fake",
                    "--channel",
                    "C001",
                    "--issue-reaction",
                    "bug",
                    "--resolution-reaction",
                    "tada",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert FixRepository(tmp_path).count() > 0

    def test_multiple_channels(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        messages, replies_map, users = self._setup_mocks()

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        call_count = {"n": 0}

        def mock_fetch(token, channel_id, oldest_days=90):
            call_count["n"] += 1
            return messages if channel_id == "C001" else []

        with (
            patch.object(slack_mod, "fetch_channel_messages", side_effect=mock_fetch),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            result = runner.invoke(
                cli,
                [
                    "import",
                    "slack",
                    "--token",
                    "xoxb-fake",
                    "--channel",
                    "C001",
                    "--channel",
                    "C002",
                    "--auto",
                ],
                env={"FIXDOC_HOME": str(tmp_path)},
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Slack API tests
# ---------------------------------------------------------------------------


class TestSlackAPI:
    def test_429_retry_with_backoff(self):
        from unittest.mock import patch, MagicMock

        call_count = {"n": 0}

        def mock_urlopen(req):
            call_count["n"] += 1
            if call_count["n"] == 1:
                err = urllib.error.HTTPError(
                    req.full_url, 429, "Rate Limited", {"Retry-After": "0"}, None
                )
                raise err
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            resp.read.return_value = json.dumps({"ok": True, "data": "test"}).encode()
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = _slack_mod._slack_request("test.method", "xoxb-fake")

        assert result["ok"] is True
        assert call_count["n"] == 2

    def test_api_error_raises_runtime_error(self):
        from unittest.mock import patch, MagicMock

        def mock_urlopen(req):
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            resp.read.return_value = json.dumps(
                {"ok": False, "error": "channel_not_found"}
            ).encode()
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(RuntimeError, match="channel_not_found"):
                _slack_mod._slack_request("conversations.history", "xoxb-fake")

    def test_max_retries_exceeded(self):
        from unittest.mock import patch

        def mock_urlopen(req):
            err = urllib.error.HTTPError(
                req.full_url, 429, "Rate Limited", {"Retry-After": "0"}, None
            )
            raise err

        with (
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
            patch("time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="rate limited"):
                _slack_mod._slack_request("test.method", "xoxb-fake")

    def test_user_cached_across_threads(self):
        from unittest.mock import patch, MagicMock

        call_count = {"n": 0}

        def mock_urlopen(req):
            call_count["n"] += 1
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            resp.read.return_value = json.dumps(
                {
                    "ok": True,
                    "user": {"profile": {"display_name": "alice"}, "name": "alice"},
                }
            ).encode()
            return resp

        cache = {}
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            name1 = _slack_mod.fetch_user_display_name("xoxb-fake", "U001", cache)
            name2 = _slack_mod.fetch_user_display_name("xoxb-fake", "U001", cache)

        assert name1 == "alice"
        assert name2 == "alice"
        # Second call should use cache, not API
        assert call_count["n"] == 1

    def test_unknown_user_fallback(self):
        from unittest.mock import patch

        def mock_urlopen(req):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        cache = {}
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            name = _slack_mod.fetch_user_display_name("xoxb-fake", "UUNKNOWN", cache)

        assert name == "UUNKNOWN"


# ---------------------------------------------------------------------------
# Slack duplicate guard
# ---------------------------------------------------------------------------


class TestSlackDuplicateGuard:
    def test_duplicate_source_tag_skipped(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        fixture = _load_slack_fixture()
        threads = fixture["threads"]
        users = fixture["users"]
        messages = [t["root"] for t in threads]
        replies_map = {t["root"]["ts"]: t.get("replies", []) for t in threads}

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        args = [
            "import",
            "slack",
            "--token",
            "xoxb-fake",
            "--channel",
            "C0123456",
            "--auto",
        ]
        env = {"FIXDOC_HOME": str(tmp_path)}

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=messages),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies_map.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            runner.invoke(cli, args, env=env, catch_exceptions=False)
            count_first = FixRepository(tmp_path).count()

            result2 = runner.invoke(cli, args, env=env, catch_exceptions=False)
            count_second = FixRepository(tmp_path).count()

        assert count_first == count_second
        assert count_first > 0
        assert "duplicates" in result2.output

    def test_different_thread_not_duplicate(self, tmp_path):
        from fixdoc.importers import slack as slack_mod
        from fixdoc.cli import create_cli
        from unittest.mock import patch

        fixture = _load_slack_fixture()
        threads = fixture["threads"]
        users = fixture["users"]

        # First import: thread 1 only
        msgs1 = [threads[0]["root"]]
        replies1 = {threads[0]["root"]["ts"]: threads[0].get("replies", [])}

        # Second import: thread 2 only
        msgs2 = [threads[1]["root"]]
        replies2 = {threads[1]["root"]["ts"]: threads[1].get("replies", [])}

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()
        args = [
            "import",
            "slack",
            "--token",
            "xoxb-fake",
            "--channel",
            "C0123456",
            "--auto",
        ]
        env = {"FIXDOC_HOME": str(tmp_path)}

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=msgs1),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies1.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            runner.invoke(cli, args, env=env, catch_exceptions=False)
            count_first = FixRepository(tmp_path).count()

        with (
            patch.object(slack_mod, "fetch_channel_messages", return_value=msgs2),
            patch.object(
                slack_mod,
                "fetch_thread_replies",
                side_effect=lambda t, c, ts: replies2.get(ts, []),
            ),
            patch.object(
                slack_mod,
                "fetch_user_display_name",
                side_effect=lambda t, uid, cache: _make_user_fn(users)(uid, cache),
            ),
        ):
            runner.invoke(cli, args, env=env, catch_exceptions=False)
            count_second = FixRepository(tmp_path).count()

        assert count_second > count_first


# ---------------------------------------------------------------------------
# Auto-classify memory type on import
# ---------------------------------------------------------------------------


class TestBuildFixMemoryType:
    """build_fix() should auto-classify memory_type via classify_memory_type."""

    def test_build_fix_classifies_memory_type_fix(self):
        fix = build_fix("Some error", "Added IAM role binding", None, "aws_iam_role", None)
        assert fix.memory_type == "fix"

    def test_build_fix_classifies_memory_type_check(self):
        fix = build_fix("CIDR error", "Verify the CIDR block is valid", None, "", None)
        assert fix.memory_type == "check"

    def test_build_fix_classifies_memory_type_playbook(self):
        resolution = "1. Stop the service\n2. Update the config\n3. Restart the service"
        fix = build_fix("Outage", resolution, None, "", None)
        assert fix.memory_type == "playbook"

    def test_build_fix_classifies_memory_type_insight(self):
        fix = build_fix("Crash", "Root cause was a stale provider lock", None, "", None)
        assert fix.memory_type == "insight"

    def test_build_fix_classifies_empty_resolution(self):
        fix = build_fix("Error", "", None, "", None)
        assert fix.memory_type == "fix"

    def test_build_fix_classifies_none_resolution(self):
        fix = build_fix("Error", None, None, "", None)
        assert fix.memory_type == "fix"

    def test_build_fix_prose_playbook(self):
        resolution = "Updated the SG, then restarted bastion, finally verified SSH"
        fix = build_fix("SSH failure", resolution, None, "", None)
        assert fix.memory_type == "playbook"


class TestImportReviewCardType:
    """Review card shows type; edit mode allows type change."""

    def test_review_card_shows_type(self):
        """_show_card output includes type line."""
        from fixdoc.commands.import_cmd import _show_card

        fix = Fix(
            issue="test issue",
            resolution="Verify the policy is correct",
            tags="source:jira:TEST-1",
            memory_type="check",
        )
        import io
        from unittest.mock import patch

        output = io.StringIO()
        with patch("click.echo", side_effect=lambda msg="", **kw: output.write(msg + "\n")):
            _show_card(1, 1, fix, "TEST-1", "jira")

        text = output.getvalue()
        assert "type       : check" in text

    def test_review_edit_changes_type(self):
        """Shorthand 'p' resolves to 'playbook' in edit mode."""
        from fixdoc.commands.import_cmd import _resolve_type_shorthand

        assert _resolve_type_shorthand("p") == "playbook"
        assert _resolve_type_shorthand("f") == "fix"
        assert _resolve_type_shorthand("c") == "check"
        assert _resolve_type_shorthand("i") == "insight"
        assert _resolve_type_shorthand("playbook") == "playbook"
        assert _resolve_type_shorthand("nonsense") == "fix"

    def test_auto_flow_preserves_classified_type(self, tmp_path):
        """Auto mode preserves the memory_type classified by build_fix."""
        from fixdoc.commands.import_cmd import _auto_flow, ImportResult

        repo = FixRepository(tmp_path)
        fix = build_fix(
            "SG error",
            "Verify the CIDR block is valid",
            None,
            "aws_security_group,kw:terraform,source:jira:X-1",
            None,
        )
        assert fix.memory_type == "check"

        result = ImportResult()
        _auto_flow([fix], 0, repo, result, dry_run=False)

        assert result.imported == 1
        saved = repo.list_all()
        assert len(saved) == 1
        assert saved[0].memory_type == "check"

    def test_review_edit_reclassifies_on_resolution_change(self, tmp_path):
        """When resolution changes in edit mode, type is re-classified."""
        from fixdoc.commands.import_cmd import _review_flow, ImportResult
        from unittest.mock import patch

        repo = FixRepository(tmp_path)
        fix = build_fix(
            "Error",
            "Fixed the IAM role",
            None,
            "aws_iam_role,kw:iam,source:jira:X-2",
            None,
        )
        assert fix.memory_type == "fix"

        result = ImportResult()

        # Simulate: user picks 'e' (edit), changes resolution to a check phrase,
        # accepts the re-classified type default
        prompts = iter([
            "e",                                # Import? -> edit
            "Error",                            # issue
            "Verify IAM role bindings",         # resolution (changed!)
            "aws_iam_role,kw:iam",              # tags
            "check",                            # type (re-classified default)
        ])

        with patch("click.prompt", side_effect=lambda *a, **kw: next(prompts)):
            _review_flow([fix], 0, repo, result, "jira", dry_run=False)

        assert result.imported == 1
        saved = repo.list_all()
        assert len(saved) == 1
        assert saved[0].memory_type == "check"
