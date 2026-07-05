"""
Testing API — 测试发现 + 执行引擎

借鉴 VSCode workbench/contrib/testing/ 的测试资源管理器模型。
纯 Python 实现，通过 subprocess 运行测试框架。

支持的测试框架:
  - pytest (Python)
  - jest / vitest (JavaScript/TypeScript)
  - go test (Go)
  - cargo test (Rust)

Session 50: 替换前端 TestingPanel.vue 的硬编码 mock 数据
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("api.testing")

router = APIRouter(prefix="/system/testing", tags=["Testing"])

# ── DTO 模型 ─────────────────────────────────────

class TestCase(BaseModel):
    """单个测试用例"""
    id: str
    name: str
    file_path: str = ""
    line: int = 0
    status: str = "idle"  # idle / running / passed / failed / skipped
    duration_ms: float = 0
    error_message: str = ""
    error_stack: str = ""
    suite_name: str = ""

class TestSuite(BaseModel):
    """测试套件"""
    id: str
    name: str
    file_path: str = ""
    cases: list[TestCase] = []
    status: str = "idle"

class TestFile(BaseModel):
    """测试文件"""
    path: str
    name: str
    suites: list[TestSuite] = []

class DiscoverRequest(BaseModel):
    """测试发现请求"""
    project_path: str = "."
    framework: str = "auto"  # auto / pytest / jest / vitest / gotest / cargotest
    pattern: str = ""  # 文件匹配模式

class ExecuteRequest(BaseModel):
    """测试执行请求"""
    project_path: str = "."
    framework: str = "auto"
    test_ids: list[str] = []  # 空 = 运行全部
    file_path: str = ""  # 单文件运行
    suite_name: str = ""  # 单套件运行

class TestRunResult(BaseModel):
    """测试运行结果"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: float = 0
    results: list[TestCase] = []

# ── 测试框架检测 ────────────────────────────────

PYTEST_FILE_PATTERNS = ["test_*.py", "*_test.py"]
JEST_FILE_PATTERNS = ["*.test.{js,ts,jsx,tsx}", "*.spec.{js,ts,jsx,tsx}"]
GO_TEST_PATTERN = "*_test.go"
RUST_TEST_PATTERN = "#[test]"

FRAMEWORK_DETECTORS = {
    "pytest": {
        "files": ["conftest.py", "pytest.ini", "pyproject.toml"],
        "exts": [".py"],
        "test_patterns": PYTEST_FILE_PATTERNS,
    },
    "jest": {
        "files": ["jest.config.js", "jest.config.ts", "jest.config.json", "package.json"],
        "exts": [".js", ".ts", ".jsx", ".tsx"],
        "test_patterns": JEST_FILE_PATTERNS,
    },
    "gotest": {
        "files": ["go.mod"],
        "exts": [".go"],
        "test_patterns": [GO_TEST_PATTERN],
    },
    "cargotest": {
        "files": ["Cargo.toml"],
        "exts": [".rs"],
        "test_patterns": [RUST_TEST_PATTERN],
    },
}


def _detect_framework(project_path: str) -> str:
    """自动检测项目使用的测试框架"""
    for fw, config in FRAMEWORK_DETECTORS.items():
        for marker in config["files"]:
            if os.path.exists(os.path.join(project_path, marker)):
                return fw
    # 默认尝试 pytest
    if os.path.exists(os.path.join(project_path, "tests")):
        return "pytest"
    return "pytest"


# ── 测试发现 ────────────────────────────────────

def _discover_pytest(project_path: str, pattern: str = "") -> list[TestFile]:
    """pytest 测试发现"""
    tests_dir = os.path.join(project_path, "tests")
    if not os.path.isdir(tests_dir):
        return []

    test_files: list[TestFile] = []

    for root, dirs, files in os.walk(tests_dir):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

        for file in sorted(files):
            if not file.endswith('.py') or not (file.startswith('test_') or file.endswith('_test.py')):
                continue
            if pattern and pattern not in file:
                continue

            file_path = os.path.join(root, file)
            suites = _parse_python_test_file(file_path)
            if suites:
                rel_path = os.path.relpath(file_path, project_path)
                test_files.append(TestFile(
                    path=file_path,
                    name=rel_path.replace('\\', '/'),
                    suites=suites,
                ))

    return test_files


def _parse_python_test_file(file_path: str) -> list[TestSuite]:
    """解析 Python 测试文件，提取 suites 和 test cases"""
    import ast
    suites: list[TestSuite] = []

    try:
        with open(file_path, encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return suites

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            # Test suite
            base_names = [b.id for b in node.bases if isinstance(b, ast.Name)]
            is_test_class = 'Test' in node.name or 'TestCase' in base_names or any(
                b in str(b) for b in node.bases)
            if not is_test_class:
                continue

            cases: list[TestCase] = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, ast.FunctionDef) and (
                    item.name.startswith('test_') or
                    any(isinstance(d, ast.Name) and d.id == 'pytest' for d in item.decorator_list)
                ):
                    cases.append(TestCase(
                        id=f"{file_path}::{node.name}::{item.name}",
                        name=item.name,
                        file_path=file_path,
                        line=item.lineno,
                        suite_name=node.name,
                    ))

            if cases:
                suites.append(TestSuite(
                    id=f"{file_path}::{node.name}",
                    name=node.name,
                    file_path=file_path,
                    cases=cases,
                ))

        elif isinstance(node, ast.FunctionDef):
            # Top-level test function
            if node.name.startswith('test_'):
                suites.append(TestSuite(
                    id=f"{file_path}::top",
                    name="(top-level)",
                    file_path=file_path,
                    cases=[TestCase(
                        id=f"{file_path}::{node.name}",
                        name=node.name,
                        file_path=file_path,
                        line=node.lineno,
                    )],
                ))

    return suites


