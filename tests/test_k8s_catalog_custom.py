"""Tests for YAML custom catalog loading, merging, and AI generation."""

import importlib
import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from fixdoc.k8s.catalog import (
    _catalog_key,
    _load_yaml_file,
    build_merged_catalog,
    list_categories,
    list_changes,
    load_custom_entries,
    resolve_change,
)
from fixdoc.k8s.models import BreakingChange, CatalogEntry
from fixdoc.commands.k8s_cmd import k8s_group

_k8s_cmd_mod = importlib.import_module("fixdoc.commands.k8s_cmd")
_pending_mod = importlib.import_module("fixdoc.pending")

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "k8s" / "catalog"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestYamlLoading:
    def test_load_single_entry(self):
        entries = _load_yaml_file(FIXTURE_DIR / "single_entry.yaml")
        assert len(entries) == 1
        e = entries[0]
        assert e.category == "os-upgrade"
        assert e.from_version == "ubuntu:22.04"
        assert e.to_version == "ubuntu:24.04"
        assert e.display_name == "Ubuntu 22.04 to 24.04"
        assert len(e.breaking_changes) == 1
        assert e.breaking_changes[0].severity == "high"

    def test_load_multi_entry(self):
        entries = _load_yaml_file(FIXTURE_DIR / "multi_entry.yaml")
        assert len(entries) == 2
        cats = {e.category for e in entries}
        assert "os-upgrade" in cats
        assert "ingress-controller" in cats

    def test_load_empty_file(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        entries = _load_yaml_file(p)
        assert entries == []

    def test_load_invalid_yaml(self):
        entries = _load_yaml_file(FIXTURE_DIR / "invalid.yaml")
        assert entries == []

    def test_load_missing_fields(self):
        entries = _load_yaml_file(FIXTURE_DIR / "missing_fields.yaml")
        assert entries == []

    def test_load_yml_extension(self, tmp_path):
        p = tmp_path / "test.yml"
        data = {
            "category": "k8s-version",
            "from_version": "1.30",
            "to_version": "1.31",
            "display_name": "K8s 1.30 to 1.31",
            "breaking_changes": [],
        }
        p.write_text(yaml.dump(data))
        entries = _load_yaml_file(p)
        assert len(entries) == 1
        assert entries[0].category == "k8s-version"

    def test_breaking_changes_deserialized(self):
        entries = _load_yaml_file(FIXTURE_DIR / "single_entry.yaml")
        bc = entries[0].breaking_changes[0]
        assert isinstance(bc, BreakingChange)
        assert bc.id == "ubuntu-2404-systemd"
        assert len(bc.detection_hints) == 1

    def test_source_field_set(self):
        entries = _load_yaml_file(FIXTURE_DIR / "single_entry.yaml")
        assert entries[0].source == "single_entry.yaml"

    def test_load_nonexistent_file(self, tmp_path):
        entries = _load_yaml_file(tmp_path / "does_not_exist.yaml")
        assert entries == []

    def test_load_list_yaml(self, tmp_path):
        """A YAML file with a top-level list (not dict) returns empty."""
        p = tmp_path / "list.yaml"
        p.write_text("- foo\n- bar\n")
        entries = _load_yaml_file(p)
        assert entries == []


# ---------------------------------------------------------------------------
# Custom entry discovery
# ---------------------------------------------------------------------------


class TestCustomEntryDiscovery:
    def test_no_directory(self, tmp_path):
        entries = load_custom_entries(catalog_dir=tmp_path / "nonexistent")
        assert entries == []

    def test_empty_directory(self, tmp_path):
        d = tmp_path / ".fixdoc-catalog"
        d.mkdir()
        entries = load_custom_entries(catalog_dir=d)
        assert entries == []

    def test_files_found(self):
        entries = load_custom_entries(catalog_dir=FIXTURE_DIR)
        # single_entry.yaml (1) + multi_entry.yaml (2) + override_builtin.yaml (1)
        # invalid.yaml (0) + missing_fields.yaml (0)
        assert len(entries) == 4

    def test_non_yaml_ignored(self, tmp_path):
        d = tmp_path / ".fixdoc-catalog"
        d.mkdir()
        (d / "readme.txt").write_text("not yaml")
        (d / "notes.md").write_text("# notes")
        entries = load_custom_entries(catalog_dir=d)
        assert entries == []

    def test_partial_load_on_error(self, tmp_path):
        d = tmp_path / ".fixdoc-catalog"
        d.mkdir()
        # Valid file
        valid = {
            "category": "k8s-version",
            "from_version": "1.29",
            "to_version": "1.30",
            "display_name": "K8s 1.29 to 1.30",
            "breaking_changes": [],
        }
        (d / "a_valid.yaml").write_text(yaml.dump(valid))
        # Invalid file
        (d / "b_invalid.yaml").write_text("{{broken yaml")
        entries = load_custom_entries(catalog_dir=d)
        assert len(entries) == 1
        assert entries[0].category == "k8s-version"


# ---------------------------------------------------------------------------
# Merged catalog
# ---------------------------------------------------------------------------


class TestMergedCatalog:
    def test_no_custom_returns_builtins(self):
        merged = build_merged_catalog([])
        assert len(merged) == 4  # 4 built-in entries

    def test_new_category_added(self):
        custom = [CatalogEntry(
            category="custom-thing",
            from_version="1.0",
            to_version="2.0",
            display_name="Custom Thing",
        )]
        merged = build_merged_catalog(custom)
        assert len(merged) == 5
        cats = {e.category for e in merged}
        assert "custom-thing" in cats

    def test_override_replaces_builtin(self):
        override = _load_yaml_file(FIXTURE_DIR / "override_builtin.yaml")
        merged = build_merged_catalog(override)
        # Still 4 entries (override replaces os-upgrade azurelinux)
        assert len(merged) == 4
        os_entries = [e for e in merged if e.category == "os-upgrade"
                      and "azurelinux" in e.from_version]
        assert len(os_entries) == 1
        assert "Custom Override" in os_entries[0].display_name

    def test_preserves_non_overridden(self):
        override = _load_yaml_file(FIXTURE_DIR / "override_builtin.yaml")
        merged = build_merged_catalog(override)
        k8s_entries = [e for e in merged if e.category == "k8s-version"]
        assert len(k8s_entries) == 1
        assert k8s_entries[0].source == "built-in"

    def test_node_pool_sku_version_specific(self):
        """node-pool-sku entries with different versions are separate entries."""
        custom = [CatalogEntry(
            category="node-pool-sku",
            from_version="Standard_D8s_v3",
            to_version="Standard_D16s_v3",
            display_name="D8s to D16s",
            source="custom.yaml",
        )]
        merged = build_merged_catalog(custom)
        sku_entries = [e for e in merged if e.category == "node-pool-sku"]
        assert len(sku_entries) == 2  # built-in D2s->D4s + custom D8s->D16s

    def test_source_field_preserved(self):
        custom = [CatalogEntry(
            category="k8s-version",
            from_version="1.30",
            to_version="1.31",
            display_name="K8s 1.30 to 1.31",
            source="my_file.yaml",
        )]
        merged = build_merged_catalog(custom)
        new_entry = [e for e in merged if e.from_version == "1.30"]
        assert len(new_entry) == 1
        assert new_entry[0].source == "my_file.yaml"


# ---------------------------------------------------------------------------
# Resolve with custom catalog
# ---------------------------------------------------------------------------


class TestResolveWithCustom:
    def test_custom_resolves(self):
        custom_entry = CatalogEntry(
            category="k8s-version",
            from_version="1.30",
            to_version="1.31",
            display_name="K8s 1.30 to 1.31",
        )
        merged = build_merged_catalog([custom_entry])
        result = resolve_change("k8s-version", "1.30", "1.31", catalog=merged)
        assert result is not None
        assert result.display_name == "K8s 1.30 to 1.31"

    def test_override_works(self):
        override = _load_yaml_file(FIXTURE_DIR / "override_builtin.yaml")
        merged = build_merged_catalog(override)
        result = resolve_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0", catalog=merged)
        assert result is not None
        assert "Custom Override" in result.display_name

    def test_builtin_unaffected_without_catalog(self):
        result = resolve_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0")
        assert result is not None
        assert "Custom Override" not in result.display_name

    def test_categories_include_custom(self):
        custom = [CatalogEntry(
            category="custom-cat",
            from_version="1.0",
            to_version="2.0",
            display_name="Custom",
        )]
        merged = build_merged_catalog(custom)
        cats = list_categories(catalog=merged)
        assert "custom-cat" in cats
        assert "os-upgrade" in cats


# ---------------------------------------------------------------------------
# CLI — changes command with custom entries
# ---------------------------------------------------------------------------


class TestChangesCommandCustom:
    @patch.object(_k8s_cmd_mod, "_get_merged_catalog")
    def test_custom_label_shown(self, mock_merged):
        custom_entry = CatalogEntry(
            category="k8s-version",
            from_version="1.30",
            to_version="1.31",
            display_name="K8s 1.30 to 1.31",
            source="my_file.yaml",
        )
        mock_merged.return_value = [custom_entry]
        runner = CliRunner()
        result = runner.invoke(k8s_group, ["changes"])
        assert result.exit_code == 0
        assert "[custom]" in result.output
        assert "K8s 1.30 to 1.31" in result.output

    @patch.object(_k8s_cmd_mod, "_get_merged_catalog")
    def test_builtin_label_shown(self, mock_merged):
        builtin_entry = CatalogEntry(
            category="os-upgrade",
            from_version="azurelinux:2.0",
            to_version="azurelinux:3.0",
            display_name="Azure Linux 2.0 to 3.0",
            source="built-in",
        )
        mock_merged.return_value = [builtin_entry]
        runner = CliRunner()
        result = runner.invoke(k8s_group, ["changes"])
        assert result.exit_code == 0
        assert "[built-in]" in result.output

    @patch.object(_k8s_cmd_mod, "_get_merged_catalog")
    def test_analyze_uses_custom(self, mock_merged):
        custom_entry = CatalogEntry(
            category="k8s-version",
            from_version="1.30",
            to_version="1.31",
            display_name="K8s 1.30 to 1.31 (Custom)",
            breaking_changes=[
                BreakingChange(
                    id="custom-bc",
                    title="Custom BC",
                    severity="high",
                    description="Custom",
                    consequence="Custom",
                ),
            ],
            source="custom.yaml",
        )
        mock_merged.return_value = build_merged_catalog([custom_entry])
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "k8s-version",
            "--from", "1.30",
            "--to", "1.31",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "K8s 1.30 to 1.31 (Custom)" in result.output


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------


class TestGenerateCatalogEntry:
    def test_mock_anthropic_call(self):
        from fixdoc.k8s.generate import generate_catalog_entry

        valid_yaml = yaml.dump({
            "category": "k8s-version",
            "from_version": "1.29",
            "to_version": "1.30",
            "display_name": "K8s 1.29 to 1.30",
            "breaking_changes": [{
                "id": "psp-removed",
                "title": "PSP removed",
                "severity": "critical",
                "description": "PSP is removed",
                "consequence": "Pods lose constraints",
                "detection_hints": [],
                "tags": ["psp"],
            }],
            "pre_checks": ["Audit PSP"],
            "post_checks": ["Verify PSA"],
            "tags": ["kubernetes"],
        })

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=valid_yaml)]
        mock_client.messages.create.return_value = mock_msg

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = generate_catalog_entry(
                category="k8s-version",
                from_version="1.29",
                to_version="1.30",
                release_notes="PSP is removed in v1.30.",
                api_key="test-key",
            )

        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["category"] == "k8s-version"

    def test_valid_yaml_output(self):
        from fixdoc.k8s.generate import validate_generated_yaml

        valid_yaml = yaml.dump({
            "category": "k8s-version",
            "from_version": "1.29",
            "to_version": "1.30",
            "display_name": "K8s 1.29 to 1.30",
            "breaking_changes": [],
        })
        entry = validate_generated_yaml(valid_yaml)
        assert entry is not None
        assert entry.category == "k8s-version"

    def test_invalid_yaml_returns_none(self):
        from fixdoc.k8s.generate import validate_generated_yaml

        entry = validate_generated_yaml("{{not valid yaml")
        assert entry is None

    def test_missing_api_key(self):
        from fixdoc.k8s.generate import generate_catalog_entry

        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}), \
             patch.dict(os.environ, {}, clear=True):
            # Remove ANTHROPIC_API_KEY from env
            os.environ.pop("ANTHROPIC_API_KEY", None)
            result = generate_catalog_entry(
                category="k8s-version",
                from_version="1.29",
                to_version="1.30",
                release_notes="test",
            )
        assert result is None

    def test_import_error_returns_none(self):
        from fixdoc.k8s.generate import generate_catalog_entry

        with patch.dict("sys.modules", {"anthropic": None}):
            result = generate_catalog_entry(
                category="k8s-version",
                from_version="1.29",
                to_version="1.30",
                release_notes="test",
                api_key="test-key",
            )
        assert result is None

    def test_prompt_contains_hint_fields(self):
        from fixdoc.k8s.generate import generate_catalog_entry, _VALID_HINT_FIELDS

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="category: test\nfrom_version: '1'\nto_version: '2'")]
        mock_client.messages.create.return_value = mock_msg

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            generate_catalog_entry(
                category="k8s-version",
                from_version="1.29",
                to_version="1.30",
                release_notes="test notes",
                api_key="test-key",
            )

        call_args = mock_client.messages.create.call_args
        prompt_text = call_args[1]["messages"][0]["content"]
        for field in _VALID_HINT_FIELDS:
            assert field in prompt_text


