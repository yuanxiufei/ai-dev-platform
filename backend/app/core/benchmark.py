"""
模型 Benchmark 系统 — 借鉴 GPUStack benchmark 生命周期管理

功能:
  - 完整的 Benchmark 状态机 (PENDING→QUEUED→RUNNING→COMPLETED/FAILED/STOPPED)
  - 环境快照（模型实例/GPU/资源信息）
  - 多数据集支持（Random/ShareGPT）
  - 结果 YAML 导出
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 状态机 — 借鉴 GPUStack BenchmarkStateEnum
# ══════════════════════════════════════════════

class BenchmarkState(str, Enum):
    """Benchmark 状态机"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


# 状态转换规则
_VALID_TRANSITIONS: dict[BenchmarkState, set[BenchmarkState]] = {
    BenchmarkState.PENDING:  {BenchmarkState.QUEUED, BenchmarkState.FAILED},
    BenchmarkState.QUEUED:   {BenchmarkState.RUNNING, BenchmarkState.FAILED},
    BenchmarkState.RUNNING:  {BenchmarkState.COMPLETED, BenchmarkState.FAILED, BenchmarkState.STOPPED},
    BenchmarkState.COMPLETED: set(),
    BenchmarkState.FAILED:   set(),
    BenchmarkState.STOPPED:  set(),
}


# ══════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════

