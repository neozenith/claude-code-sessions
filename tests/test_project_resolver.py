"""
Comprehensive tests for the ProjectResolver utility.

Tests cover:
- Resolution from sessions-index.json (primary strategy)
- Resolution from path heuristics (fallback strategy)
- Caching behavior
- Edge cases and error handling
- The encode_path_to_project_id utility function
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_code_sessions.project_resolver import (
    ProjectInfo,
    ProjectResolver,
    encode_path_to_project_id,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_projects_dir(tmp_path: Path) -> Path:
    """Create a temporary projects directory for testing."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    return projects_dir


@pytest.fixture
def project_with_index(temp_projects_dir: Path) -> tuple[str, Path, Path]:
    """
    Create a project directory with a valid sessions-index.json.

    Returns:
        Tuple of (project_id, project_dir, original_path)
    """
    project_id = "-Users-testuser-code-myproject"
    original_path = Path("/Users/testuser/code/myproject")

    project_dir = temp_projects_dir / project_id
    project_dir.mkdir()

    # Create sessions-index.json
    index_data = {
        "version": 1,
        "entries": [
            {
                "sessionId": "abc-123",
                "projectPath": str(original_path),
                "fullPath": f"/Users/testuser/.claude/projects/{project_id}/abc-123.jsonl",
                "created": "2025-01-01T00:00:00.000Z",
            },
            {
                "sessionId": "def-456",
                "projectPath": str(original_path),  # Same projectPath
                "fullPath": f"/Users/testuser/.claude/projects/{project_id}/def-456.jsonl",
                "created": "2025-01-02T00:00:00.000Z",
            },
        ],
    }

    (project_dir / "sessions-index.json").write_text(json.dumps(index_data))

    return project_id, project_dir, original_path


@pytest.fixture
def project_without_index(temp_projects_dir: Path, tmp_path: Path) -> tuple[str, Path, Path]:
    """
    Create a project directory without sessions-index.json.

    Also creates the actual path on the filesystem for heuristic resolution.

    Returns:
        Tuple of (project_id, project_dir, actual_path)
    """
    # Create a real directory structure for heuristic resolution
    actual_path = tmp_path / "realproject"
    actual_path.mkdir()

    # Encode the path
    project_id = encode_path_to_project_id(actual_path)

    project_dir = temp_projects_dir / project_id
    project_dir.mkdir()

    return project_id, project_dir, actual_path


@pytest.fixture
def project_with_empty_index(temp_projects_dir: Path) -> tuple[str, Path]:
    """
    Create a project directory with an empty sessions-index.json.

    Returns:
        Tuple of (project_id, project_dir)
    """
    project_id = "-Users-testuser-emptyproject"
    project_dir = temp_projects_dir / project_id
    project_dir.mkdir()

    # Create empty sessions-index.json
    index_data = {"version": 1, "entries": []}
    (project_dir / "sessions-index.json").write_text(json.dumps(index_data))

    return project_id, project_dir


@pytest.fixture
def project_with_malformed_index(temp_projects_dir: Path) -> tuple[str, Path]:
    """
    Create a project directory with a malformed sessions-index.json.

    Returns:
        Tuple of (project_id, project_dir)
    """
    project_id = "-Users-testuser-badproject"
    project_dir = temp_projects_dir / project_id
    project_dir.mkdir()

    # Create malformed JSON
    (project_dir / "sessions-index.json").write_text("{ invalid json }")

    return project_id, project_dir


@pytest.fixture
def resolver(temp_projects_dir: Path) -> ProjectResolver:
    """Create a ProjectResolver instance."""
    return ProjectResolver(projects_path=temp_projects_dir)


# =============================================================================
# Tests: ProjectInfo dataclass
# =============================================================================