# ---------------------------------------------------------------------------
# CLI — catalog generate
# ---------------------------------------------------------------------------


class TestGenerateCLI:
    @patch.object(_pending_mod, "_find_git_root")
    def test_from_text(self, mock_git_root, tmp_path):
        mock_git_root.return_value = tmp_path

        valid_yaml = yaml.dump({
            "category": "k8s-version",
            "from_version": "1.29",
            "to_version": "1.30",
            "display_name": "K8s 1.29 to 1.30",
            "breaking_changes": [{
                "id": "psp-removed",
                "title": "PSP removed",
                "severity": "critical",
                "description": "PSP removed",
                "consequence": "Pods lose constraints",
                "detection_hints": [],
                "tags": ["psp"],
            }],
            "pre_checks": ["Audit PSP"],
            "post_checks": ["Verify PSA"],
            "tags": ["kubernetes"],
        })

        gen_mod = importlib.import_module("fixdoc.k8s.generate")
        with patch.object(gen_mod, "generate_catalog_entry", return_value=valid_yaml):
            runner = CliRunner()
            result = runner.invoke(k8s_group, [
                "catalog", "generate",
                "--change", "k8s-version",
                "--from", "1.29",
                "--to", "1.30",
                "--from-text", "PSP is removed in v1.30.",
            ])

        assert result.exit_code == 0
        out_file = tmp_path / ".fixdoc-catalog" / "k8s-version-1.29-1.30.yaml"
        assert out_file.exists()
        content = yaml.safe_load(out_file.read_text())
        assert content["category"] == "k8s-version"

    @patch.object(_pending_mod, "_find_git_root")
    @patch.object(_k8s_cmd_mod, "_fetch_url_text")
    def test_from_url(self, mock_fetch, mock_git_root, tmp_path):
        mock_git_root.return_value = tmp_path
        mock_fetch.return_value = "PSP is removed in v1.30. Use PSA instead."

        valid_yaml = yaml.dump({
            "category": "k8s-version",
            "from_version": "1.29",
            "to_version": "1.30",
            "display_name": "K8s 1.29 to 1.30",
            "breaking_changes": [],
        })

        gen_mod = importlib.import_module("fixdoc.k8s.generate")
        with patch.object(gen_mod, "generate_catalog_entry", return_value=valid_yaml):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(k8s_group, [
                "catalog", "generate",
                "--change", "k8s-version",
                "--from", "1.29",
                "--to", "1.30",
                "--from-url", "https://example.com/notes",
            ])

        assert result.exit_code == 0
        out_file = tmp_path / ".fixdoc-catalog" / "k8s-version-1.29-1.30.yaml"
        assert out_file.exists()

    @patch.object(_pending_mod, "_find_git_root")
    def test_interactive_stdin(self, mock_git_root, tmp_path):
        mock_git_root.return_value = tmp_path

        valid_yaml = yaml.dump({
            "category": "os-upgrade",
            "from_version": "azurelinux:2.0",
            "to_version": "azurelinux:3.0",
            "display_name": "Azure Linux Upgrade",
            "breaking_changes": [],
        })

        gen_mod = importlib.import_module("fixdoc.k8s.generate")
        with patch.object(gen_mod, "generate_catalog_entry", return_value=valid_yaml):
            runner = CliRunner()
            result = runner.invoke(k8s_group, [
                "catalog", "generate",
                "--change", "os-upgrade",
                "--from", "azurelinux:2.0",
                "--to", "azurelinux:3.0",
            ], input="Some release notes here\n")

        assert result.exit_code == 0
        out_file = tmp_path / ".fixdoc-catalog" / "os-upgrade-azurelinux-2.0-azurelinux-3.0.yaml"
        assert out_file.exists()

    @patch.object(_pending_mod, "_find_git_root")
    def test_file_written_to_catalog_dir(self, mock_git_root, tmp_path):
        mock_git_root.return_value = tmp_path

        valid_yaml = yaml.dump({
            "category": "k8s-version",
            "from_version": "1.29",
            "to_version": "1.30",
            "display_name": "K8s 1.29 to 1.30",
            "breaking_changes": [],
        })

        gen_mod = importlib.import_module("fixdoc.k8s.generate")
        with patch.object(gen_mod, "generate_catalog_entry", return_value=valid_yaml):
            runner = CliRunner()
            result = runner.invoke(k8s_group, [
                "catalog", "generate",
                "--change", "k8s-version",
                "--from", "1.29",
                "--to", "1.30",
                "--from-text", "test notes",
            ])

        assert result.exit_code == 0
        catalog_dir = tmp_path / ".fixdoc-catalog"
        assert catalog_dir.is_dir()
        files = list(catalog_dir.glob("*.yaml"))
        assert len(files) == 1


# ---------------------------------------------------------------------------
# CatalogEntry source field
# ---------------------------------------------------------------------------


class TestCatalogEntrySource:
    def test_default_source(self):
        entry = CatalogEntry(
            category="test",
            from_version="1.0",
            to_version="2.0",
            display_name="Test",
        )
        assert entry.source == "built-in"

    def test_source_not_in_to_dict(self):
        entry = CatalogEntry(
            category="test",
            from_version="1.0",
            to_version="2.0",
            display_name="Test",
            source="custom.yaml",
        )
        d = entry.to_dict()
        assert "source" not in d

    def test_source_from_dict(self):
        entry = CatalogEntry.from_dict({
            "category": "test",
            "from_version": "1.0",
            "to_version": "2.0",
            "source": "my_file.yaml",
        })
        assert entry.source == "my_file.yaml"

    def test_source_default_in_from_dict(self):
        entry = CatalogEntry.from_dict({
            "category": "test",
            "from_version": "1.0",
            "to_version": "2.0",
        })
        assert entry.source == "built-in"
