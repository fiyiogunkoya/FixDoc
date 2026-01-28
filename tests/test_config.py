"""Tests for fixdoc configuration management."""

import pytest
from pathlib import Path
import tempfile

from fixdoc.config import ConfigManager, FixDocConfig, SyncConfig, UserConfig


class TestFixDocConfig:
    def test_default_config(self):
        config = FixDocConfig()

        assert config.sync.remote_url is None
        assert config.sync.branch == "main"
        assert config.sync.auto_pull is False
        assert config.user.name is None
        assert config.user.email is None
        assert config.private_fixes == []

    def test_to_dict(self):
        config = FixDocConfig(
            sync=SyncConfig(
                remote_url="git@github.com:test/repo.git",
                branch="develop",
                auto_pull=True,
            ),
            user=UserConfig(name="John Doe", email="john@example.com"),
            private_fixes=["fix-1", "fix-2"],
        )

        d = config.to_dict()

        assert d["sync"]["remote_url"] == "git@github.com:test/repo.git"
        assert d["sync"]["branch"] == "develop"
        assert d["sync"]["auto_pull"] is True
        assert d["user"]["name"] == "John Doe"
        assert d["user"]["email"] == "john@example.com"
        assert d["private_fixes"] == ["fix-1", "fix-2"]

    def test_from_dict(self):
        data = {
            "sync": {
                "remote_url": "https://github.com/test/repo.git",
                "branch": "main",
                "auto_pull": False,
            },
            "user": {"name": "Jane Doe", "email": "jane@example.com"},
            "private_fixes": ["abc123"],
        }

        config = FixDocConfig.from_dict(data)

        assert config.sync.remote_url == "https://github.com/test/repo.git"
        assert config.sync.branch == "main"
        assert config.user.name == "Jane Doe"
        assert config.private_fixes == ["abc123"]

    def test_from_dict_with_defaults(self):
        data = {}

        config = FixDocConfig.from_dict(data)

        assert config.sync.remote_url is None
        assert config.sync.branch == "main"
        assert config.user.name is None
        assert config.private_fixes == []


class TestConfigManager:
    def test_load_nonexistent_returns_default(self, tmp_path):
        manager = ConfigManager(tmp_path)

        config = manager.load()

        assert config.sync.remote_url is None
        assert config.user.name is None

    def test_save_and_load(self, tmp_path):
        manager = ConfigManager(tmp_path)
        config = FixDocConfig(
            sync=SyncConfig(remote_url="git@github.com:test/repo.git"),
            user=UserConfig(name="Test User", email="test@example.com"),
        )

        manager.save(config)
        loaded = manager.load()

        assert loaded.sync.remote_url == "git@github.com:test/repo.git"
        assert loaded.user.name == "Test User"
        assert loaded.user.email == "test@example.com"

    def test_is_sync_configured(self, tmp_path):
        manager = ConfigManager(tmp_path)

        assert manager.is_sync_configured() is False

        config = FixDocConfig(
            sync=SyncConfig(remote_url="git@github.com:test/repo.git")
        )
        manager.save(config)

        assert manager.is_sync_configured() is True

    def test_add_private_fix(self, tmp_path):
        manager = ConfigManager(tmp_path)

        manager.add_private_fix("fix-123")
        manager.add_private_fix("fix-456")
        manager.add_private_fix("fix-123")  # Duplicate

        config = manager.load()
        assert "fix-123" in config.private_fixes
        assert "fix-456" in config.private_fixes
        assert len(config.private_fixes) == 2  # No duplicate

    def test_remove_private_fix(self, tmp_path):
        manager = ConfigManager(tmp_path)
        manager.add_private_fix("fix-123")
        manager.add_private_fix("fix-456")

        manager.remove_private_fix("fix-123")

        config = manager.load()
        assert "fix-123" not in config.private_fixes
        assert "fix-456" in config.private_fixes

    def test_is_fix_private(self, tmp_path):
        manager = ConfigManager(tmp_path)
        manager.add_private_fix("fix-123")

        assert manager.is_fix_private("fix-123") is True
        assert manager.is_fix_private("fix-456") is False

    def test_creates_directory_on_save(self, tmp_path):
        nested_path = tmp_path / "nested" / "path"
        manager = ConfigManager(nested_path)
        config = FixDocConfig()

        manager.save(config)

        assert nested_path.exists()
        assert (nested_path / "config.yaml").exists()
