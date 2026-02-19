"""Configuration management for fixdoc."""

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml


def resolve_base_path() -> Path:
    """Resolve the fixdoc base path.

    Checks FIXDOC_HOME env var first, falls back to ~/.fixdoc.
    """
    env_home = os.environ.get("FIXDOC_HOME")
    if env_home:
        return Path(env_home)
    return Path.home() / ".fixdoc"


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
class DisplayConfig:
    """Configuration for display/output limits."""

    search_result_limit: int = 10
    list_result_limit: int = 20
    top_tags_limit: int = 10


@dataclass
class CaptureConfig:
    """Configuration for the capture pipeline."""

    error_excerpt_max_chars: int = 2000
    max_suggestions_shown: int = 3
    similar_fix_limit: int = 5


@dataclass
class SuggestionWeights:
    """Scoring weights for similar-fix matching."""

    resource_address_weight: int = 25
    error_code_weight: int = 20
    error_similarity_weight: int = 15
    resource_type_weight: int = 8
    tag_weight: int = 5
    issue_keyword_weight: int = 2
    resolution_keyword_weight: int = 1


@dataclass
class FixDocConfig:
    """Root configuration object."""

    sync: SyncConfig = field(default_factory=SyncConfig)
    user: UserConfig = field(default_factory=UserConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    suggestion_weights: SuggestionWeights = field(default_factory=SuggestionWeights)
    private_fixes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert config to dictionary for YAML serialization."""
        return {
            "sync": asdict(self.sync),
            "user": asdict(self.user),
            "display": asdict(self.display),
            "capture": asdict(self.capture),
            "suggestion_weights": asdict(self.suggestion_weights),
            "private_fixes": self.private_fixes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixDocConfig":
        """Create config from dictionary loaded from YAML."""
        sync_data = data.get("sync", {})
        user_data = data.get("user", {})
        display_data = data.get("display", {})
        capture_data = data.get("capture", {})
        weights_data = data.get("suggestion_weights", {})
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
            display=DisplayConfig(
                search_result_limit=display_data.get("search_result_limit", 10),
                list_result_limit=display_data.get("list_result_limit", 20),
                top_tags_limit=display_data.get("top_tags_limit", 10),
            ),
            capture=CaptureConfig(
                error_excerpt_max_chars=capture_data.get("error_excerpt_max_chars", 2000),
                max_suggestions_shown=capture_data.get("max_suggestions_shown", 3),
                similar_fix_limit=capture_data.get("similar_fix_limit", 5),
            ),
            suggestion_weights=SuggestionWeights(
                resource_address_weight=weights_data.get("resource_address_weight", 25),
                error_code_weight=weights_data.get("error_code_weight", 20),
                error_similarity_weight=weights_data.get("error_similarity_weight", 15),
                resource_type_weight=weights_data.get("resource_type_weight", 8),
                tag_weight=weights_data.get("tag_weight", 5),
                issue_keyword_weight=weights_data.get("issue_keyword_weight", 2),
                resolution_keyword_weight=weights_data.get("resolution_keyword_weight", 1),
            ),
            private_fixes=private_fixes,
        )


class ConfigManager:
    """Manages ~/.fixdoc/config.yaml."""

    CONFIG_FILE = "config.yaml"

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or resolve_base_path()
        self.config_path = self.base_path / self.CONFIG_FILE

    def load(self) -> FixDocConfig:
        """Load config from YAML, create with defaults if not exists."""
        if not self.config_path.exists():
            config = FixDocConfig()
            self.save(config)
            return config

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