def _discover_jest(project_path: str, pattern: str = "") -> list[TestFile]:
    """Jest / Vitest 测试发现"""
    test_files: list[TestFile] = []

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']

        for file in sorted(files):
            if '.test.' in file or '.spec.' in file:
                if file.endswith(('.js', '.ts', '.jsx', '.tsx')):
                    if pattern and pattern not in file:
                        continue
                    file_path = os.path.join(root, file)
                    suites = _parse_jest_test_file(file_path)
                    if suites:
                        rel_path = os.path.relpath(file_path, project_path)
                        test_files.append(TestFile(
                            path=file_path,
                            name=rel_path.replace('\\', '/'),
                            suites=suites,
                        ))

    return test_files


def _parse_jest_test_file(file_path: str) -> list[TestSuite]:
    """解析 JS/TS 测试文件的 describe/test 块"""
    suites: list[TestSuite] = []
    try:
        with open(file_path, encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, FileNotFoundError):
        return suites

    lines = content.split('\n')
    current_describe = ""
    describe_stack: list[str] = []

    describe_re = re.compile(r'(?:describe|context)\s*\(\s*[\'"`](.+?)[\'"`]\s*,')
    test_re = re.compile(r'(?:it|test)\s*\(\s*[\'"`](.+?)[\'"`]\s*,')

    for i, line in enumerate(lines):
        d_match = describe_re.search(line)
        if d_match:
            name = d_match.group(1)
            describe_stack.append(name)
            current_describe = " > ".join(describe_stack)
            suites.append(TestSuite(
                id=f"{file_path}::describe::{i}",
                name=current_describe,
                file_path=file_path,
            ))
            continue

        if line.strip() == '});' or line.strip() == '})':
            if describe_stack:
                describe_stack.pop()
            continue

        t_match = test_re.search(line)
        if t_match:
            name = t_match.group(1)
            suite_name = current_describe or "(top-level)"
            # 找到对应 suite
            current_suite = suites[-1] if suites and suites[-1].name == current_describe else None
            tc = TestCase(
                id=f"{file_path}::{name}",
                name=name,
                file_path=file_path,
                line=i + 1,
                suite_name=suite_name,
            )
            if current_suite:
                current_suite.cases.append(tc)
            else:
                suites.append(TestSuite(
                    id=f"{file_path}::describe::{i}",
                    name=suite_name,
                    file_path=file_path,
                    cases=[tc],
                ))

    return [s for s in suites if s.cases]


# ── 测试执行 ────────────────────────────────────

