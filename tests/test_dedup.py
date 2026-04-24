"""Tests for content-hash deduplication."""

import importlib

import pytest
from click.testing import CliRunner

from fixdoc.models import Fix, compute_content_hash, _normalize_for_hash
from fixdoc.storage import FixRepository


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_hash_computed_on_creation(self):
        fix = Fix(issue="AccessDenied on s3", resolution="Added bucket policy")
        assert fix.content_hash
        assert len(fix.content_hash) == 16

    def test_hash_is_deterministic(self):
        a = Fix(issue="issue text", resolution="resolution text")
        b = Fix(issue="issue text", resolution="resolution text")
        assert a.content_hash == b.content_hash

    def test_hash_case_insensitive(self):
        a = Fix(issue="AccessDenied", resolution="Added role")
        b = Fix(issue="accessdenied", resolution="added role")
        assert a.content_hash == b.content_hash

    def test_hash_whitespace_normalized(self):
        a = Fix(issue="error   with   spaces", resolution="fix  it")
        b = Fix(issue="error with spaces", resolution="fix it")
        assert a.content_hash == b.content_hash

    def test_hash_strips_leading_trailing(self):
        a = Fix(issue="  issue  ", resolution="  fix  ")
        b = Fix(issue="issue", resolution="fix")
        assert a.content_hash == b.content_hash

    def test_different_content_different_hash(self):
        a = Fix(issue="error A", resolution="fix A")
        b = Fix(issue="error B", resolution="fix B")
        assert a.content_hash != b.content_hash

    def test_same_issue_different_resolution(self):
        a = Fix(issue="error A", resolution="fix A")
        b = Fix(issue="error A", resolution="fix B")
        assert a.content_hash != b.content_hash

    def test_hash_in_to_dict(self):
        fix = Fix(issue="test", resolution="test")
        d = fix.to_dict()
        assert "content_hash" in d
        assert d["content_hash"] == fix.content_hash

    def test_hash_recomputed_in_from_dict(self):
        """Old data without content_hash gets it recomputed."""
        data = {
            "id": "some-id",
            "issue": "error",
            "resolution": "fix",
        }
        fix = Fix.from_dict(data)
        assert fix.content_hash == compute_content_hash("error", "fix")

    def test_hash_from_dict_with_hash(self):
        """Data with content_hash preserves it (but __post_init__ recomputes if empty)."""
        fix1 = Fix(issue="error", resolution="fix")
        data = fix1.to_dict()
        fix2 = Fix.from_dict(data)
        assert fix2.content_hash == fix1.content_hash


