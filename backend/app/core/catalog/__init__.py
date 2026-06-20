"""
Model Catalog — centralized module for model discovery and browsing.
"""

from app.core.catalog.loader import (
    init_catalog,
    reload_catalog,
    get_catalog,
    get_model_sets,
    get_draft_models,
    get_spec_for_model,
)
from app.core.catalog.schemas import (
    Catalog,
    ModelSet,
    ModelSetPublic,
    ModelSpec,
    DraftModel,
    convert_to_public,
)

__all__ = [
    # Loader functions
    "init_catalog",
    "reload_catalog",
    "get_catalog",
    "get_model_sets",
    "get_draft_models",
    "get_spec_for_model",
    # Schemas
    "Catalog",
    "ModelSet",
    "ModelSetPublic",
    "ModelSpec",
    "DraftModel",
    "convert_to_public",
]
