"""Shared GLiNER2 model cache — loads once per process.

Both NER and RE use the same model instance via this loader. The cache
ensures the ~205 MB DeBERTa weights are mmaped at most once even when
both phases run sequentially.

Offline loading: ``snapshot_download`` returns the cached local path;
``GLiNER2.from_pretrained(local_dir)`` short-circuits to local file
access via ``os.path.isdir()`` — no ``HF_HUB_OFFLINE`` patching required.
"""

from __future__ import annotations

import logging

from gliner2 import GLiNER2
from huggingface_hub import snapshot_download

log = logging.getLogger(__name__)

DEFAULT_GLINER2_MODEL = "fastino/gliner2-base-v1"

_cache: dict[str, GLiNER2] = {}


def get_gliner2(model_name: str = DEFAULT_GLINER2_MODEL) -> GLiNER2:
    """Return a cached GLiNER2 instance.

    First call resolves the model in the local HF cache (without a
    network round-trip — ``snapshot_download(local_files_only=True)``).
    The weights live under ``~/.cache/huggingface/hub/...``; if they
    aren't present we re-issue the call WITHOUT ``local_files_only`` so
    the missing files are downloaded once. This keeps warm starts
    instant while still bootstrapping a fresh machine.

    Subsequent calls with the same ``model_name`` return the cached
    instance with no additional memory or disk I/O.
    """
    if model_name not in _cache:
        log.info("  loading GLiNER2 weights: %s", model_name)
        try:
            local_path = snapshot_download(model_name, local_files_only=True)
        except Exception:
            log.info("  GLiNER2 weights not in HF cache — downloading from HF Hub")
            local_path = snapshot_download(model_name)
        _cache[model_name] = GLiNER2.from_pretrained(local_path)
    return _cache[model_name]
