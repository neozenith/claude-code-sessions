"""Community-naming phase — LLM-generated labels for clusters and communities.

Calls ``muninn_chat()`` once per group (entity cluster, then Leiden community
at each resolution), assembling a small prompt with the group's member names
and committing each label as soon as it lands. This keeps memory bounded
and makes the phase resumable: a crash at row N means the next run starts
at row N (already-labelled groups are skipped).

Earlier versions used the bulk ``muninn_label_groups`` TVF which ran the
entire phase as one atomic INSERT … SELECT. That approach OOM-killed the
process on large corpora (~40 k clusters) because the TVF and SQLite both
held intermediate state until the transaction committed. The per-row
approach trades a small amount of throughput for crash-resilience and
visible progress.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections import defaultdict
from datetime import UTC, datetime

from claude_code_sessions.database.sqlite.kg.runtime import (
    CHAT_MODEL_NAME,
    ensure_chat_model_downloaded,
    register_chat_model,
)

log = logging.getLogger(__name__)


_MIN_GROUP_SIZE = 3
_MAX_MEMBERS_IN_PROMPT = 10
_LABEL_PROMPT = "Output ONLY a concise label (3-8 words). No explanation."
_COMMIT_EVERY = 10

# The cytoscape page reads ``community_labels`` filtered by the active
# resolution. We label communities at the default page resolution ONLY,
# because labelling all three resolutions of a 40k-node graph means
# tens of thousands of LLM calls (24+ hours on a 4B GGUF). Other
# resolutions fall back to ``community #N`` placeholders, which the
# frontend already handles. ``DEFAULT_RESOLUTION`` mirrors
# ``payload.py``'s default; keep them in sync.
_LABEL_RESOLUTION = 0.25

# Skip entity_cluster_labels entirely — they are not consumed by the
# current cytoscape page. Re-enabling is a one-line change here if a
# future UI surfaces them.
_LABEL_ENTITY_CLUSTERS = False


def sync_community_labels(conn: sqlite3.Connection) -> tuple[int, int]:
    """Rebuild community_labels (Leiden) — and entity_cluster_labels last.

    Returns ``(entity_cluster_label_count, community_label_count)``.

    Lazily registers the chat-model GGUF on first use. Resumable: if a
    previous run stopped mid-phase, this skips groups that already have
    a label.

    Order matters: the cytoscape page consumes ``community_labels`` for
    its community-parent compound boxes, so we name those FIRST. The
    ``entity_cluster_labels`` table is internal (synonym-group labels)
    and not displayed by the current UI; we still build it but only after
    the user-visible labels are committed.
    """
    if not _has_groups_to_label(conn):
        log.info("  community-naming: nothing to label — skipping chat model load")
        return 0, 0

    chat_path = ensure_chat_model_downloaded()
    register_chat_model(conn, chat_path)

    now = datetime.now(UTC).isoformat()
    t0 = time.monotonic()
    cl_count = _label_leiden_communities(conn, now)
    if _LABEL_ENTITY_CLUSTERS:
        ecl_count = _label_entity_clusters(conn, now)
    else:
        ecl_count = int(conn.execute("SELECT count(*) FROM entity_cluster_labels").fetchone()[0])
        log.info("  community-naming: skipping entity_cluster_labels (UI does not use)")
    log.info(
        "  community-naming: %d community labels + %d cluster labels in %.1f s",
        cl_count,
        ecl_count,
        time.monotonic() - t0,
    )
    return ecl_count, cl_count


def _has_groups_to_label(conn: sqlite3.Connection) -> bool:
    """True if any cluster or Leiden community needs labelling."""
    try:
        cluster_rows = int(conn.execute("SELECT count(*) FROM entity_clusters").fetchone()[0])
        leiden_rows = int(conn.execute("SELECT count(*) FROM leiden_communities").fetchone()[0])
    except sqlite3.OperationalError:
        return False
    return (cluster_rows + leiden_rows) > 0


def _label_one(conn: sqlite3.Connection, members: list[str]) -> str:
    """Run muninn_chat on a member list and return the cleaned label.

    ``muninn_chat`` is a 2-arg SQL function: ``(model_name, prompt)``.
    A third argument is interpreted as a GBNF grammar by llama.cpp,
    so we fold the system instruction into a single prompt string.
    """
    sample = members[:_MAX_MEMBERS_IN_PROMPT]
    member_block = "\n".join(f"- {m}" for m in sample)
    prompt = f"{_LABEL_PROMPT}\n\nGroup members\n{member_block}\n\nLabel:"
    row = conn.execute(
        "SELECT muninn_chat(?, ?)",
        (CHAT_MODEL_NAME, prompt),
    ).fetchone()
    raw = (row[0] if row and row[0] else "").strip()
    # Strip leading bullet/quote chars, take first line.
    first_line = raw.splitlines()[0] if raw else ""
    return first_line.strip(" \"'`*-•") or "(unlabelled)"


def _label_entity_clusters(conn: sqlite3.Connection, now: str) -> int:
    """Label every entity cluster with ≥3 members. Resumable."""
    # Build {canonical: [member_name_with_type, ...]} from entity_clusters.
    # We only consider clusters with ≥3 members to match the legacy TVF
    # behaviour and avoid wasting LLM calls on singletons.
    rows = conn.execute(
        """
        SELECT ec.canonical,
               ec.name || ' (' || COALESCE(n.entity_type, 'unknown') || ')' AS member
        FROM entity_clusters ec
        LEFT JOIN nodes n ON n.name = ec.canonical
        """
    ).fetchall()
    grouped: dict[str, list[str]] = defaultdict(list)
    for canonical, member in rows:
        grouped[str(canonical)].append(str(member))

    eligible = [(c, ms) for c, ms in grouped.items() if len(ms) >= _MIN_GROUP_SIZE]
    if not eligible:
        log.info(
            "  community-naming: no entity clusters with >= %d members",
            _MIN_GROUP_SIZE,
        )
        return int(conn.execute("SELECT count(*) FROM entity_cluster_labels").fetchone()[0])

    # Resume support — skip canonicals we've already labelled.
    already = {
        str(r[0]) for r in conn.execute("SELECT canonical FROM entity_cluster_labels").fetchall()
    }
    todo = [(c, ms) for c, ms in eligible if c not in already]
    log.info(
        "  community-naming: %d entity clusters need labels (%d already done, %d eligible total)",
        len(todo),
        len(already),
        len(eligible),
    )
    if not todo:
        return int(conn.execute("SELECT count(*) FROM entity_cluster_labels").fetchone()[0])

    t0 = time.monotonic()
    last_log = t0
    for i, (canonical, members) in enumerate(todo, start=1):
        label = _label_one(conn, members)
        conn.execute(
            "INSERT OR REPLACE INTO entity_cluster_labels"
            " (canonical, label, member_count, model, generated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (canonical, label, len(members), CHAT_MODEL_NAME, now),
        )
        if i % _COMMIT_EVERY == 0:
            conn.commit()

        now_t = time.monotonic()
        if now_t - last_log >= 10.0 or i == len(todo):
            rate = i / (now_t - t0) if now_t > t0 else 0
            eta = (len(todo) - i) / rate if rate > 0 else 0
            log.info(
                "  community-naming/clusters: %d/%d (%.2f labels/s, ETA %.0f s)",
                i,
                len(todo),
                rate,
                eta,
            )
            last_log = now_t

    conn.commit()
    return int(conn.execute("SELECT count(*) FROM entity_cluster_labels").fetchone()[0])


def _label_leiden_communities(conn: sqlite3.Connection, now: str) -> int:
    """Label every Leiden community with ≥3 members at the page resolution. Resumable.

    Restricts to ``_LABEL_RESOLUTION`` (the cytoscape page's default) so
    the LLM workload is bounded — labelling all three resolutions on a
    40k-node graph would be tens of thousands of inferences.
    """
    rows = conn.execute(
        """
        SELECT lc.resolution,
               lc.community_id,
               lc.node || ' (' || COALESCE(n.entity_type, 'unknown') || ')' AS member
        FROM leiden_communities lc
        LEFT JOIN nodes n ON n.name = lc.node
        WHERE lc.resolution = ?
        """,
        (_LABEL_RESOLUTION,),
    ).fetchall()
    if not rows:
        return 0

    grouped: dict[tuple[float, int], list[str]] = defaultdict(list)
    for resolution, community_id, member in rows:
        grouped[(float(resolution), int(community_id))].append(str(member))

    eligible = [(k, ms) for k, ms in grouped.items() if len(ms) >= _MIN_GROUP_SIZE]
    if not eligible:
        log.info(
            "  community-naming: no Leiden communities with >= %d members",
            _MIN_GROUP_SIZE,
        )
        return int(conn.execute("SELECT count(*) FROM community_labels").fetchone()[0])

    already_rows = conn.execute("SELECT resolution, community_id FROM community_labels").fetchall()
    already = {(float(r[0]), int(r[1])) for r in already_rows}
    todo = [(k, ms) for k, ms in eligible if k not in already]
    log.info(
        "  community-naming: %d Leiden communities to label (%d done, %d eligible)",
        len(todo),
        len(already),
        len(eligible),
    )
    if not todo:
        return int(conn.execute("SELECT count(*) FROM community_labels").fetchone()[0])

    t0 = time.monotonic()
    last_log = t0
    for i, ((resolution, community_id), members) in enumerate(todo, start=1):
        label = _label_one(conn, members)
        conn.execute(
            "INSERT OR REPLACE INTO community_labels"
            " (resolution, community_id, label, member_count, model, generated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (resolution, community_id, label, len(members), CHAT_MODEL_NAME, now),
        )
        if i % _COMMIT_EVERY == 0:
            conn.commit()

        now_t = time.monotonic()
        if now_t - last_log >= 10.0 or i == len(todo):
            rate = i / (now_t - t0) if now_t > t0 else 0
            eta = (len(todo) - i) / rate if rate > 0 else 0
            log.info(
                "  community-naming/leiden: %d/%d (%.2f labels/s, ETA %.0f s)",
                i,
                len(todo),
                rate,
                eta,
            )
            last_log = now_t

    conn.commit()
    return int(conn.execute("SELECT count(*) FROM community_labels").fetchone()[0])
