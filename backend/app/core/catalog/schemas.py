"""
Model Catalog schemas — ModelSet, ModelSpec, DraftModel, Catalog.

Based on GPUStack's catalog model (schemas/model_sets.py).
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ModelSpec(BaseModel):
    """Specification for how to obtain and run a specific model variant."""
    model_source_key: str = Field(
        default="",
        description="e.g., 'Qwen/Qwen2.5-Coder-7B-Instruct' (HuggingFace) or model ID",
    )
    source: str = Field(
        default="huggingface",
        description="Source: 'huggingface', 'modelscope', 'ollama', etc.",
    )
    quantization: Optional[str] = Field(
        default=None,
        description="e.g., 'Q4_K_M', 'FP16', 'INT8'",
    )
    size_gb: float = Field(default=0.0, description="Estimated disk size in GB")
    vram_required_gb: float = Field(
        default=0.0,
        description="Estimated VRAM required for inference",
    )
    backend: str = Field(
        default="llama.cpp",
        description="Inference backend: 'llama.cpp', 'vllm', 'transformers', etc.",
    )
    context_length: int = Field(default=4096)
    capabilities: list[str] = Field(
        default_factory=list,
        description="e.g., ['code_generation', 'vision', 'chat']",
    )
    benchmark_score: Optional[float] = Field(default=None)
    license: str = Field(default="", description="Model license (MIT, Apache-2.0, etc.)")
    language: list[str] = Field(default_factory=list, description="Supported languages")
    tags: list[str] = Field(default_factory=list)


class DraftModel(BaseModel):
    """Preview of an unreleased / planned model."""
    name: str = ""
    description: str = ""
    expected_release: Optional[str] = None
    source_url: str = ""


class ModelSet(BaseModel):
    """A collection of model specs — e.g., all variants of Qwen2.5-Coder."""
    id: int = 0
    name: str = ""
    description: str = ""
    icon: str = ""
    homepage: str = ""
    organization: str = ""
    release_date: Optional[date] = None
    order: Optional[int] = None
    categories: list[str] = Field(default_factory=list)
    specs: list[ModelSpec] = Field(default_factory=list)
    templates: dict = Field(default_factory=dict)


class ModelSetPublic(BaseModel):
    """Public-facing ModelSet (without internal templates)."""
    id: int = 0
    name: str = ""
    description: str = ""
    icon: str = ""
    homepage: str = ""
    organization: str = ""
    release_date: Optional[date] = None
    order: Optional[int] = None
    categories: list[str] = Field(default_factory=list)
    specs: list[ModelSpec] = Field(default_factory=list)


class Catalog(BaseModel):
    """Top-level model catalog."""
    version: str = "1.0"
    updated: Optional[str] = None
    model_sets: list[ModelSet] = Field(default_factory=list)
    draft_models: list[DraftModel] = Field(default_factory=list)


def convert_to_public(model_sets: list[ModelSet]) -> list[ModelSetPublic]:
    """Strip internal templates from ModelSets for public API responses."""
    return [
        ModelSetPublic(**ms.model_dump(exclude={"templates"}))
        for ms in model_sets
    ]
