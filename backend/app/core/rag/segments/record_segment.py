"""
记录 Segment — BlockFile 原始文档存储

借鉴 Chroma Record Segment (BlockFile 后端):
- 按块存储原始 chunk 数据 (text + metadata)
- 支持 get(ids) 按 doc_id 查询
- 用于检索结果回填原始文本渲染
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

from app.core.rag.segments import Segment

logger = logging.getLogger("app.core.rag.segments.record")

BLOCK_SIZE = 4096  # 每个 block 最大字节数


class RecordSegment(Segment):
    """BlockFile 记录存储

    实现 Segment ABC:
    - add(ids, records)    → 追加写入 JSON records
    - get(ids)             → 解析 block 文件，按 doc_id 查找
    - delete(ids)          → 不支持物理删除 (重新写入过滤)
    - query(...)           → 不支持查询 (走 MetadataSegment)
    """

    def __init__(self, kb_path: str, scope: str = "default"):
        super().__init__(name="record", scope=scope)
        self._file_path = kb_path.rstrip("/\\") + "/records.block"
        self._lock = threading.Lock()
        # 内存缓存 {doc_id: record}
        self._cache: dict[str, dict] = {}

    # ── Segment ABC 实现 ─────────────────────────────────

    def add(self, ids: list[str], records: list[dict]) -> int:
        """追加写入 block 文件"""
        if not ids or not records:
            return 0

        with self._lock:
            n = 0
            with open(self._file_path, "ab") as f:
                for rec_id, rec in zip(ids, records):
                    doc_id = rec.get("doc_id", rec_id)
                    entry = {
                        "doc_id": doc_id,
                        "text": rec.get("text", ""),
                        "metadata": rec.get("metadata", {}),
                    }
                    line = json.dumps(entry, ensure_ascii=False) + "\n"
                    f.write(line.encode("utf-8"))
                    self._cache[doc_id] = entry
                    n += 1
            return n

    def get(self, ids: list[str]) -> dict[str, dict]:
        """按 doc_id 查询记录"""
        if not ids:
            return {}

        results = {}
        missing = []

        # 先查内存缓存
        for did in ids:
            if did in self._cache:
                results[did] = self._cache[did]
            else:
                missing.append(did)

        # 缓存未命中，读文件
        if missing and os.path.exists(self._file_path):
            results.update(self._scan_file(missing))

        return results

    def delete(self, ids: list[str]) -> int:
        """物理删除：重写文件过滤已删除 id"""
        if not ids or not os.path.exists(self._file_path):
            return 0

        delete_set = set(ids)
        kept = 0

        with self._lock:
            temp_path = self._file_path + ".tmp"
            try:
                with open(self._file_path, "r") as fin, open(temp_path, "w") as fout:
                    for line in fin:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("doc_id") not in delete_set:
                                fout.write(line)
                                kept += 1
                        except json.JSONDecodeError:
                            fout.write(line)
                            kept += 1

                os.replace(temp_path, self._file_path)

                # 清缓存
                for did in ids:
                    self._cache.pop(did, None)

                return len(ids)
            except Exception as e:
                logger.error("RecordSegment.delete failed: %s", e)
                return 0

    def count(self) -> int:
        if not os.path.exists(self._file_path):
            return 0
        count = 0
        with open(self._file_path, "r") as f:
            for _ in f:
                count += 1
        return count

    def clear(self):
        with self._lock:
            self._cache.clear()
            if os.path.exists(self._file_path):
                os.remove(self._file_path)

    def close(self):
        pass

    # ── 扫描文件 ─────────────────────────────────────────

    def _scan_file(self, target_ids: list[str]) -> dict[str, dict]:
        """扫描 block 文件查找指定 id"""
        results = {}
        target_set = set(target_ids)
        if not target_set or not os.path.exists(self._file_path):
            return results

        with open(self._file_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    did = entry.get("doc_id", "")
                    if did in target_set:
                        results[did] = entry
                        self._cache[did] = entry
                        target_set.discard(did)
                        if not target_set:
                            break
                except json.JSONDecodeError:
                    continue

        return results

    # ── 辅助方法 ─────────────────────────────────────────

    def get_all_ids(self) -> list[str]:
        """获取所有 doc_id"""
        ids = list(self._cache.keys()) if self._cache else []
        if os.path.exists(self._file_path):
            with open(self._file_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        ids.append(entry.get("doc_id", ""))
                    except json.JSONDecodeError:
                        continue
        return list(set(ids))