class TestProjectInfo:
    """Tests for the ProjectInfo dataclass."""

    def test_is_resolved_with_path(self) -> None:
        """Test is_resolved returns True when project_path is set."""
        info = ProjectInfo(
            project_id="-test",
            project_path=Path("/test"),
            project_name="test",
            resolution_source="sessions-index",
        )
        assert info.is_resolved is True

    def test_is_resolved_without_path(self) -> None:
        """Test is_resolved returns False when project_path is None."""
        info = ProjectInfo(
            project_id="-test",
            project_path=None,
            project_name="test",
            resolution_source="unresolved",
        )
        assert info.is_resolved is False

    def test_frozen_dataclass(self) -> None:
        """Test that ProjectInfo is immutable."""
        info = ProjectInfo(
            project_id="-test",
            project_path=Path("/test"),
            project_name="test",
            resolution_source="sessions-index",
        )
        with pytest.raises(AttributeError):
            info.project_id = "-other"  # type: ignore[misc]


# =============================================================================
# Tests: ProjectResolver initialization
# =============================================================================


class TestProjectResolverInit:
    """Tests for ProjectResolver initialization."""

    def test_init_with_valid_path(self, temp_projects_dir: Path) -> None:
        """Test initialization with a valid projects path."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)
        assert resolver.projects_path == temp_projects_dir

    def test_init_with_invalid_path(self, tmp_path: Path) -> None:
        """Test initialization with a non-existent path raises ValueError."""
        nonexistent = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="does not exist"):
            ProjectResolver(projects_path=nonexistent)


# =============================================================================
# Tests: Resolution from sessions-index.json
# =============================================================================


class TestResolveFromSessionsIndex:
    """Tests for resolution using sessions-index.json."""

    def test_resolve_with_valid_index(
        self,
        resolver: ProjectResolver,
        project_with_index: tuple[str, Path, Path],
    ) -> None:
        """Test resolution when sessions-index.json contains projectPath."""
        project_id, _, original_path = project_with_index

        info = resolver.resolve(project_id)

        assert info.project_id == project_id
        assert info.project_path == original_path
        assert info.project_name == "myproject"
        assert info.resolution_source == "sessions-index"
        assert info.is_resolved is True

    def test_resolve_with_empty_entries(
        self,
        resolver: ProjectResolver,
        project_with_empty_index: tuple[str, Path],
    ) -> None:
        """Test resolution when sessions-index.json has empty entries."""
        project_id, _ = project_with_empty_index

        info = resolver.resolve(project_id)

        # Should fall through to unresolved since no path exists
        assert info.project_id == project_id
        assert info.project_path is None
        assert info.resolution_source == "unresolved"

    def test_resolve_with_malformed_json(
        self,
        resolver: ProjectResolver,
        project_with_malformed_index: tuple[str, Path],
    ) -> None:
        """Test resolution when sessions-index.json is malformed."""
        project_id, _ = project_with_malformed_index

        info = resolver.resolve(project_id)

        # Should fall through gracefully
        assert info.project_id == project_id
        assert info.project_path is None
        assert info.resolution_source == "unresolved"


# =============================================================================
# Tests: Resolution from path heuristics
# =============================================================================


class TestResolveFromHeuristics:
    """Tests for resolution using path heuristics."""

    def test_resolve_with_existing_path(
        self,
        resolver: ProjectResolver,
        project_without_index: tuple[str, Path, Path],
    ) -> None:
        """Test resolution when the encoded path exists on the filesystem."""
        project_id, _, actual_path = project_without_index

        info = resolver.resolve(project_id)

        assert info.project_id == project_id
        assert info.project_path == actual_path
        assert info.project_name == actual_path.name
        assert info.resolution_source == "heuristic"
        assert info.is_resolved is True

    def test_resolve_invalid_encoded_path(self, resolver: ProjectResolver) -> None:
        """Test resolution with invalid encoded path format."""
        # Create a project dir with invalid format (no leading dash)
        project_id = "invalid-format"
        (resolver.projects_path / project_id).mkdir()

        info = resolver.resolve(project_id)

        # Should not be resolved via heuristics
        assert info.project_path is None
        assert info.resolution_source == "unresolved"

    def test_resolve_nonexistent_path(
        self,
        temp_projects_dir: Path,
    ) -> None:
        """Test resolution when the decoded path doesn't exist."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)
        project_id = "-nonexistent-path-on-filesystem"
        (temp_projects_dir / project_id).mkdir()

        info = resolver.resolve(project_id)

        # Path doesn't exist, so should be unresolved
        assert info.project_path is None
        assert info.resolution_source == "unresolved"


