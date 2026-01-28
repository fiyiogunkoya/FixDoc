"""Configuration management for fixdoc sync."""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SyncConfig:
    """Configuration for Git sync operations."""

    remote_url: Optional[str] = None
    branch: str = "main"
    auto_pull: bool = False


@dataclass
class UserConfig:
    """User identity for attribution."""

    name: Optional[str] = None
    email: Optional[str] = None


@dataclass
class FixDocConfig:
    """Root configuration object."""

    sync: SyncConfig = field(default_factory=SyncConfig)
    user: UserConfig = field(default_factory=UserConfig)
    private_fixes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert config to dictionary for YAML serialization."""
        return {
            "sync": asdict(self.sync),
            "user": asdict(self.user),
            "private_fixes": self.private_fixes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixDocConfig":
        """Create config from dictionary loaded from YAML."""
        sync_data = data.get("sync", {})
        user_data = data.get("user", {})
        private_fixes = data.get("private_fixes", [])

        return cls(
            sync=SyncConfig(
                remote_url=sync_data.get("remote_url"),
                branch=sync_data.get("branch", "main"),
                auto_pull=sync_data.get("auto_pull", False),
            ),
            user=UserConfig(
                name=user_data.get("name"),
                email=user_data.get("email"),
            ),
            private_fixes=private_fixes,
        )


class ConfigManager:
    """Manages ~/.fixdoc/config.yaml."""

    CONFIG_FILE = "config.yaml"

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.home() / ".fixdoc"
        self.config_path = self.base_path / self.CONFIG_FILE

    def load(self) -> FixDocConfig:
        """Load config from YAML, return defaults if not exists."""
        if not self.config_path.exists():
            return FixDocConfig()

        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}
            return FixDocConfig.from_dict(data)
        except (yaml.YAMLError, IOError):
            return FixDocConfig()

    def save(self, config: FixDocConfig) -> None:
        """Save config to YAML."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.safe_dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)

    def is_sync_configured(self) -> bool:
        """Check if sync has been initialized."""
        config = self.load()
        return config.sync.remote_url is not None

    def add_private_fix(self, fix_id: str) -> None:
        """Add a fix ID to the private list."""
        config = self.load()
        if fix_id not in config.private_fixes:
            config.private_fixes.append(fix_id)
            self.save(config)

    def remove_private_fix(self, fix_id: str) -> None:
        """Remove a fix ID from the private list."""
        config = self.load()
        if fix_id in config.private_fixes:
            config.private_fixes.remove(fix_id)
            self.save(config)

    def is_fix_private(self, fix_id: str) -> bool:
        """Check if a fix is marked as private."""
        config = self.load()
        return fix_id in config.private_fixes
