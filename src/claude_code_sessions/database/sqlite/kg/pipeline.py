"""KG pipeline orchestrator — sync_kg().

Called from ``CacheManager.update()`` after ``sync_embeddings()`` on every
server start. Each phase is incremental, so warm starts are O(1).

Phase order:
  1. NER + RE          — extract entities and relations from new chunks
                         using the GLiNER2 zero-shot model (DeBERTa, ~205 MB)
  2. entity_embeddings — embed unique entity names into HNSW (NomicEmbed)
  3. entity_resolution — collapse synonyms via muninn_extract_er
  4. communities       — Leiden community detection at multiple resolutions
  5. community_naming  — LLM-generated labels (the only phase that needs a
                         chat-model GGUF; loaded lazily inside that phase)
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import TypedDict

from claude_code_sessions.database.sqlite.kg.communities import sync_communities
from claude_code_sessions.database.sqlite.kg.community_naming import sync_community_labels
from claude_code_sessions.database.sqlite.kg.entity_embeddings import sync_entity_embeddings
from claude_code_sessions.database.sqlite.kg.entity_resolution import sync_entity_clusters
from claude_code_sessions.database.sqlite.kg.ner_re import sync_ner_re

log = logging.getLogger(__name__)


class KGSyncResult(TypedDict):
    entities_added: int
    relations_added: int
    entity_embeddings_added: int
    nodes: int
    edges: int
    leiden_assignments: int
    cluster_labels: int
    community_labels: int


def sync_kg(conn: sqlite3.Connection) -> KGSyncResult:
    """Run every KG phase against ``conn``.

    GLiNER2 weights download on first call (~205 MB). The chat-model GGUF
    needed by ``community_naming`` is loaded inside that phase only —
    server starts that have nothing new to label avoid the 2.6 GiB memory
    cost entirely.

    Per ``/escalators-not-stairs``: this function never silently skips a
    phase. If a phase fails, the exception propagates and the cache stays
    in a known-stale state for the next run.
    """
    log.info("──────── kg pipeline ────────")
    t0 = time.monotonic()

    # 1. NER + RE via GLiNER2.
    entities_added, relations_added = sync_ner_re(conn)

    # 2. Entity embeddings (uses the same NomicEmbed GGUF as chunk embeddings).
    entity_embeddings_added = sync_entity_embeddings(conn)

    # 3. Entity resolution (rebuild nodes/edges).
    nodes, edges = sync_entity_clusters(conn)

    # 4. Communities (Leiden, multi-resolution).
    leiden_assignments = sync_communities(conn)

    # 5. Community naming — registers the chat-model GGUF lazily.
    cluster_labels, community_labels = sync_community_labels(conn)

    log.info(
        "──── kg pipeline complete in %.1f s "
        "(ents +%d, rels +%d, ent-vecs +%d, nodes %d, edges %d, "
        "leiden %d, cluster-labels %d, community-labels %d) ────",
        time.monotonic() - t0,
        entities_added,
        relations_added,
        entity_embeddings_added,
        nodes,
        edges,
        leiden_assignments,
        cluster_labels,
        community_labels,
    )
    return KGSyncResult(
        entities_added=entities_added,
        relations_added=relations_added,
        entity_embeddings_added=entity_embeddings_added,
        nodes=nodes,
        edges=edges,
        leiden_assignments=leiden_assignments,
        cluster_labels=cluster_labels,
        community_labels=community_labels,
    )