# =============================================================================
# Tests: Path encoding/decoding
# =============================================================================


class TestPathEncoding:
    """Tests for path encoding utilities."""

    def test_encode_simple_path(self) -> None:
        """Test encoding a simple path."""
        result = encode_path_to_project_id("/Users/josh/myproject")
        assert result == "-Users-josh-myproject"

    def test_encode_path_with_hyphen(self) -> None:
        """Test encoding a path that contains hyphens."""
        result = encode_path_to_project_id("/Users/josh/my-cool-project")
        assert result == "-Users-josh-my-cool-project"

    def test_encode_root_path(self) -> None:
        """Test encoding the root path."""
        result = encode_path_to_project_id("/")
        assert result == "-"

    def test_encode_relative_path(self) -> None:
        """Test encoding a relative path (gets resolved to absolute)."""
        result = encode_path_to_project_id("relative/path")
        # This will resolve to an absolute path, so it should start with '-'
        assert result.startswith("-")

    def test_encode_path_object(self) -> None:
        """Test encoding a Path object."""
        result = encode_path_to_project_id(Path("/Users/josh/project"))
        assert result == "-Users-josh-project"


# =============================================================================
# Tests: Caching behavior
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""

    def test_cached_result(
        self,
        resolver: ProjectResolver,
        project_with_index: tuple[str, Path, Path],
    ) -> None:
        """Test that results are cached."""
        project_id, _, _ = project_with_index

        info1 = resolver.resolve(project_id)
        info2 = resolver.resolve(project_id)

        # Should return the same object from cache
        assert info1 is info2

    def test_clear_cache(
        self,
        resolver: ProjectResolver,
        project_with_index: tuple[str, Path, Path],
    ) -> None:
        """Test cache clearing."""
        project_id, _, _ = project_with_index

        info1 = resolver.resolve(project_id)
        resolver.clear_cache()
        info2 = resolver.resolve(project_id)

        # Should be equal but not the same object
        assert info1 == info2
        assert info1 is not info2


# =============================================================================
# Tests: resolve_all and build_mapping
# =============================================================================


class TestBulkOperations:
    """Tests for bulk resolution operations."""

    def test_resolve_all(
        self,
        temp_projects_dir: Path,
        project_with_index: tuple[str, Path, Path],
        project_without_index: tuple[str, Path, Path],
    ) -> None:
        """Test resolving all projects."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)

        results = list(resolver.resolve_all())

        assert len(results) == 2
        project_ids = {r.project_id for r in results}
        assert project_with_index[0] in project_ids
        assert project_without_index[0] in project_ids

    def test_resolve_all_skips_hidden_dirs(
        self,
        temp_projects_dir: Path,
        project_with_index: tuple[str, Path, Path],
    ) -> None:
        """Test that resolve_all skips hidden directories."""
        # Create a hidden directory
        (temp_projects_dir / ".hidden").mkdir()

        resolver = ProjectResolver(projects_path=temp_projects_dir)
        results = list(resolver.resolve_all())

        # Should only have the non-hidden project
        assert len(results) == 1
        assert results[0].project_id == project_with_index[0]

    def test_build_mapping(
        self,
        temp_projects_dir: Path,
        project_with_index: tuple[str, Path, Path],
    ) -> None:
        """Test building a complete mapping."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)

        mapping = resolver.build_mapping()

        assert project_with_index[0] in mapping
        assert mapping[project_with_index[0]].project_path == project_with_index[2]


# =============================================================================
# Tests: Friendly name extraction
# =============================================================================


