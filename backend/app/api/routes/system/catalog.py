"""
Model Catalog API — browse, search, and manage model sets.
"""

from fastapi import APIRouter, HTTPException, Query

from app.core.catalog import (
    get_model_sets,
    get_draft_models,
    get_spec_for_model,
    get_catalog,
)
from app.core.catalog.schemas import convert_to_public

router = APIRouter(prefix="/system/catalog", tags=["Model Catalog"])


@router.get("/models")
async def list_model_sets(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str = Query("", description="Filter by category"),
    search: str = Query("", description="Search by name/description"),
) -> dict:
    """List all model sets with pagination and filtering."""
    all_sets = get_model_sets()
    public_sets = convert_to_public(all_sets)

    # Filter
    if category:
        public_sets = [
            ms for ms in public_sets
            if category.lower() in [c.lower() for c in ms.categories]
        ]
    if search:
        q = search.lower()
        public_sets = [
            ms for ms in public_sets
            if q in ms.name.lower() or q in ms.description.lower()
        ]

    total = len(public_sets)
    start = (page - 1) * size
    page_data = public_sets[start:start + size]

    return {
        "data": [ms.model_dump() for ms in page_data],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/models/{model_set_id}")
async def get_model_set(model_set_id: int) -> dict:
    """Get a single model set with all specs."""
    all_sets = get_model_sets()
    for ms in all_sets:
        if ms.id == model_set_id:
            return ms.model_dump()
    raise HTTPException(status_code=404, detail="Model set not found")


@router.get("/drafts")
async def list_draft_models() -> dict:
    """List draft / upcoming models."""
    drafts = get_draft_models()
    return {"data": [d.model_dump() for d in drafts], "total": len(drafts)}


@router.get("/specs/{source_key:path}")
async def get_model_spec(source_key: str) -> dict:
    """Get a model spec by its source key."""
    spec = get_spec_for_model(source_key)
    if spec is None:
        raise HTTPException(status_code=404, detail="Model spec not found")
    return spec.model_dump()


@router.get("/categories")
async def list_categories() -> dict:
    """List all model categories."""
    categories: set[str] = set()
    for ms in get_model_sets():
        for cat in ms.categories:
            categories.add(cat)
    return {"data": sorted(categories), "total": len(categories)}


@router.get("/info")
async def catalog_info() -> dict:
    """Get catalog metadata."""
    catalog = get_catalog()
    if catalog is None:
        raise HTTPException(status_code=500, detail="Catalog not loaded")
    return {
        "version": catalog.version,
        "updated": catalog.updated,
        "model_sets_count": len(catalog.model_sets),
        "draft_models_count": len(catalog.draft_models or []),
    }
