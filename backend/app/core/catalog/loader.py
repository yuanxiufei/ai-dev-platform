"""
Model Catalog — YAML-driven model catalog with HuggingFace/ModelScope dual-source support.

Borrows directly from GPUStack's catalog/init_model_catalog() pattern:
- YAML-based catalog file with ModelSet + ModelSpec definitions
- Network accessibility probe for HuggingFace vs ModelScope fallback
- Chat template management
"""

import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
import yaml

from app.core.catalog.schemas import Catalog, ModelSet, ModelSpec, DraftModel

logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────
_model_catalog: Optional[Catalog] = None
_model_specs_by_key: dict[str, ModelSpec] = {}


def get_catalog() -> Optional[Catalog]:
    """Get the loaded model catalog."""
    return _model_catalog


def get_model_sets() -> list[ModelSet]:
    """Get all model sets from the catalog."""
    return _model_catalog.model_sets if _model_catalog else []


def get_draft_models() -> list[DraftModel]:
    """Get draft/unreleased models."""
    return _model_catalog.draft_models if _model_catalog else []


def get_spec_for_model(source_key: str) -> Optional[ModelSpec]:
    """Look up a ModelSpec by its source key (e.g., 'Qwen/Qwen2.5-Coder-7B-Instruct')."""
    return _model_specs_by_key.get(source_key)


def init_catalog(catalog_file: Optional[str] = None) -> Catalog:
    """Initialize the model catalog from a YAML file or built-in default.

    Supports loading from:
    1. Explicit file path
    2. Remote URL (http/https)
    3. Built-in catalog (auto-detects HuggingFace vs ModelScope accessibility)

    Args:
        catalog_file: Optional path or URL to catalog YAML file.

    Returns:
        Loaded Catalog object.

    Raises:
        Exception: If catalog loading fails entirely.
    """
    global _model_catalog, _model_specs_by_key

    if catalog_file is None:
        catalog_file = _get_builtin_catalog_path()

    try:
        raw_data = _load_yaml(catalog_file)
        _model_catalog = Catalog(**raw_data)
        logger.info(
            "Loaded %d model sets, %d draft models from catalog: %s",
            len(_model_catalog.model_sets),
            len(_model_catalog.draft_models or []),
            catalog_file,
        )

        # Assign IDs
        for idx, ms in enumerate(_model_catalog.model_sets):
            ms.id = idx + 1

        # Sort by order asc, then release_date desc
        _model_catalog.model_sets.sort(
            key=lambda x: (
                x.order if x.order is not None else float("inf"),
                -(x.release_date.toordinal() if x.release_date else 0),
            ),
        )

        # Build specs index
        _model_specs_by_key.clear()
        for ms in _model_catalog.model_sets:
            for spec in reversed(ms.specs):
                if spec.model_source_key and spec.model_source_key not in _model_specs_by_key:
                    _model_specs_by_key[spec.model_source_key] = spec

        _init_chat_templates()

        return _model_catalog

    except Exception as e:
        raise RuntimeError(f"Failed to load model catalog: {e}")


def reload_catalog(catalog_file: Optional[str] = None) -> Catalog:
    """Reload the catalog from source."""
    global _model_catalog, _model_specs_by_key
    _model_catalog = None
    _model_specs_by_key.clear()
    return init_catalog(catalog_file)


# ── Internal helpers ──────────────────────────────

def _load_yaml(source: str) -> dict:
    """Load YAML from a file path or URL."""
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        resp = requests.get(source, timeout=10)
        resp.raise_for_status()
        return yaml.safe_load(resp.text)
    else:
        with open(source, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


def _get_builtin_catalog_path() -> str:
    """Determine which built-in catalog to use based on network accessibility.

    Defaults to HuggingFace catalog; falls back to ModelScope if HF is blocked.
    """
    catalog_dir = Path(__file__).parent
    hf_catalog = catalog_dir / "model-catalog.yaml"
    ms_catalog = catalog_dir / "model-catalog-modelscope.yaml"

    if _can_access("https://huggingface.co"):
        if hf_catalog.exists():
            return str(hf_catalog)
    elif _can_access("https://modelscope.cn"):
        if ms_catalog.exists():
            logger.info("HuggingFace inaccessible, using ModelScope catalog")
            return str(ms_catalog)

    # Fallback to whatever exists locally
    if hf_catalog.exists():
        return str(hf_catalog)
    if ms_catalog.exists():
        return str(ms_catalog)

    raise FileNotFoundError(
        f"No model catalog found at {hf_catalog} or {ms_catalog}. "
        "Ensure at least one catalog file exists."
    )


def _can_access(url: str, timeout: int = 3) -> bool:
    """Check if a URL is accessible."""
    try:
        resp = requests.get(url, timeout=timeout)
        return 200 <= resp.status_code < 300
    except requests.RequestException:
        return False


def _init_chat_templates() -> None:
    """Copy built-in chat templates to the data directory."""
    source_dir = Path(__file__).parent / "chat_templates"
    if not source_dir.exists():
        return
    target_dir = Path(os.getenv("MODELS_DIR", "models")) / "chat_templates"
    try:
        import shutil
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            dest = target_dir / item.name
            if item.is_file() and not dest.exists():
                shutil.copy2(item, dest)
    except Exception as e:
        logger.debug("Chat template copy skipped: %s", e)
