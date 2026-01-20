"""
Project ID to Path Resolver for Claude Code Sessions.

The Claude Code CLI stores session data in directories named with encoded paths,
e.g., `/Users/joshpeak/play/myproject` becomes `-Users-joshpeak-play-myproject`.

This module provides utilities to resolve these encoded project IDs back to their
original filesystem paths using multiple strategies:

1. **sessions-index.json** (Primary): Each project directory contains a
   `sessions-index.json` file with a `projectPath` field - the authoritative source.

2. **Path Heuristics** (Fallback): If the index is unavailable, we decode the
   encoded path by replacing `-` with `/` and validating against the filesystem.

Usage:
    resolver = ProjectResolver(projects_path)
    info = resolver.resolve("-Users-joshpeak-play-myproject")
    print(info.project_path)  # /Users/joshpeak/play/myproject
    print(info.project_name)  # myproject
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectInfo:
    """Information about a resolved project."""

    project_id: str
    """The encoded project ID (directory name), e.g., '-Users-joshpeak-play-myproject'."""

    project_path: Path | None
    """The original filesystem path, e.g., Path('/Users/joshpeak/play/myproject')."""

    project_name: str
    """Human-friendly name derived from the path (typically the last path component)."""

    resolution_source: str
    """How the path was resolved: 'sessions-index', 'heuristic', or 'unresolved'."""

    @property
    def is_resolved(self) -> bool:
        """Return True if the project path was successfully resolved."""
        return self.project_path is not None


@dataclass
class ProjectResolver:
    """
    Resolves encoded Claude Code project IDs to their original filesystem paths.

    The resolver uses a two-tier strategy:
    1. Parse sessions-index.json for the authoritative projectPath
    2. Fall back to path heuristics with filesystem validation

    Results are cached for performance.
    """

    projects_path: Path
    """Path to the directory containing project subdirectories."""

    _cache: dict[str, ProjectInfo] = field(default_factory=dict, repr=False)
    """Cache of resolved project information."""

    def __post_init__(self) -> None:
        """Validate the projects path exists."""
        if not self.projects_path.exists():
            raise ValueError(f"Projects path does not exist: {self.projects_path}")

    def resolve(self, project_id: str) -> ProjectInfo:
        """
        Resolve a project ID to its original path.

        Args:
            project_id: The encoded project ID (directory name).

        Returns:
            ProjectInfo with the resolved path and metadata.
        """
        if project_id in self._cache:
            return self._cache[project_id]

        info = self._resolve_uncached(project_id)
        self._cache[project_id] = info
        return info

    def _resolve_uncached(self, project_id: str) -> ProjectInfo:
        """Resolve without cache lookup."""
        project_dir = self.projects_path / project_id

        # Strategy 1: Try sessions-index.json
        info = self._resolve_from_sessions_index(project_id, project_dir)
        if info is not None:
            return info

        # Strategy 2: Path heuristics with filesystem validation
        info = self._resolve_from_heuristics(project_id)
        if info is not None:
            return info

        # Unresolved - return with extracted name at least
        return ProjectInfo(
            project_id=project_id,
            project_path=None,
            project_name=self._extract_name_from_id(project_id),
            resolution_source="unresolved",
        )

    def _resolve_from_sessions_index(
        self, project_id: str, project_dir: Path
    ) -> ProjectInfo | None:
        """
        Try to resolve using sessions-index.json.

        The sessions-index.json file contains entries with a 'projectPath' field
        that gives us the authoritative original path.
        """
        index_file = project_dir / "sessions-index.json"
        if not index_file.exists():
            return None

        try:
            with index_file.open() as f:
                data = json.load(f)

            entries = data.get("entries", [])
            if not entries:
                return None

            # All entries should have the same projectPath; use the first one
            project_path_str = entries[0].get("projectPath")
            if not project_path_str:
                return None

            project_path = Path(project_path_str)
            return ProjectInfo(
                project_id=project_id,
                project_path=project_path,
                project_name=project_path.name,
                resolution_source="sessions-index",
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse sessions-index.json for {project_id}: {e}")
            return None

    def _resolve_from_heuristics(self, project_id: str) -> ProjectInfo | None:
        """
        Resolve using path heuristics with filesystem validation.

        The encoding replaces '/' with '-'. To decode, we try different
        interpretations and validate against the filesystem.

        For example, `-Users-joshpeak-play-claude-code-sessions` could be:
        - /Users/joshpeak/play/claude-code-sessions (valid if this path exists)
        - /Users/joshpeak/play/claude/code/sessions (also possible)

        We use a greedy algorithm: at each step, find the longest path segment
        that exists as a valid directory.
        """
        if not project_id.startswith("-"):
            # Not a valid encoded path
            return None

        # Remove leading '-' which represents root '/'
        encoded = project_id[1:]
        if not encoded:
            return None

        decoded_path = self._decode_path_greedy(encoded)
        if decoded_path is None:
            return None

        return ProjectInfo(
            project_id=project_id,
            project_path=decoded_path,
            project_name=decoded_path.name,
            resolution_source="heuristic",
        )

    def _decode_path_greedy(self, encoded: str) -> Path | None:
        """
        Decode an encoded path using greedy filesystem validation.

        At each step, we try to find the longest valid path segment.
        """
        parts = encoded.split("-")
        if not parts:
            return None

        current_path = Path("/")
        i = 0

        while i < len(parts):
            # Try progressively longer segments
            found = False
            for j in range(len(parts), i, -1):
                segment = "-".join(parts[i:j])
                candidate = current_path / segment

                # Check if this is a valid directory (or file for the last segment)
                if candidate.exists():
                    current_path = candidate
                    i = j
                    found = True
                    break

            if not found:
                # No valid segment found; the path doesn't exist
                # Return None since we can't validate this path
                return None

        return current_path if current_path != Path("/") else None

    def _extract_name_from_id(self, project_id: str) -> str:
        """
        Extract a human-friendly name from the project ID.

        Uses the last segment that looks like a project name.
        """
        # Remove leading dash and split
        clean_id = project_id.lstrip("-")
        parts = clean_id.split("-")

        # Skip common path prefixes to find the actual project name
        skip_prefixes = {"Users", "home", "var", "tmp", "opt"}
        for i, part in enumerate(parts):
            if part not in skip_prefixes:
                # Return the rest joined by '-' as it might be a hyphenated name
                return "-".join(parts[i:]) if i > 0 else parts[-1]

        return parts[-1] if parts else project_id

    def resolve_all(self) -> Iterator[ProjectInfo]:
        """
        Resolve all projects in the projects directory.

        Yields:
            ProjectInfo for each project directory found.
        """
        if not self.projects_path.is_dir():
            return

        for item in self.projects_path.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                yield self.resolve(item.name)

    def build_mapping(self) -> dict[str, ProjectInfo]:
        """
        Build a complete mapping of all project IDs to their info.

        Returns:
            Dictionary mapping project_id to ProjectInfo.
        """
        return {info.project_id: info for info in self.resolve_all()}

    def get_friendly_name(self, project_id: str) -> str:
        """
        Get a human-friendly display name for a project.

        This is a convenience method that returns just the name.
        """
        return self.resolve(project_id).project_name

    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        self._cache.clear()


def encode_path_to_project_id(path: Path | str) -> str:
    """
    Encode a filesystem path to a Claude Code project ID.

    This is the inverse of the resolution operation - useful for testing
    and for understanding the encoding scheme.

    Args:
        path: The filesystem path to encode.

    Returns:
        The encoded project ID string.

    Example:
        >>> encode_path_to_project_id("/Users/josh/myproject")
        '-Users-josh-myproject'
    """
    path_str = str(Path(path).resolve())
    return path_str.replace("/", "-")
