"""CR6 EVoC clustering — real in-memory cache; the stochastic clusterer and the GGUF
namer are injected hand-written deterministic stand-ins (dependency injection, not mocks),
exactly like ``test_claims._FakeEngine`` stands in for the model boundary.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from claude_code_sessions.database.sqlite.claim_clustering import (
    GGUF_EMBEDDING_DIM,
    cluster_claims,
    cluster_rollup,
    ensure_clustering_schema,
    select_layers,
    sync_claim_embeddings,
    _plurality_parents,
)
from claude_code_sessions.database.sqlite.claim_naming import name_clusters
from claude_code_sessions.database.sqlite.claims import ensure_claims_schema
from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.project_resolver import ProjectResolver

PID = "-Users-dev-play-proj"
PROJECT_PATH = "/Users/dev/play/proj"


def _cache() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_claims_schema(conn)
    ensure_clustering_schema(conn)
    return conn


def _index(tmp_path: Path) -> ProjectResolver:
    pdir = tmp_path / "projects" / PID
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": PROJECT_PATH}]}), encoding="utf-8"
    )
    return ProjectResolver(tmp_path / "projects")


def _seed_session_events(conn: sqlite3.Connection, sid: str) -> int:
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"f-{sid}", PID, sid),
    )
    sf = cur.lastrowid
    conn.execute(
        """INSERT INTO events
               (event_type, msg_kind, message_content, timestamp, session_id,
                project_id, source_file_id, line_number, raw_json)
           VALUES ('user', 'human', 'prompt', '2026-01-15T00:00:00Z', ?, ?, ?, 1, '')""",
        (sid, PID, sf),
    )
    return int(sf or 0)


def _seed_claim(
    conn: sqlite3.Connection, sid: str, lens: str, idx: int, claim: str,
    *, model: str = "M", embedding: bytes | None = None,
) -> None:
    conn.execute(
        """INSERT INTO session_claims
               (project_id, session_id, model, lens, claim_index, claim,
                embedding, content_hash, generated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'h', '2026-01-15T00:00:00Z')""",
        (PID, sid, model, lens, idx, claim, embedding),
    )


def _blob(seed: int) -> bytes:
    """A deterministic unit-norm 768-d float32 vector blob (a stand-in muninn_embed)."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=GGUF_EMBEDDING_DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tobytes()