async def _run_pytest(project_path: str, test_ids: list[str] = [],
                      file_path: str = "", suite_name: str = "") -> TestRunResult:
    """运行 pytest 测试"""
    args = ["python", "-m", "pytest", "-v", "--tb=short"]
    cmd = []
    if test_ids:
        # pytest 格式: file::class::method
        for tid in test_ids:
            # 从 id 中提取路径
            parts = tid.split("::", 1)
            if parts:
                cmd.append(parts[0])
    elif file_path:
        cmd.append(file_path)
        if suite_name and suite_name != "(top-level)":
            cmd.append(f"-k={suite_name}")

    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=120
        )
        output = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return TestRunResult(total=0, failed=1, duration_ms=120_000,
                             results=[TestCase(id="timeout", name="timeout",
                                              status="failed",
                                              error_message="执行超时 (120s)")])
    except FileNotFoundError:
        return TestRunResult(total=0, failed=1,
                             results=[TestCase(id="pytest-missing", name="pytest-missing",
                                              status="failed",
                                              error_message="pytest 未安装。运行: pip install pytest")])

    duration = (time.perf_counter() - start) * 1000
    results = _parse_pytest_output(output + "\n" + err)
    return TestRunResult(
        total=len(results),
        passed=sum(1 for r in results if r.status == "passed"),
        failed=sum(1 for r in results if r.status == "failed"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        duration_ms=round(duration, 2),
        results=results,
    )


_PYTEST_RESULT_RE = re.compile(
    r'(\S+)::(\S+)\s+(PASSED|FAILED|SKIPPED|ERROR|XPASS|XFAIL)'
)


def _parse_pytest_output(output: str) -> list[TestCase]:
    """解析 pytest -v 输出"""
    results: list[TestCase] = []
    for m in _PYTEST_RESULT_RE.finditer(output):
        file_part = m.group(1)
        test_name = m.group(2)
        status_raw = m.group(3).lower()
        status = {
            "passed": "passed", "passed": "passed",
            "failed": "failed", "error": "failed",
            "skipped": "skipped", "xpass": "passed", "xfail": "skipped",
        }.get(status_raw, "failed")

        results.append(TestCase(
            id=f"{file_part}::{test_name}",
            name=test_name,
            file_path=file_part,
            status=status,
        ))

    # Parse failures
    failures = list(re.finditer(
        r'FAILED\s+(\S+::\S+).*?\n(.*?)(?=\n\S+::|$)',
        output, re.DOTALL
    ))
    for fm in failures:
        name = fm.group(1).split("::")[-1]
        for r in results:
            if r.name == name and r.status == "failed":
                r.error_message = fm.group(2).strip()[:200]
                break

    return results


async def _run_jest(project_path: str, test_ids: list[str] = [],
                    file_path: str = "") -> TestRunResult:
    """运行 Jest 测试"""
    cmd = ["npx", "jest", "--no-coverage", "--json", "--verbose"]
    if file_path:
        cmd.append(file_path)

    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return TestRunResult(total=0, failed=1, duration_ms=120_000)
    except FileNotFoundError:
        return TestRunResult(total=0, failed=1,
                             results=[TestCase(id="jest-missing", name="jest-missing",
                                              status="failed",
                                              error_message="Jest 未安装。运行: npm install jest")])
    duration = (time.perf_counter() - start) * 1000

    # 解析 Jest JSON 输出
    try:
        import json
        data = json.loads(output)
        results = []
        for suite in data.get("testResults", []):
            for tc in suite.get("assertionResults", []):
                results.append(TestCase(
                    id=f"{suite.get('name', '')}::{tc.get('title', '')}",
                    name=tc.get("title", ""),
                    file_path=suite.get("name", ""),
                    status=tc.get("status", "failed").lower(),
                    duration_ms=tc.get("duration", 0),
                    error_message="\n".join(tc.get("failureMessages", [])),
                    suite_name=tc.get("ancestorTitles", [""])[0] or "",
                ))
        return TestRunResult(
            total=len(results),
            passed=sum(1 for r in results if r.status == "passed"),
            failed=sum(1 for r in results if r.status == "failed"),
            skipped=sum(1 for r in results if r.status in ("skipped", "pending")),
            duration_ms=round(duration, 2),
            results=results,
        )
    except (json.JSONDecodeError, KeyError):
        return TestRunResult(total=0, failed=1, duration_ms=round(duration, 2))


# Framework runner map
FRAMEWORK_RUNNERS = {
    "pytest": _run_pytest,
    "jest": _run_jest,
    "vitest": _run_jest,  # vitest 兼容 jest JSON 输出
}


# ── API 路由 ──────────────────────────────────────

@router.post("/discover")
async def discover_tests(req: DiscoverRequest) -> dict:
    """
    发现工作区中的测试 — 对标 VSCode Test Explorer

    返回 TestFile[] 树结构（File > Suite > TestCase）
    """
    framework = req.framework
    if framework == "auto":
        framework = _detect_framework(req.project_path)

    if framework == "pytest":
        files = _discover_pytest(req.project_path, req.pattern)
    elif framework in ("jest", "vitest"):
        files = _discover_jest(req.project_path, req.pattern)
    else:
        return {"files": [], "framework": framework, "error": f"不支持的框架: {framework}"}

    total_cases = sum(len(c) for f in files for s in f.suites for c in s.cases)
    return {
        "files": [f.model_dump() for f in files],
        "framework": framework,
        "total_files": len(files),
        "total_suites": sum(len(f.suites) for f in files),
        "total_cases": total_cases,
    }


@router.post("/run")
async def run_tests(req: ExecuteRequest) -> dict:
    """
    运行测试 — 对标 VSCode 的 Run Test / Debug Test 操作
    """
    framework = req.framework
    if framework == "auto":
        framework = _detect_framework(req.project_path)

    runner = FRAMEWORK_RUNNERS.get(framework)
    if not runner:
        raise HTTPException(status_code=400, detail=f"不支持的测试框架: {framework}")

    result = await runner(req.project_path, req.test_ids, req.file_path, req.suite_name)
    return {
        "framework": framework,
        "results": result.model_dump(),
    }


@router.get("/frameworks")
async def list_frameworks() -> dict:
    """列出支持的测试框架"""
    return {
        "frameworks": [
            {"id": "pytest", "name": "pytest", "language": "Python",
             "available": True, "install": "pip install pytest"},
            {"id": "jest", "name": "Jest", "language": "JavaScript/TypeScript",
             "available": True, "install": "npm install --save-dev jest"},
            {"id": "vitest", "name": "Vitest", "language": "JavaScript/TypeScript",
             "available": True, "install": "npm install --save-dev vitest"},
            {"id": "gotest", "name": "go test", "language": "Go",
             "available": True, "install": "built-in"},
            {"id": "cargotest", "name": "cargo test", "language": "Rust",
             "available": True, "install": "built-in"},
        ]
    }