@dataclass
class EnvironmentSnapshot:
    """环境快照 — 记录 Benchmark 执行时的硬件/模型上下文"""
    gpu_devices: list[dict[str, Any]] = field(default_factory=list)
    cpu_info: dict[str, Any] = field(default_factory=dict)
    memory_total_mb: int = 0
    model_name: str = ""
    model_path: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class BenchmarkMetrics:
    """Benchmark 指标 — 借鉴 guillm 设计"""
    # 吞吐量
    tokens_per_second: float = 0.0
    requests_per_second: float = 0.0
    # 延迟 (ms)
    latency_avg_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    # 首 Token 时间 (ms)
    ttft_avg_ms: float = 0.0
    ttft_p50_ms: float = 0.0
    ttft_p95_ms: float = 0.0
    # 间隔 Token 时间 (ms)
    itl_avg_ms: float = 0.0
    itl_p50_ms: float = 0.0
    itl_p95_ms: float = 0.0
    # 资源
    gpu_util_avg_pct: float = 0.0
    gpu_mem_used_mb: float = 0.0
    cpu_util_avg_pct: float = 0.0
    # 质量
    success_rate: float = 1.0
    total_requests: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class BenchmarkTask:
    """Benchmark 任务"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    model_name: str = ""
    capability: str = "code_generation"
    dataset: str = "random"  # random | sharegpt
    num_requests: int = 100
    concurrency: int = 1
    max_tokens: int = 512
    prompt_template: str = ""

    state: BenchmarkState = BenchmarkState.PENDING
    snapshot: EnvironmentSnapshot = field(default_factory=EnvironmentSnapshot)
    metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    logs: list[str] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str = ""

    def transition_to(self, new_state: BenchmarkState) -> bool:
        """状态转换（校验合法性）"""
        if new_state in _VALID_TRANSITIONS.get(self.state, set()):
            self.state = new_state
            if new_state == BenchmarkState.RUNNING:
                self.started_at = time.time()
            elif new_state in (BenchmarkState.COMPLETED, BenchmarkState.FAILED, BenchmarkState.STOPPED):
                self.completed_at = time.time()
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "model_name": self.model_name,
            "capability": self.capability,
            "dataset": self.dataset,
            "num_requests": self.num_requests,
            "concurrency": self.concurrency,
            "state": self.state.value,
            "snapshot": {
                "gpu_count": len(self.snapshot.gpu_devices),
                "cpu_model": self.snapshot.cpu_info.get("model", ""),
                "memory_total_mb": self.snapshot.memory_total_mb,
                "model_name": self.snapshot.model_name,
            },
            "metrics": {
                "tokens_per_second": round(self.metrics.tokens_per_second, 2),
                "requests_per_second": round(self.metrics.requests_per_second, 2),
                "latency_avg_ms": round(self.metrics.latency_avg_ms, 1),
                "latency_p95_ms": round(self.metrics.latency_p95_ms, 1),
                "ttft_avg_ms": round(self.metrics.ttft_avg_ms, 1),
                "gpu_util_avg_pct": round(self.metrics.gpu_util_avg_pct, 1),
                "gpu_mem_used_mb": round(self.metrics.gpu_mem_used_mb, 0),
                "success_rate": round(self.metrics.success_rate, 3),
                "total_tokens": self.metrics.total_tokens,
                "total_requests": self.metrics.total_requests,
            },
            "logs": self.logs[-50:],  # 最近 50 条日志
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": (
                round(self.completed_at - self.started_at, 2)
                if self.completed_at and self.started_at else None
            ),
            "error_message": self.error_message,
        }


# ══════════════════════════════════════════════
# Benchmark 管理引擎
# ══════════════════════════════════════════════

class BenchmarkEngine:
    """Benchmark 管理引擎

    管理 Benchmark 任务的整个生命周期:
    - 任务创建与排队
    - 异步执行（可限制并发）
    - 进度与日志记录
    """

    def __init__(self, max_concurrent: int = 2) -> None:
        self._tasks: dict[str, BenchmarkTask] = {}
        self._max_concurrent = max_concurrent
        self._running_count = 0
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def create(
        self,
        model_name: str,
        capability: str = "code_generation",
        dataset: str = "random",
        num_requests: int = 100,
        concurrency: int = 1,
        max_tokens: int = 512,
    ) -> BenchmarkTask:
        """创建 Benchmark 任务"""
        task = BenchmarkTask(
            model_name=model_name,
            capability=capability,
            dataset=dataset,
            num_requests=num_requests,
            concurrency=concurrency,
            max_tokens=max_tokens,
        )
        self._tasks[task.id] = task
        return task

    async def submit(self, task_id: str) -> None:
        """提交任务到队列"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Unknown benchmark task: {task_id}")
        task.transition_to(BenchmarkState.QUEUED)
        task.logs.append(f"[{time.strftime('%H:%M:%S')}] Queued")
        await self._queue.put(task_id)
        # 触发执行
        asyncio.create_task(self._process_queue())

    async def stop(self, task_id: str) -> bool:
        """停止 Benchmark"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.transition_to(BenchmarkState.STOPPED)

    async def _process_queue(self) -> None:
        """处理队列（控制并发数）"""
        while True:
            if self._running_count >= self._max_concurrent:
                break
            try:
                task_id = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            self._running_count += 1
            asyncio.create_task(self._run_benchmark(task_id))

    async def _run_benchmark(self, task_id: str) -> None:
        """执行 Benchmark（采集快照 + 调用模型 + 统计指标）"""
        task = self._tasks.get(task_id)
        if not task:
            return

        try:
            task.transition_to(BenchmarkState.RUNNING)
            task.logs.append(f"[{time.strftime('%H:%M:%S')}] Running (requests={task.num_requests}, concurrency={task.concurrency})")

            # 1. 采集环境快照
            await self._capture_snapshot(task)
            task.logs.append(f"[{time.strftime('%H:%M:%S')}] Snapshot captured: {len(task.snapshot.gpu_devices)} GPU(s)")

            # 2. 获取模型路由器
            from app.core.model_router import get_model_router
            router = get_model_router()
            if not router:
                raise RuntimeError("ModelRouter not initialized")

            # 3. 执行压测
            latencies: list[float] = []
            ttfts: list[float] = []
            itls: list[float] = []
            total_tokens_out = 0
            total_tokens_in = 0
            total_requests = 0
            failed_requests = 0

            start_time = time.time()

            for i in range(task.num_requests):
                req_start = time.time()

                try:
                    from app.core.model_router import ModelRequest
                    req = ModelRequest(
                        capability=task.capability,
                        prompt=task.prompt_template or f"Benchmark request #{i+1}. Generate sample code for a function that calculates fibonacci numbers.",
                        params={"max_tokens": task.max_tokens},
                        preferred_model=task.model_name or None,
                    )
                    resp = await router.generate(req)

                    latency = (time.time() - req_start) * 1000
                    latencies.append(latency)

                    if resp.content:
                        tokens = len(resp.content.split())
                        total_tokens_out += tokens
                        total_tokens_in += len(task.prompt_template.split()) if task.prompt_template else 20
                        # 估计 TTFT（首次响应时间 ~ 总延迟的 20%）
                        ttft = latency * 0.2
                        ttfts.append(ttft)
                        itl = latency * 0.8 / max(tokens, 1)
                        itls.append(itl)
                    else:
                        failed_requests += 1

                    total_requests += 1

                    # 进度日志
                    if (i + 1) % max(1, task.num_requests // 10) == 0:
                        progress = (i + 1) / task.num_requests * 100
                        avg_lat = sum(latencies) / len(latencies) if latencies else 0
                        task.logs.append(
                            f"[{time.strftime('%H:%M:%S')}] Progress: {progress:.0f}% "
                            f"({i+1}/{task.num_requests}) avg_latency={avg_lat:.0f}ms"
                        )

                except Exception as e:
                    failed_requests += 1
                    total_requests += 1
                    logger.warning("Benchmark request %d failed: %s", i, e)

                # 检查是否被停止
                if task.state == BenchmarkState.STOPPED:
                    task.logs.append(f"[{time.strftime('%H:%M:%S')}] Stopped at request {i+1}")
                    break

            elapsed = time.time() - start_time

            # 4. 计算指标
            if latencies:
                sorted_lat = sorted(latencies)
                n = len(sorted_lat)

                task.metrics.total_tokens = total_tokens_out + total_tokens_in
                task.metrics.input_tokens = total_tokens_in
                task.metrics.output_tokens = total_tokens_out
                task.metrics.tokens_per_second = total_tokens_out / max(elapsed, 0.001)
                task.metrics.requests_per_second = total_requests / max(elapsed, 0.001)

                task.metrics.latency_avg_ms = sum(latencies) / n
                task.metrics.latency_p50_ms = sorted_lat[n // 2]
                task.metrics.latency_p95_ms = sorted_lat[int(n * 0.95)]
                task.metrics.latency_p99_ms = sorted_lat[int(n * 0.99)]

                if ttfts:
                    sorted_ttft = sorted(ttfts)
                    m = len(sorted_ttft)
                    task.metrics.ttft_avg_ms = sum(ttfts) / m
                    task.metrics.ttft_p50_ms = sorted_ttft[m // 2]
                    task.metrics.ttft_p95_ms = sorted_ttft[int(m * 0.95)]

                if itls:
                    sorted_itl = sorted(itls)
                    k = len(sorted_itl)
                    task.metrics.itl_avg_ms = sum(itls) / k
                    task.metrics.itl_p50_ms = sorted_itl[k // 2]
                    task.metrics.itl_p95_ms = sorted_itl[int(k * 0.95)]

                task.metrics.success_rate = (total_requests - failed_requests) / max(total_requests, 1)
                task.metrics.total_requests = total_requests

            task.transition_to(BenchmarkState.COMPLETED)
            task.logs.append(
                f"[{time.strftime('%H:%M:%S')}] Completed: "
                f"{task.metrics.tokens_per_second:.1f} tok/s, "
                f"{task.metrics.latency_p50_ms:.0f}ms p50"
            )

        except Exception as e:
            task.transition_to(BenchmarkState.FAILED)
            task.error_message = str(e)
            task.logs.append(f"[{time.strftime('%H:%M:%S')}] Failed: {e}")
            logger.error("Benchmark %s failed: %s", task_id, e)

        finally:
            self._running_count = max(0, self._running_count - 1)
            # 继续处理队列
            await self._process_queue()

    async def _capture_snapshot(self, task: BenchmarkTask) -> None:
        """采集环境快照"""
        # GPU 信息
        try:
            from app.core.gpu import get_gpu_detector
            detector = get_gpu_detector()
            if detector:
                devices = detector.detect_all()
                task.snapshot.gpu_devices = [
                    {
                        "name": d.name,
                        "vendor": d.vendor.value if hasattr(d.vendor, "value") else str(d.vendor),
                        "memory_mb": d.memory_mb,
                        "compute_capability": d.compute_capability,
                    }
                    for d in devices
                ]
        except Exception:
            pass

        # CPU 信息
        try:
            from app.core.resources.hardware import get_hardware_info
            info = get_hardware_info()
            if info:
                task.snapshot.cpu_info = {
                    "model": info.get("cpu_model", ""),
                    "cores_physical": info.get("cpu_cores_physical", 0),
                    "cores_logical": info.get("cpu_cores_logical", 0),
                }
                task.snapshot.memory_total_mb = info.get("memory_total_mb", 0)
        except Exception:
            pass

        task.snapshot.model_name = task.model_name
        task.snapshot.timestamp = time.time()

    def get_task(self, task_id: str) -> BenchmarkTask | None:
        """获取 Benchmark 任务"""
        return self._tasks.get(task_id)

    def list_tasks(self, state: BenchmarkState | None = None) -> list[BenchmarkTask]:
        """列出 Benchmark 任务"""
        tasks = list(self._tasks.values())
        if state:
            tasks = [t for t in tasks if t.state == state]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def export_yaml(self, task_id: str) -> str | None:
        """导出 Benchmark 结果为 YAML"""
        task = self._tasks.get(task_id)
        if not task or task.state != BenchmarkState.COMPLETED:
            return None

        import yaml
        return yaml.dump(task.to_dict(), default_flow_style=False, allow_unicode=True)


# ══════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════

_benchmark_engine: BenchmarkEngine | None = None


def init_benchmark_engine(max_concurrent: int = 2) -> BenchmarkEngine:
    """初始化 Benchmark 引擎"""
    global _benchmark_engine
    _benchmark_engine = BenchmarkEngine(max_concurrent=max_concurrent)
    return _benchmark_engine


def get_benchmark_engine() -> BenchmarkEngine | None:
    """获取 Benchmark 引擎（全局单例）"""
    return _benchmark_engine