class _GridClusterer:
    """Deterministic 2-layer clusterer: fine = idx//3 (triples), coarse = idx//9. Adapts to
    any N via ``fit_predict`` so the injected-clusterer path is exercised without
    hand-listing labels. persistence picks the coarse layer as 'best' (tests the step-down
    in :func:`select_layers`)."""

    def __init__(self) -> None:
        self.cluster_layers_: list[Any] = []
        self.membership_strength_layers_: list[Any] = []
        self.persistence_scores_: list[float] = []

    def fit_predict(self, X: Any) -> Any:
        n = len(X)
        fine = np.array([i // 3 for i in range(n)], dtype=np.int64)
        coarse = np.array([i // 9 for i in range(n)], dtype=np.int64)
        self.cluster_layers_ = [fine, coarse]
        self.membership_strength_layers_ = [np.ones(n), np.ones(n)]
        self.persistence_scores_ = [0.5, 0.9]  # coarse 'best' → fine steps down to layer 0
        return fine


class _CountingNamer:
    """Names a cluster as ``<lens>-c<id>`` and counts calls (to prove the source-hash cache
    short-circuits the second run)."""

    def __init__(self) -> None:
        self.calls = 0

    def name(self, model: str, prompt: str) -> str:
        self.calls += 1
        return json.dumps({"name": f"thread-{self.calls}"})


# --- pure helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    "n_layers,persistence,expected",
    [
        (1, [0.0], (0, 0)),  # single layer → degenerate one-level tree
        (3, [0.2, 0.9, 0.1], (2, 1)),  # best=index1 → coarse=2, fine=1
        (3, [0.2, 0.1, 0.9], (2, 1)),  # best=coarsest → step down (fine=1, coarse=2)
        (2, [0.9, 0.1], (1, 0)),
    ],
)
def test_select_layers(n_layers: int, persistence: list[float], expected: tuple[int, int]) -> None:
    assert select_layers(n_layers, persistence) == expected


def test_plurality_parents_breaks_chains_by_vote() -> None:
    fine = np.array([0, 0, 0, 1, 1, -1])  # fine cluster 1's points...
    coarse = np.array([0, 0, 0, 1, 0, 0])  # ...split 1×coarse-1, 1×coarse-0 → plurality 0
    parents = _plurality_parents(fine, coarse)
    assert parents[0] == 0
    assert parents[1] == 0  # plurality, not the single coarse-1 vote
    assert -1 not in parents  # noise contributes no cluster


# --- sync embeddings ---------------------------------------------------------


def test_sync_embeddings_one_call_per_concept() -> None:
    conn = _cache()
    _seed_session_events(conn, "s1")
    _seed_session_events(conn, "s2")
    _seed_claim(conn, "s1", "tasks", 0, "Refactor the Makefile")
    _seed_claim(conn, "s2", "tasks", 0, "refactor the makefile")  # same concept, other session
    _seed_claim(conn, "s1", "tasks", 1, "Add a CLI flag")
    conn.commit()

    calls: list[str] = []

    def embed(text: str) -> bytes:
        calls.append(text)
        return _blob(abs(hash(text)) % 1000)

    written = sync_claim_embeddings(conn, "M", embed)
    assert written == 3  # all three rows filled
    assert len(calls) == 2  # but only two DISTINCT concepts embedded
    nulls = conn.execute(
        "SELECT COUNT(*) FROM session_claims WHERE model='M' AND embedding IS NULL"
    ).fetchone()[0]
    assert nulls == 0


# --- clustering: singleton boundary ------------------------------------------


def test_cluster_claims_singleton_below_viable_n() -> None:
    conn = _cache()
    _seed_session_events(conn, "s1")
    for i in range(3):  # 3 concepts < viable_n() (16)
        _seed_claim(conn, "s1", "tasks", i, f"task number {i}", embedding=_blob(i))
    conn.commit()

    stats = cluster_claims(conn, "M")
    assert stats["tasks"]["used_singleton"] is True
    assert stats["tasks"]["n_concepts"] == 3
    meta = conn.execute(
        "SELECT n_layers, fine_layer, coarse_layer, used_singleton FROM claim_cluster_meta "
        "WHERE model='M' AND lens='tasks'"
    ).fetchone()
    assert (meta["n_layers"], meta["fine_layer"], meta["coarse_layer"], meta["used_singleton"]) == (
        1, 0, 0, 1,
    )
    # Each concept is its own cluster; every claim_id has a membership row.
    n_clusters = conn.execute(
        "SELECT COUNT(*) FROM claim_clusters WHERE model='M' AND lens='tasks'"
    ).fetchone()[0]
    assert n_clusters == 3
    n_members = conn.execute(
        "SELECT COUNT(*) FROM claim_cluster_membership WHERE model='M' AND lens='tasks'"
    ).fetchone()[0]
    assert n_members == 3


# --- clustering: injected grid clusterer (audit trail + parent links) --------


def _seed_grid(conn: sqlite3.Connection, n: int = 18) -> None:
    """n distinct task concepts spread across two sessions (provenance)."""
    _seed_session_events(conn, "s1")
    _seed_session_events(conn, "s2")
    for i in range(n):
        sid = "s1" if i % 2 == 0 else "s2"
        _seed_claim(conn, sid, "tasks", i, f"distinct concept {i}", embedding=_blob(i))
    conn.commit()


def test_cluster_claims_builds_layers_membership_and_parents() -> None:
    conn = _cache()
    _seed_grid(conn, 18)  # ≥ viable_n() → uses the injected clusterer

    stats = cluster_claims(conn, "M", clusterer_factory=_GridClusterer)
    s = stats["tasks"]
    assert s["used_singleton"] is False
    assert s["n_layers"] == 2
    assert (s["fine_layer"], s["coarse_layer"]) == (0, 1)
    assert s["n_fine_clusters"] == 6  # 18 concepts // 3

    # Audit trail: every claim_id has a membership row at EVERY layer (all layers persisted).
    members_per_layer = conn.execute(
        """SELECT layer, COUNT(*) AS n FROM claim_cluster_membership
           WHERE model='M' AND lens='tasks' GROUP BY layer ORDER BY layer"""
    ).fetchall()
    assert [(r["layer"], r["n"]) for r in members_per_layer] == [(0, 18), (1, 18)]

    # Parent links: fine cluster 0 (concepts 0,1,2 → coarse 0) parents to 0;
    # fine cluster 3 (concepts 9,10,11 → coarse 1) parents to 1.
    parents = {
        r["cluster_id"]: r["parent_cluster_id"]
        for r in conn.execute(
            "SELECT cluster_id, parent_cluster_id FROM claim_clusters "
            "WHERE model='M' AND lens='tasks' AND layer=0"
        )
    }
    assert parents[0] == 0
    assert parents[3] == 1


# --- naming: cache by source hash, skip noise --------------------------------


def test_name_clusters_caches_and_is_idempotent() -> None:
    conn = _cache()
    _seed_grid(conn, 18)
    cluster_claims(conn, "M", clusterer_factory=_GridClusterer)

    namer = _CountingNamer()
    first = name_clusters(conn, "M", namer)
    assert first > 0
    calls_after_first = namer.calls
    # Every surfaced cluster (layers 0 and 1) got a name.
    unnamed = conn.execute(
        """SELECT COUNT(*) FROM claim_clusters
           WHERE model='M' AND lens='tasks' AND layer IN (0,1) AND cluster_id>=0 AND name IS NULL"""
    ).fetchone()[0]
    assert unnamed == 0

    # Second run: members unchanged → source-hash cache hit → zero new model calls.
    second = name_clusters(conn, "M", namer)
    assert second == 0
    assert namer.calls == calls_after_first


# --- leaf rollup tagged by fine cluster --------------------------------------


def test_cluster_rollup_tags_leaves_and_counts_sessions(tmp_path: Path) -> None:
    conn = _cache()
    resolver = _index(tmp_path)
    _seed_grid(conn, 18)
    cluster_claims(conn, "M", clusterer_factory=_GridClusterer)

    written = cluster_rollup(conn, "M", "month", resolver)
    assert written > 0

    # Leaf rows at the project leaf scope carry a fine cluster_id and provenance.
    rows = conn.execute(
        """SELECT claim, cluster_id, count, source_session_ids FROM rollup_clusters
           WHERE model='M' AND lens='tasks' AND scope_path=? AND time_granularity='month'
           ORDER BY claim_index""",
        ("play/proj",),
    ).fetchall()
    assert rows, "expected leaf rollup rows at the project scope"
    for r in rows:
        assert r["cluster_id"] >= 0  # every concept was clustered (no noise from the grid)
        assert len(json.loads(r["source_session_ids"])) == r["count"]
    # Concept 0 lived only in s1 → count 1; the 18 concepts are all distinct → 18 leaves.
    assert len(rows) == 18


def test_cluster_rollup_clears_stale_leaves(tmp_path: Path) -> None:
    """Re-running the rollup after claims are dropped must rebuild from scratch, not strand
    the removed leaves (full delete-then-rebuild per (model, grain))."""
    conn = _cache()
    resolver = _index(tmp_path)
    _seed_grid(conn, 18)
    cluster_claims(conn, "M", clusterer_factory=_GridClusterer)
    cluster_rollup(conn, "M", "month", resolver)
    root = "SELECT COUNT(*) FROM rollup_clusters WHERE model='M' AND scope_path=''"
    assert conn.execute(root).fetchone()[0] == 18

    conn.execute("DELETE FROM session_claims WHERE model='M' AND claim_index >= 9")
    conn.commit()
    cluster_rollup(conn, "M", "month", resolver)
    assert conn.execute(root).fetchone()[0] == 9  # stale leaves cleared, not stranded


# --- real EVoC integration (guards against library API drift) ----------------


def test_cluster_claims_runs_real_evoc() -> None:
    """Exercise the production ``default_clusterer_factory`` (real numba-backed EVoC) — not
    the injected fake. Asserts the structural invariants that hold regardless of EVoC's
    exact partitioning, so it can't flake on cluster-count quirks."""
    conn = _cache()
    _seed_session_events(conn, "s1")
    # 4 well-separated blobs × 8 concepts = 32 (≥ viable_n) → the real-EVoC path runs.
    rng = np.random.default_rng(0)
    centres = rng.normal(0, 50, size=(4, GGUF_EMBEDDING_DIM)).astype(np.float32)
    n = 0
    for b, centre in enumerate(centres):
        for j in range(8):
            v = centre + rng.normal(0, 0.1, size=GGUF_EMBEDDING_DIM).astype(np.float32)
            v /= np.linalg.norm(v)
            _seed_claim(conn, "s1", "tasks", n, f"blob {b} concept {j}", embedding=v.tobytes())
            n += 1
    conn.commit()

    stats = cluster_claims(conn, "M")  # default (real) clusterer
    assert stats["tasks"]["used_singleton"] is False
    assert stats["tasks"]["n_concepts"] == 32
    # Invariant: every concept has a membership row at every persisted layer.
    n_layers = stats["tasks"]["n_layers"]
    per_layer = conn.execute(
        """SELECT layer, COUNT(*) AS n FROM claim_cluster_membership
           WHERE model='M' AND lens='tasks' GROUP BY layer"""
    ).fetchall()
    assert len(per_layer) == n_layers
    assert all(r["n"] == 32 for r in per_layer)
    # Invariant: claim_clusters member counts sum to 32 at each layer.
    layer0_total = conn.execute(
        "SELECT SUM(member_claim_count) FROM claim_clusters "
        "WHERE model='M' AND lens='tasks' AND layer=0"
    ).fetchone()[0]
    assert layer0_total == 32