class TestFriendlyNames:
    """Tests for friendly name extraction."""

    def test_get_friendly_name_from_resolved(
        self,
        resolver: ProjectResolver,
        project_with_index: tuple[str, Path, Path],
    ) -> None:
        """Test getting friendly name from resolved project."""
        project_id, _, _ = project_with_index

        name = resolver.get_friendly_name(project_id)

        assert name == "myproject"

    def test_extract_name_from_encoded_id(self, temp_projects_dir: Path) -> None:
        """Test name extraction from encoded project ID."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)

        # Create a project dir
        project_id = "-Users-josh-work-cool-project"
        (temp_projects_dir / project_id).mkdir()

        info = resolver.resolve(project_id)

        # Should extract the meaningful part
        assert "project" in info.project_name.lower() or "cool" in info.project_name.lower()


# =============================================================================
# Tests: Complex path scenarios
# =============================================================================


class TestComplexPaths:
    """Tests for complex path resolution scenarios."""

    def test_path_with_multiple_hyphens(
        self,
        temp_projects_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test resolution of paths containing multiple consecutive hyphens."""
        # Create a real path with hyphens
        actual_path = tmp_path / "my--double-hyphen"
        actual_path.mkdir()

        project_id = encode_path_to_project_id(actual_path)
        (temp_projects_dir / project_id).mkdir()

        resolver = ProjectResolver(projects_path=temp_projects_dir)
        info = resolver.resolve(project_id)

        assert info.project_path == actual_path
        assert info.resolution_source == "heuristic"

    def test_deeply_nested_path(
        self,
        temp_projects_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test resolution of deeply nested paths."""
        # Create a deeply nested directory structure
        nested_path = tmp_path / "a" / "b" / "c" / "d" / "project"
        nested_path.mkdir(parents=True)

        project_id = encode_path_to_project_id(nested_path)
        (temp_projects_dir / project_id).mkdir()

        resolver = ProjectResolver(projects_path=temp_projects_dir)
        info = resolver.resolve(project_id)

        assert info.project_path == nested_path
        assert info.project_name == "project"

    def test_index_takes_precedence_over_heuristics(
        self,
        temp_projects_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test that sessions-index.json takes precedence over heuristics."""
        # Create both: a sessions-index.json AND a matching filesystem path
        actual_path = tmp_path / "realpath"
        actual_path.mkdir()

        index_path = Path("/different/path/from/index")

        project_id = encode_path_to_project_id(actual_path)
        project_dir = temp_projects_dir / project_id
        project_dir.mkdir()

        # Add sessions-index.json with different path
        index_data = {
            "version": 1,
            "entries": [{"sessionId": "test", "projectPath": str(index_path)}],
        }
        (project_dir / "sessions-index.json").write_text(json.dumps(index_data))

        resolver = ProjectResolver(projects_path=temp_projects_dir)
        info = resolver.resolve(project_id)

        # Should use the index path, not the heuristic
        assert info.project_path == index_path
        assert info.resolution_source == "sessions-index"


# =============================================================================
# Tests: Edge cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_resolve_nonexistent_project_id(self, temp_projects_dir: Path) -> None:
        """Test resolving a project ID that doesn't exist."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)

        info = resolver.resolve("-nonexistent-project")

        # Should return unresolved info with extracted name
        assert info.project_id == "-nonexistent-project"
        assert info.project_path is None
        assert info.resolution_source == "unresolved"

    def test_empty_projects_directory(self, temp_projects_dir: Path) -> None:
        """Test with an empty projects directory."""
        resolver = ProjectResolver(projects_path=temp_projects_dir)

        results = list(resolver.resolve_all())

        assert results == []

    def test_index_with_missing_project_path_field(
        self,
        temp_projects_dir: Path,
    ) -> None:
        """Test index entries missing the projectPath field."""
        project_id = "-test-missing-field"
        project_dir = temp_projects_dir / project_id
        project_dir.mkdir()

        # Index without projectPath
        index_data = {
            "version": 1,
            "entries": [{"sessionId": "test"}],  # No projectPath
        }
        (project_dir / "sessions-index.json").write_text(json.dumps(index_data))

        resolver = ProjectResolver(projects_path=temp_projects_dir)
        info = resolver.resolve(project_id)

        # Should fall through to unresolved
        assert info.project_path is None
        assert info.resolution_source == "unresolved"