class TestNormalizeForHash:
    def test_collapse_whitespace(self):
        assert _normalize_for_hash("a  b\tc\nd") == "a b c d"

    def test_lowercase(self):
        assert _normalize_for_hash("ABC") == "abc"

    def test_strip(self):
        assert _normalize_for_hash("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# Storage dedup tests
# ---------------------------------------------------------------------------


class TestStorageDedup:
    def test_save_duplicate_returns_existing(self, tmp_path):
        repo = FixRepository(tmp_path)
        fix1 = Fix(issue="AccessDenied on s3", resolution="Added bucket policy")
        repo.save(fix1)

        fix2 = Fix(issue="AccessDenied on s3", resolution="Added bucket policy")
        saved = repo.save(fix2)

        assert saved.id == fix1.id
        assert repo.count() == 1

    def test_different_content_creates_separate(self, tmp_path):
        repo = FixRepository(tmp_path)
        fix1 = Fix(issue="error A", resolution="fix A")
        fix2 = Fix(issue="error B", resolution="fix B")
        repo.save(fix1)
        repo.save(fix2)
        assert repo.count() == 2

    def test_same_id_update_works(self, tmp_path):
        repo = FixRepository(tmp_path)
        fix = Fix(issue="error", resolution="fix v1")
        repo.save(fix)

        fix.resolution = "fix v2"
        fix.content_hash = compute_content_hash(fix.issue, fix.resolution)
        repo.save(fix)

        updated = repo.get(fix.id)
        assert updated.resolution == "fix v2"
        assert repo.count() == 1

    def test_case_insensitive_dedup(self, tmp_path):
        repo = FixRepository(tmp_path)
        fix1 = Fix(issue="AccessDenied", resolution="Added Role")
        repo.save(fix1)

        fix2 = Fix(issue="accessdenied", resolution="added role")
        saved = repo.save(fix2)

        assert saved.id == fix1.id
        assert repo.count() == 1

    def test_whitespace_normalized_dedup(self, tmp_path):
        repo = FixRepository(tmp_path)
        fix1 = Fix(issue="error  with  spaces", resolution="fix   it")
        repo.save(fix1)

        fix2 = Fix(issue="error with spaces", resolution="fix it")
        saved = repo.save(fix2)

        assert saved.id == fix1.id
        assert repo.count() == 1

    def test_old_data_without_hash_still_deduped(self, tmp_path):
        """Entries written before content_hash was added still get deduped."""
        import json

        repo = FixRepository(tmp_path)
        # Manually write old-format entry without content_hash
        old_entry = {
            "id": "old-id-1234",
            "issue": "AccessDenied on s3",
            "resolution": "Added bucket policy",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        with open(repo.db_path, "w") as f:
            json.dump([old_entry], f)

        fix2 = Fix(issue="AccessDenied on s3", resolution="Added bucket policy")
        saved = repo.save(fix2)

        assert saved.id == "old-id-1234"
        assert repo.count() == 1

    def test_triple_save_no_growth(self, tmp_path):
        repo = FixRepository(tmp_path)
        for _ in range(3):
            fix = Fix(issue="same issue", resolution="same fix")
            repo.save(fix)
        assert repo.count() == 1


# ---------------------------------------------------------------------------
# Dedup CLI command tests
# ---------------------------------------------------------------------------


_dedup_cmd_mod = importlib.import_module("fixdoc.commands.dedup")


class TestDeduplicateCommand:
    def _seed_duplicates(self, repo, n=3):
        """Seed n duplicates by writing directly to the DB."""
        import json

        entries = []
        for i in range(n):
            entries.append({
                "id": f"dup-{i}",
                "issue": "aws_iam_role.app: AccessDenied",
                "resolution": "Added role binding",
                "created_at": f"2025-01-0{i + 1}T00:00:00+00:00",
                "updated_at": f"2025-01-0{i + 1}T00:00:00+00:00",
                "tags": "",
                "is_private": False,
                "applied_count": 0,
                "success_count": 0,
                "memory_type": "fix",
            })
        # Add one unique fix
        entries.append({
            "id": "unique-1",
            "issue": "Timeout on deploy",
            "resolution": "Increased timeout to 300s",
            "created_at": "2025-02-01T00:00:00+00:00",
            "updated_at": "2025-02-01T00:00:00+00:00",
            "tags": "",
            "is_private": False,
            "applied_count": 0,
            "success_count": 0,
            "memory_type": "fix",
        })
        with open(repo.db_path, "w") as f:
            json.dump(entries, f)

    def test_dry_run_shows_duplicates(self, tmp_path):
        repo = FixRepository(tmp_path)
        self._seed_duplicates(repo, 3)

        runner = CliRunner()
        result = runner.invoke(
            _dedup_cmd_mod.deduplicate,
            ["--dry-run"],
            obj={"base_path": tmp_path},
        )
        assert result.exit_code == 0
        assert "would remove 2 duplicate(s)" in result.output
        # DB unchanged
        assert repo.count() == 4

    def test_removes_duplicates_keeps_oldest(self, tmp_path):
        repo = FixRepository(tmp_path)
        self._seed_duplicates(repo, 3)

        runner = CliRunner()
        result = runner.invoke(
            _dedup_cmd_mod.deduplicate,
            [],
            obj={"base_path": tmp_path},
        )
        assert result.exit_code == 0
        assert "removed 2" in result.output
        assert repo.count() == 2  # 1 kept + 1 unique

        # Oldest kept
        kept = repo.get("dup-0")
        assert kept is not None

    def test_keep_newest(self, tmp_path):
        repo = FixRepository(tmp_path)
        self._seed_duplicates(repo, 3)

        runner = CliRunner()
        result = runner.invoke(
            _dedup_cmd_mod.deduplicate,
            ["--keep", "newest"],
            obj={"base_path": tmp_path},
        )
        assert result.exit_code == 0
        assert repo.count() == 2

        # Newest kept
        kept = repo.get("dup-2")
        assert kept is not None

    def test_no_duplicates_clean_message(self, tmp_path):
        repo = FixRepository(tmp_path)
        Fix(issue="unique A", resolution="fix A")
        repo.save(Fix(issue="unique A", resolution="fix A"))
        repo.save(Fix(issue="unique B", resolution="fix B"))

        runner = CliRunner()
        result = runner.invoke(
            _dedup_cmd_mod.deduplicate,
            [],
            obj={"base_path": tmp_path},
        )
        assert result.exit_code == 0
        assert "No duplicates found" in result.output

    def test_prefers_keeping_tracked_fix(self, tmp_path):
        """Fix with applied_count > 0 is preferred even if not oldest."""
        import json

        repo = FixRepository(tmp_path)
        entries = [
            {
                "id": "old-untracked",
                "issue": "error X",
                "resolution": "fix X",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "applied_count": 0,
                "success_count": 0,
                "memory_type": "fix",
            },
            {
                "id": "newer-tracked",
                "issue": "error X",
                "resolution": "fix X",
                "created_at": "2025-02-01T00:00:00+00:00",
                "updated_at": "2025-02-01T00:00:00+00:00",
                "applied_count": 3,
                "success_count": 2,
                "memory_type": "fix",
            },
        ]
        with open(repo.db_path, "w") as f:
            json.dump(entries, f)

        runner = CliRunner()
        result = runner.invoke(
            _dedup_cmd_mod.deduplicate,
            [],
            obj={"base_path": tmp_path},
        )
        assert result.exit_code == 0
        assert repo.count() == 1
        kept = repo.list_all()[0]
        assert kept.id == "newer-tracked"

    def test_prefers_keeping_fix_with_source_error_ids(self, tmp_path):
        import json

        repo = FixRepository(tmp_path)
        entries = [
            {
                "id": "no-links",
                "issue": "error Y",
                "resolution": "fix Y",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "applied_count": 0,
                "success_count": 0,
                "memory_type": "fix",
            },
            {
                "id": "has-links",
                "issue": "error Y",
                "resolution": "fix Y",
                "created_at": "2025-02-01T00:00:00+00:00",
                "updated_at": "2025-02-01T00:00:00+00:00",
                "applied_count": 0,
                "success_count": 0,
                "source_error_ids": ["abc123"],
                "memory_type": "fix",
            },
        ]
        with open(repo.db_path, "w") as f:
            json.dump(entries, f)

        runner = CliRunner()
        result = runner.invoke(
            _dedup_cmd_mod.deduplicate,
            [],
            obj={"base_path": tmp_path},
        )
        assert result.exit_code == 0
        kept = repo.list_all()[0]
        assert kept.id == "has-links"
