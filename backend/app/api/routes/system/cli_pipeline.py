"""CLI 流水线 API — 借鉴 AutoCLI 的 YAML 适配器 + 流水线组合

端点：
  - POST /system/cli-pipeline/run-file    — 从 YAML 文件运行管道
  - POST /system/cli-pipeline/run-inline  — 内联定义运行管道
  - GET  /system/cli-pipeline/samples     — 获取示例管道模板
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/cli-pipeline", tags=["CLIPipeline"])


class RunFileRequest(BaseModel):
    file_path: str
    variables: dict | None = None


class RunInlineRequest(BaseModel):
    name: str
    steps: list[dict]
    variables: dict | None = None


@router.post("/run-file")
async def run_pipeline_from_file(req: RunFileRequest):
    """从 YAML 文件加载并运行 CLI 管道"""
    try:
        from app.core.tools.cli_pipeline import load_pipeline

        pipeline = load_pipeline(req.file_path)
        result = await pipeline.run()
        return result.to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"YAML file not found: {req.file_path}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to run pipeline from file: %s", req.file_path)
        raise HTTPException(status_code=500, detail="Internal error running pipeline")


@router.post("/run-inline")
async def run_pipeline_inline(req: RunInlineRequest):
    """以内联定义运行 CLI 管道"""
    try:
        from app.core.tools.cli_pipeline import build_pipeline

        pipeline = build_pipeline(
            name=req.name,
            steps=req.steps,
            variables=req.variables,
        )
        result = await pipeline.run()
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to run inline pipeline: %s", req.name)
        raise HTTPException(status_code=500, detail="Internal error running pipeline")


@router.post("/run-yaml")
async def run_pipeline_from_yaml(yaml_content: str):
    """从 YAML 字符串直接运行 CLI 管道"""
    try:
        from app.core.tools.cli_pipeline import CLIPipelineLoader

        pipeline = CLIPipelineLoader.load_from_string(yaml_content, name="inline-yaml")
        result = await pipeline.run()
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to run pipeline from YAML string")
        raise HTTPException(status_code=500, detail="Internal error running YAML pipeline")


@router.get("/samples")
async def get_sample_pipelines():
    """获取示例管道模板"""
    return {
        "samples": [
            {
                "name": "setup-project",
                "description": "Standard project setup workflow",
                "yaml": """name: setup-project
steps:
  - id: check-node
    command: node --version
    description: "Check Node.js installation"
  - id: install-deps
    command: pnpm install
    depends_on: [check-node]
    description: "Install project dependencies"
  - id: lint
    command: pnpm lint
    depends_on: [install-deps]
    parallel: [test]
  - id: test
    command: pnpm test
    depends_on: [install-deps]
    parallel: [lint]""",
            },
            {
                "name": "docker-build",
                "description": "Docker build and push pipeline",
                "yaml": """name: docker-build
steps:
  - id: build
    command: docker build -t myapp:latest .
    timeout: 300
  - id: test
    command: docker run --rm myapp:latest test
    depends_on: [build]
  - id: push
    command: docker push myapp:latest
    depends_on: [test]
    condition: "{{test.exit_code}} == 0\"""",
            },
            {
                "name": "git-sync",
                "description": "Git sync with branch protection",
                "yaml": """name: git-sync
steps:
  - id: fetch
    command: git fetch origin
  - id: status
    command: git status --porcelain
    depends_on: [fetch]
  - id: pull
    command: git pull --rebase origin main
    depends_on: [status]
    condition: "{{status.stdout}} == ''"
    on_failure: stop""",
            },
        ]
    }
