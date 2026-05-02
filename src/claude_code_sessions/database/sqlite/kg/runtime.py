"""Runtime configuration for the KG pipeline — chat model + label registry.

The KG pipeline drives the published ``sqlite-muninn`` extension via SQL
primitives. Two model artifacts are needed:

* The **chat model** (a llama.cpp-compatible GGUF) that backs
  ``muninn_extract_ner_re()`` and ``muninn_label_groups``. Default is a
  4B-parameter Qwen3.5 Instruct quant (~2.6 GiB on disk).
* The **embedding model** — already managed by
  ``claude_code_sessions.database.sqlite.embeddings`` for chunk vectors. We
  re-use the same ``GGUF_MODEL_NAME`` registration there for entity
  embeddings.

Per ``/escalators-not-stairs``: missing chat model → fail loud with the
search paths printed and a remediation hint, never a silent skip.

## Chat-model resolution order

1. ``CLAUDE_SESSIONS_KG_CHAT_MODEL_PATH`` env var (absolute path; if set
   but missing, raises immediately — does not fall back).
2. Cached default at ``~/.claude/cache/models/Qwen3.5-4B-Q4_K_M.gguf``.
3. The sqlite-muninn benchmark models directory at
   ``~/play/sqlite-vector-graph/models/Qwen3.5-4B-Q4_K_M.gguf`` — picked
   up automatically when the developer already maintains a copy there
   (avoids re-downloading 2.6 GiB).
4. None of the above → download from ``CHAT_MODEL_URL_DEFAULT`` into the
   cache directory in (2).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chat model — drives muninn_extract_ner_re() and muninn_label_groups
# ---------------------------------------------------------------------------

CHAT_MODEL_NAME = "kg_chat"
# gemma-4-E2B-it is a 2-billion-parameter instruction-tuned model that
# produces direct short labels in ~3-4 seconds per call on CPU. Larger
# alternatives like Qwen3.5-4B can take 60×+ longer because they emit
# extended `<think>` reasoning traces before answering — disastrous for
# a phase that needs hundreds of inferences per build.
CHAT_MODEL_FILENAME_DEFAULT = "gemma-4-E2B-it-Q4_K_M.gguf"
CHAT_MODEL_URL_DEFAULT = (
    "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/"
    "gemma-4-E2B-it-Q4_K_M.gguf"
)

MODELS_DIR = Path.home() / ".claude" / "cache" / "models"

# Other locations searched before downloading. The first existing match
# wins. These are *opportunistic*: they let a developer who already has
# the GGUF on disk skip the download without having to symlink or set
# env vars.
_FALLBACK_SEARCH_PATHS: tuple[Path, ...] = (
    Path.home() / "play" / "sqlite-vector-graph" / "models" / CHAT_MODEL_FILENAME_DEFAULT,
)


def _env_override_path() -> Path | None:
    raw = os.environ.get("CLAUDE_SESSIONS_KG_CHAT_MODEL_PATH", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(
            f"CLAUDE_SESSIONS_KG_CHAT_MODEL_PATH={p} does not exist. "
            f"Either point it at an existing GGUF chat model or unset it "
            f"so the pipeline falls back to the cached default."
        )
    return p


def _existing_chat_model() -> Path | None:
    """Return the first chat-model path that exists, in priority order."""
    cache_target = MODELS_DIR / CHAT_MODEL_FILENAME_DEFAULT
    if cache_target.exists():
        return cache_target
    for candidate in _FALLBACK_SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None


def ensure_chat_model_downloaded(*, force: bool = False) -> Path:
    """Return the local path to the KG chat GGUF, downloading on first use.

    Resolution order: env override → cache → fallback search paths →
    download. ``force=True`` skips every existing-file check and re-downloads
    into the cache directory.

    Raises ``URLError``/``HTTPError`` on network failure — fail loud, since
    without the chat model the NER+RE and community-naming phases cannot run.
    """
    override = _env_override_path()
    if override is not None:
        log.info("  KG chat model: %s (env override)", override)
        return override

    if not force:
        existing = _existing_chat_model()
        if existing is not None:
            log.info(
                "  KG chat model already present: %s (%.1f GiB)",
                existing,
                existing.stat().st_size / (1024**3),
            )
            return existing

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / CHAT_MODEL_FILENAME_DEFAULT

    log.info("  downloading KG chat model %s → %s", CHAT_MODEL_URL_DEFAULT, target)
    req = urllib.request.Request(
        CHAT_MODEL_URL_DEFAULT,
        headers={"User-Agent": "claude-code-sessions/1.0"},
    )
    t0 = time.monotonic()
    partial = target.with_suffix(target.suffix + ".partial")
    with urllib.request.urlopen(req) as resp, partial.open("wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        last_log = t0
        chunk_bytes = 1024 * 1024
        while True:
            chunk = resp.read(chunk_bytes)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            now = time.monotonic()
            if now - last_log >= 5.0:
                pct = f"{100 * downloaded / total:.1f}%" if total else "?%"
                rate = (downloaded / (now - t0)) / (1024 * 1024) if now > t0 else 0
                log.info(
                    "  downloaded %.1f MiB / %.1f MiB (%s, %.1f MiB/s)",
                    downloaded / (1024 * 1024),
                    total / (1024 * 1024) if total else 0,
                    pct,
                    rate,
                )
                last_log = now
    partial.rename(target)
    log.info(
        "  KG chat model downloaded (%.1f GiB in %.1f s)",
        target.stat().st_size / (1024**3),
        time.monotonic() - t0,
    )
    return target


def register_chat_model(conn: sqlite3.Connection, model_path: Path) -> None:
    """Register the GGUF chat model in ``temp.muninn_chat_models``.

    The registration is idempotent: re-registering with the same name is a
    no-op (sqlite-muninn raises an OperationalError saying "already loaded"
    that we treat as success).
    """
    try:
        conn.execute(
            "INSERT INTO temp.muninn_chat_models(name, model) "
            "SELECT ?, muninn_chat_model(?)",
            (CHAT_MODEL_NAME, str(model_path)),
        )
        log.info("  registered KG chat model in temp.muninn_chat_models: %s", CHAT_MODEL_NAME)
    except sqlite3.OperationalError as exc:
        if "already loaded" not in str(exc).lower():
            raise


# ---------------------------------------------------------------------------
# Label vocabularies — domain-tuned for Claude Code session content.
# ---------------------------------------------------------------------------

NER_LABELS: tuple[str, ...] = (
    "tool",
    "file_path",
    "model",
    "concept",
    "error",
    "person",
    "organization",
    "library",
    "command",
)

RE_LABELS: tuple[str, ...] = (
    "uses",
    "calls",
    "imports",
    "depends_on",
    "modifies",
    "reads",
    "writes",
    "instance_of",
    "part_of",
)


# ---------------------------------------------------------------------------
# Leiden resolutions — coarse / medium / fine community structure.
# ---------------------------------------------------------------------------

LEIDEN_RESOLUTIONS: tuple[float, ...] = (0.25, 1.0, 3.0)
DEFAULT_RESOLUTION = 0.25
