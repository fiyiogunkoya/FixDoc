"""Tests for smart pending features: cwd, _command_family, find_by_context, find_by_cwd."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from fixdoc.pending import (
    PendingEntry,
    PendingStore,
    _command_family,
    pending_entry_from_parsed_error,
)


# ===================================================================
# _command_family
# ===================================================================


class TestCommandFamily:
    def test_terraform_apply_with_flags(self):
        assert _command_family("terraform apply --auto-approve") == "terraform apply"

    def test_kubectl_get_with_flags(self):
        assert _command_family("kubectl get pods -A") == "kubectl get"

    def test_empty_string(self):
        assert _command_family("") == ""

    def test_none(self):
        assert _command_family(None) == ""

    def test_single_token(self):
        assert _command_family("terraform") == "terraform"

    def test_two_tokens_no_flags(self):
        assert _command_family("make apply") == "make apply"

    def test_flags_only(self):
        # All tokens start with "-", so result is ""
        assert _command_family("--verbose --debug") == ""

    def test_more_than_two_tokens(self):
        assert _command_family("helm upgrade release chart") == "helm upgrade"


# ===================================================================
# PendingEntry.cwd field
# ===================================================================


class TestPendingEntryCwd:
    def _make_entry(self, **kwargs):
        defaults = dict(
            error_id="abc123",
            error_type="terraform",
            short_message="Error: something",
            error_excerpt="full error text",
            tags="terraform,aws",
        )
        defaults.update(kwargs)
        return PendingEntry(**defaults)

    def test_cwd_field_default_is_none(self):
        entry = self._make_entry()
        assert entry.cwd is None

    def test_cwd_field_set(self):
        entry = self._make_entry(cwd="/home/user/project")
        assert entry.cwd == "/home/user/project"

    def test_cwd_serializes_in_to_dict(self):
        entry = self._make_entry(cwd="/some/path")
        d = entry.to_dict()
        assert d["cwd"] == "/some/path"

    def test_cwd_deserializes_from_dict(self):
        data = {
            "error_id": "abc123",
            "error_type": "terraform",
            "short_message": "Error",
            "error_excerpt": "text",
            "tags": "",
            "cwd": "/project/dir",
        }
        entry = PendingEntry.from_dict(data)
        assert entry.cwd == "/project/dir"

    def test_old_payload_without_cwd_loads_with_none(self):
        """Backward compat: missing cwd key yields None."""
        data = {
            "error_id": "abc123",
            "error_type": "generic",
            "short_message": "Error",
            "error_excerpt": "text",
            "tags": "",
        }
        entry = PendingEntry.from_dict(data)
        assert entry.cwd is None

    def test_cwd_roundtrip_via_json(self, tmp_path):
        store = PendingStore(tmp_path)
        entry = self._make_entry(cwd="/some/cwd", command="terraform apply")
        store.save(entry)
        loaded = store.list_all()[0]
        assert loaded.cwd == "/some/cwd"


# ===================================================================
# pending_entry_from_parsed_error with cwd
# ===================================================================


class TestPendingEntryFromParsedError:
    def _make_parsed_error(self):
        from fixdoc.parsers.base import ParsedError, CloudProvider
        return ParsedError(
            error_type="terraform",
            error_message="access denied",
            raw_output="Error: access denied on aws_iam_role.app",
            resource_address="aws_iam_role.app",
            error_code="AccessDenied",
            cloud_provider=CloudProvider.AWS,
        )

    def test_cwd_passed_through(self):
        err = self._make_parsed_error()
        entry = pending_entry_from_parsed_error(err, command="terraform apply", cwd="/my/project")
        assert entry.cwd == "/my/project"

    def test_cwd_defaults_to_none(self):
        err = self._make_parsed_error()
        entry = pending_entry_from_parsed_error(err, command="terraform apply")
        assert entry.cwd is None

    def test_command_still_set(self):
        err = self._make_parsed_error()
        entry = pending_entry_from_parsed_error(err, command="terraform apply --auto-approve", cwd="/x")
        assert entry.command == "terraform apply --auto-approve"


# ===================================================================
# PendingStore.find_by_context
# ===================================================================


class TestFindByContext:
    def _make_store_with_entries(self, tmp_path, entries):
        store = PendingStore(tmp_path)
        for e in entries:
            store.save(e)
        return store

    def _entry(self, error_id, cwd, command, deferred_at=None, **kwargs):
        if deferred_at is None:
            deferred_at = datetime.now(timezone.utc).isoformat()
        return PendingEntry(
            error_id=error_id,
            error_type="terraform",
            short_message="Error",
            error_excerpt="text",
            tags="",
            cwd=cwd,
            command=command,
            deferred_at=deferred_at,
            **kwargs,
        )

    def test_matches_same_cwd_and_family_within_24h(self, tmp_path):
        entry = self._entry("id1", "/proj", "terraform apply --auto-approve")
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert len(results) == 1
        assert results[0].error_id == "id1"

    def test_ignores_different_cwd(self, tmp_path):
        entry = self._entry("id1", "/other", "terraform apply")
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert results == []

    def test_ignores_different_command_family(self, tmp_path):
        entry = self._entry("id1", "/proj", "kubectl apply -f manifest.yaml")
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert results == []

    def test_ignores_entries_older_than_24h(self, tmp_path):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        entry = self._entry("id1", "/proj", "terraform apply", deferred_at=old_time)
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert results == []

    def test_includes_entries_within_24h(self, tmp_path):
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
        entry = self._entry("id1", "/proj", "terraform apply", deferred_at=recent_time)
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert len(results) == 1

    def test_handles_entry_with_no_cwd(self, tmp_path):
        entry = PendingEntry(
            error_id="id1",
            error_type="generic",
            short_message="err",
            error_excerpt="text",
            tags="",
            command="terraform apply",
            cwd=None,
        )
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert results == []

    def test_handles_entry_with_no_command(self, tmp_path):
        entry = PendingEntry(
            error_id="id1",
            error_type="generic",
            short_message="err",
            error_excerpt="text",
            tags="",
            cwd="/proj",
            command=None,
        )
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert results == []

    def test_handles_naive_iso_deferred_at(self, tmp_path):
        """Naive ISO string (no timezone) is treated as UTC."""
        # Naive timestamp from ~1 hour ago
        naive_recent = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        entry = self._entry("id1", "/proj", "terraform apply", deferred_at=naive_recent)
        store = self._make_store_with_entries(tmp_path, [entry])
        results = store.find_by_context("/proj", "terraform apply")
        assert len(results) == 1

    def test_returns_multiple_matches(self, tmp_path):
        e1 = self._entry("id1", "/proj", "terraform apply")
        e2 = self._entry("id2", "/proj", "terraform apply --auto-approve")
        store = self._make_store_with_entries(tmp_path, [e1, e2])
        results = store.find_by_context("/proj", "terraform apply")
        assert len(results) == 2

    def test_custom_max_age_hours(self, tmp_path):
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        entry = self._entry("id1", "/proj", "terraform apply", deferred_at=old)
        store = self._make_store_with_entries(tmp_path, [entry])
        # Default 24h includes it
        assert len(store.find_by_context("/proj", "terraform apply")) == 1
        # 2h window excludes it
        assert len(store.find_by_context("/proj", "terraform apply", max_age_hours=2)) == 0


# ===================================================================
# PendingStore.find_by_cwd
# ===================================================================


class TestFindByCwd:
    def _entry(self, error_id, cwd, **kwargs):
        return PendingEntry(
            error_id=error_id,
            error_type="terraform",
            short_message="Error",
            error_excerpt="text",
            tags="",
            cwd=cwd,
            **kwargs,
        )

    def test_returns_entries_for_matching_cwd(self, tmp_path):
        store = PendingStore(tmp_path)
        e1 = self._entry("id1", "/proj")
        e2 = self._entry("id2", "/proj")
        e3 = self._entry("id3", "/other")
        store.save(e1)
        store.save(e2)
        store.save(e3)
        results = store.find_by_cwd("/proj")
        assert len(results) == 2
        ids = {r.error_id for r in results}
        assert ids == {"id1", "id2"}

    def test_returns_empty_when_no_match(self, tmp_path):
        store = PendingStore(tmp_path)
        e = self._entry("id1", "/other")
        store.save(e)
        results = store.find_by_cwd("/proj")
        assert results == []

    def test_ignores_age_and_command(self, tmp_path):
        """find_by_cwd returns regardless of age or command."""
        store = PendingStore(tmp_path)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        e = PendingEntry(
            error_id="id1",
            error_type="generic",
            short_message="err",
            error_excerpt="text",
            tags="",
            cwd="/proj",
            command="some-old-command",
            deferred_at=old_time,
        )
        store.save(e)
        results = store.find_by_cwd("/proj")
        assert len(results) == 1

    def test_none_cwd_not_returned_for_real_cwd(self, tmp_path):
        store = PendingStore(tmp_path)
        e = PendingEntry(
            error_id="id1",
            error_type="generic",
            short_message="err",
            error_excerpt="text",
            tags="",
            cwd=None,
        )
        store.save(e)
        results = store.find_by_cwd("/proj")
        assert results == []


# ===================================================================
# PendingStore.find_latest_session
# ===================================================================


class TestFindLatestSession:
    def _entry(self, error_id, cwd, command_family, session_id, deferred_at=None, **kwargs):
        if deferred_at is None:
            deferred_at = datetime.now(timezone.utc).isoformat()
        return PendingEntry(
            error_id=error_id,
            error_type="terraform",
            short_message="Error",
            error_excerpt="text",
            tags="",
            cwd=cwd,
            command_family=command_family,
            session_id=session_id,
            deferred_at=deferred_at,
            **kwargs,
        )

    def test_returns_entries_from_latest_session(self, tmp_path):
        """Returns only entries from the most recent session_id."""
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        new_time = datetime.now(timezone.utc).isoformat()
        store = PendingStore(tmp_path)
        e_old = self._entry("id1", "/proj", "terraform apply", "sess_a", deferred_at=old_time)
        e_new = self._entry("id2", "/proj", "terraform apply", "sess_b", deferred_at=new_time)
        store.save(e_old)
        store.save(e_new)
        results = store.find_latest_session("/proj", "terraform apply")
        assert len(results) == 1
        assert results[0].error_id == "id2"

    def test_returns_all_entries_in_latest_session(self, tmp_path):
        """Returns all entries sharing the latest session_id."""
        store = PendingStore(tmp_path)
        now = datetime.now(timezone.utc).isoformat()
        e1 = self._entry("id1", "/proj", "terraform apply", "sess_b", deferred_at=now)
        e2 = self._entry("id2", "/proj", "terraform apply", "sess_b", deferred_at=now)
        store.save(e1)
        store.save(e2)
        results = store.find_latest_session("/proj", "terraform apply")
        assert len(results) == 2

    def test_excludes_superseded_entries(self, tmp_path):
        """Superseded entries are not returned."""
        store = PendingStore(tmp_path)
        now = datetime.now(timezone.utc).isoformat()
        e = self._entry("id1", "/proj", "terraform apply", "sess_a",
                        deferred_at=now, status="superseded")
        store.save(e)
        results = store.find_latest_session("/proj", "terraform apply")
        assert results == []

    def test_ignores_different_cwd(self, tmp_path):
        store = PendingStore(tmp_path)
        e = self._entry("id1", "/other", "terraform apply", "sess_a")
        store.save(e)
        results = store.find_latest_session("/proj", "terraform apply")
        assert results == []

    def test_ignores_different_command_family(self, tmp_path):
        store = PendingStore(tmp_path)
        e = self._entry("id1", "/proj", "kubectl apply", "sess_a")
        store.save(e)
        results = store.find_latest_session("/proj", "terraform apply")
        assert results == []

    def test_ignores_entries_older_than_window(self, tmp_path):
        store = PendingStore(tmp_path)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        e = self._entry("id1", "/proj", "terraform apply", "sess_a", deferred_at=old_time)
        store.save(e)
        results = store.find_latest_session("/proj", "terraform apply")
        assert results == []

    def test_empty_store_returns_empty(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.find_latest_session("/proj", "terraform apply") == []


# ===================================================================
# PendingStore.supersede_context
# ===================================================================


class TestSupersedeContext:
    def _entry(self, error_id, cwd, command_family, **kwargs):
        return PendingEntry(
            error_id=error_id,
            error_type="terraform",
            short_message="Error",
            error_excerpt="text",
            tags="",
            cwd=cwd,
            command_family=command_family,
            **kwargs,
        )

    def test_marks_matching_entries_as_superseded(self, tmp_path):
        store = PendingStore(tmp_path)
        e = self._entry("id1", "/proj", "terraform apply")
        store.save(e)
        count = store.supersede_context("/proj", "terraform apply")
        assert count == 1
        # Entry still exists, but is now superseded
        all_entries = store.list_all(include_superseded=True)
        assert len(all_entries) == 1
        assert all_entries[0].status == "superseded"
        # Not returned by default list_all
        assert store.list_all() == []

    def test_does_not_delete_entries(self, tmp_path):
        """supersede_context preserves entries (does not remove them)."""
        store = PendingStore(tmp_path)
        store.save(self._entry("id1", "/proj", "terraform apply"))
        store.supersede_context("/proj", "terraform apply")
        assert len(store.list_all(include_superseded=True)) == 1

    def test_skips_entries_from_different_cwd(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(self._entry("id1", "/other", "terraform apply"))
        count = store.supersede_context("/proj", "terraform apply")
        assert count == 0
        assert store.list_all()[0].status == "pending"

    def test_does_not_double_supersede(self, tmp_path):
        """Calling supersede_context twice only marks entries once."""
        store = PendingStore(tmp_path)
        store.save(self._entry("id1", "/proj", "terraform apply"))
        store.supersede_context("/proj", "terraform apply")
        count2 = store.supersede_context("/proj", "terraform apply")
        assert count2 == 0  # Already superseded, not re-counted

    def test_returns_zero_for_empty_store(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.supersede_context("/proj", "terraform apply") == 0


# ===================================================================
# PendingEntry new fields: session_id, status, command_family, kind
# ===================================================================


class TestPendingEntryNewFields:
    def _base_entry(self, **kwargs):
        defaults = dict(
            error_id="abc",
            error_type="terraform",
            short_message="err",
            error_excerpt="text",
            tags="",
        )
        defaults.update(kwargs)
        return PendingEntry(**defaults)

    def test_default_status_is_pending(self):
        e = self._base_entry()
        assert e.status == "pending"

    def test_session_id_default_is_none(self):
        e = self._base_entry()
        assert e.session_id is None

    def test_command_family_default_is_none(self):
        e = self._base_entry()
        assert e.command_family is None

    def test_kind_default_is_none(self):
        e = self._base_entry()
        assert e.kind is None

    def test_new_fields_serialize(self):
        e = self._base_entry(session_id="aabbccdd", status="superseded",
                              command_family="terraform apply", kind="resource")
        d = e.to_dict()
        assert d["session_id"] == "aabbccdd"
        assert d["status"] == "superseded"
        assert d["command_family"] == "terraform apply"
        assert d["kind"] == "resource"

    def test_old_payload_without_new_fields_loads_cleanly(self):
        """Backward compat: old JSON without new fields loads with defaults."""
        data = {
            "error_id": "abc",
            "error_type": "terraform",
            "short_message": "err",
            "error_excerpt": "text",
            "tags": "",
        }
        e = PendingEntry.from_dict(data)
        assert e.status == "pending"
        assert e.session_id is None
        assert e.command_family is None
        assert e.kind is None


# ===================================================================
# pending_entry_from_parsed_error — session_id, command_family, kind
# ===================================================================


class TestPendingEntryFromParsedErrorNewFields:
    def _make_parsed_error(self, resource_address="aws_iam_role.app"):
        from fixdoc.parsers.base import ParsedError, CloudProvider
        return ParsedError(
            error_type="terraform",
            error_message="access denied",
            raw_output="Error: access denied",
            resource_address=resource_address,
            error_code="AccessDenied",
            cloud_provider=CloudProvider.AWS,
        )

    def test_session_id_passed_through(self):
        err = self._make_parsed_error()
        entry = pending_entry_from_parsed_error(
            err, session_id="deadbeef", command_family="terraform apply"
        )
        assert entry.session_id == "deadbeef"
        assert entry.command_family == "terraform apply"

    def test_kind_resource_for_normal_address(self):
        err = self._make_parsed_error("aws_iam_role.app")
        entry = pending_entry_from_parsed_error(err)
        assert entry.kind == "resource"

    def test_kind_terraform_config_for_variable(self):
        err = self._make_parsed_error("variable.instance_count")
        entry = pending_entry_from_parsed_error(err)
        assert entry.kind == "terraform_config"

    def test_kind_terraform_config_for_output(self):
        err = self._make_parsed_error("output.my_output")
        entry = pending_entry_from_parsed_error(err)
        assert entry.kind == "terraform_config"

    def test_kind_terraform_config_for_module(self):
        err = self._make_parsed_error("module.networking")
        entry = pending_entry_from_parsed_error(err)
        assert entry.kind == "terraform_config"

    def test_kind_terraform_init(self):
        err = self._make_parsed_error("terraform.init")
        entry = pending_entry_from_parsed_error(err)
        assert entry.kind == "terraform_init"

    def test_kind_defaults_to_resource_for_none_address(self):
        err = self._make_parsed_error(resource_address=None)
        entry = pending_entry_from_parsed_error(err)
        assert entry.kind == "resource"
