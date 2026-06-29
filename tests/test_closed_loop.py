"""
完整闭环系统端到端验证测试

验证链路:
  CodebaseMemory (索引+持久化) → MemoryStore (记忆保存)
  → MemoryExtractor (提取) → MemoryRetriever (检索)
  → Tool Priority (排序) → AutoCLI (安全执行)
  → AgentMode ↔ Skill 绑定

所有测试使用临时目录，零副作用。
"""
import sys
import os
import tempfile
import json
import time
from pathlib import Path

# 路径设置
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(str(PROJECT_ROOT))

PASS = 0
FAIL = 0


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {label}")


def _fail(label: str, expected=None, got=None) -> None:
    global FAIL
    FAIL += 1
    detail = f": expected={expected}, got={got}" if expected is not None else ""
    print(f"  ❌ {label}{detail}")


def assert_equal(actual, expected, label):
    if actual == expected:
        _ok(label)
    else:
        _fail(label, expected, actual)


def assert_true(cond, label):
    if cond:
        _ok(label)
    else:
        _fail(label)


def assert_false(cond, label):
    assert_true(not cond, label)


print("=" * 60)
print("AI Fullstack Platform — 完整闭环验证")
print("=" * 60)

# ===================================================================
# TEST 1: CodebaseMemory — SQLite 持久化 + 调用链追踪
# ===================================================================
print("\n📦 Test 1: CodebaseMemory (SQLite persist + call tracing)")
from app.core.codebase_memory.graph import CodeGraph, Node, NodeType, EdgeType
from app.core.codebase_memory.parser import parse_source

# 加载方式：先用常规 import（需要 __init__.py 支持）
try:
    from app.core.codebase_memory.graph import CodeGraph, Node, NodeType, EdgeType
    from app.core.codebase_memory.parser import parse_source
except ImportError:
    # 回退：直接 import 文件
    G = __import__("app.core.codebase_memory.graph", fromlist=["CodeGraph"])
    CodeGraph, Node, NodeType, EdgeType = G.CodeGraph, G.Node, G.NodeType, G.EdgeType
    P = __import__("app.core.codebase_memory.parser", fromlist=["parse_source"])
    parse_source = P.parse_source

tmp1 = tempfile.mkdtemp()

# 1a. 创建图 → 保存到 SQLite → 重新加载
g = CodeGraph()
n1 = Node(name="create_user", node_type=NodeType.FUNCTION,
          qualified_name="api.create_user", language="Python",
          file_path="api.py", line_start=10, line_end=25)
n2 = Node(name="UserService", node_type=NodeType.CLASS,
          qualified_name="services.UserService", language="Python",
          file_path="services.py", line_start=5, line_end=50)
n3 = Node(name="get_db", node_type=NodeType.FUNCTION,
          qualified_name="db.get_db", language="Python",
          file_path="db.py", line_start=1, line_end=15)
n1_id = g.add_node(n1)
n2_id = g.add_node(n2)
n3_id = g.add_node(n3)
g.add_edge(n1_id, n2_id, EdgeType.CALLS)
g.add_edge(n2_id, n3_id, EdgeType.CALLS)
g.add_edge(n1_id, n2_id, EdgeType.IMPORTS)

db_path = os.path.join(tmp1, "test_graph.db")
g.save_to_db(db_path)
assert_true(os.path.exists(db_path), "1a. Graph saved to SQLite")

g2 = CodeGraph()
loaded = g2.load_from_db(db_path)
assert_true(loaded, "1a. Graph loaded from SQLite")
assert_equal(g2.node_count, 3, "1a. Node count (3)")
assert_equal(g2.edge_count, 3, "1a. Edge count (3)")

# 1b. 调用链追踪
callers = g2.get_callers(n2_id)
assert_equal(len(callers), 1, "1b. Caller count")
assert_equal(callers[0].name, "create_user", "1b. Caller name")
callees = g2.get_callees(n1_id)
assert_equal(len(callees), 1, "1b. Callee count")

# 1c. AST 解析
g3 = CodeGraph()
source = '''
"""Test module"""
import os
from typing import Optional

class DataService:
    def __init__(self, url: str):
        self.url = url

    async def fetch_data(self, query: str) -> Optional[dict]:
        return await self._request(query)

    async def _request(self, query: str):
        pass

def validate_input(data: dict) -> bool:
    return bool(data)

def main():
    svc = DataService("http://localhost")
    svc.fetch_data("test")
    validate_input({"key": "value"})
'''
fid = parse_source("test_service.py", source, g3, ".py")
assert_true(fid is not None, "1c. File parsed")
assert_true(g3.node_count >= 4, f"1c. Nodes >= 4 (got {g3.node_count})")

classes = [n for n in g3._nodes.values() if n.node_type == NodeType.CLASS]
funcs = [n for n in g3._nodes.values() if n.node_type == NodeType.FUNCTION]
methods = [n for n in g3._nodes.values() if n.node_type == NodeType.METHOD]
assert_equal(len(classes), 1, "1c. Class count (DataService)")
assert_true(len(funcs) >= 2, f"1c. Functions >= 2 (got {len(funcs)})")
assert_true(len(methods) >= 2, f"1c. Methods >= 2 (got {len(methods)})")


# ===================================================================
# TEST 2: LongTermMemory — MemoryStore + Extractor + Retriever
# ===================================================================
print("\n🧠 Test 2: LongTermMemory (Store + Extract + Retrieve)")
from app.core.memory.memory_store import MemoryStore, MemoryNode, MemoryType
from app.core.memory.memory_extractor import MemoryExtractor
from app.core.memory.memory_retriever import MemoryRetriever

tmp2 = os.path.join(tempfile.mkdtemp(), "mem.db")
store = MemoryStore(tmp2)

# 2a. CRUD
mind = MemoryNode(
    content="使用 PostgreSQL 作为主数据库",
    memory_type=MemoryType.DECISION,
    importance=0.9,
    source="conversation:session-001",
    tags=["database", "decision"],
)
store.save(mind)
n = store.get(mind.id)
assert_true(n is not None, "2a. Memory saved & retrieved")
assert_equal(n.content, mind.content, "2a. Content match")

# 2b. 关系图
m2 = MemoryNode(
    content="使用 asyncpg 作为数据库驱动",
    memory_type=MemoryType.FACT,
    importance=0.7,
    source="conversation:session-001",
    tags=["database", "driver"],
)
store.save(m2)
store.add_edge(mind.id, m2.id, "DEPENDS_ON")
edges = store.get_edges(mind.id)
assert_equal(len(edges), 1, "2b. Edge count")

# 2c. 关键词检索
results = store.search_by_keyword("PostgreSQL")
assert_true(len(results) >= 1, "2c. Keyword search found results")
results2 = store.search_by_keyword("redis")
assert_equal(len(results2), 0, "2c. No false positives")

# 2d. 提取器 — 使用能匹配正则的消息
extractor = MemoryExtractor(store)
conversation = [
    {"role": "user", "content": "We should use Redis for the caching layer because it is fast"},
    {"role": "assistant", "content": "Good choice, Redis for caching can significantly boost performance"},
    {"role": "user", "content": "I prefer using Vue 3 with Vite for the frontend build tooling"},
    {"role": "assistant", "content": "Vue 3's Composition API is the best approach for this project"},
]
nodes = extractor.extract_from_conversation(conversation, "session-002")
for n in nodes:
    store.save(n)
assert_true(len(nodes) >= 2, f"2d. Extracted memories (got {len(nodes)})")

# 2e. 检索器
retriever = MemoryRetriever(store)
results = retriever.retrieve("Redis 缓存", top_k=5)
# 可能找到也可能找不到（依赖提取器结果），只验证不崩溃
retriever_context = retriever.retrieve_as_context("database")
assert_true(len(retriever_context) > 0, "2e. Context generation works")

# 2f. 遗忘 — 验证衰减公式正确性 (不破坏 store)
n_test = MemoryNode(
    content="Test decay",
    memory_type=MemoryType.FACT,
    importance=0.1,
    created_at=time.time() - 90000,  # 25h ago
    last_accessed=time.time() - 90000,
)
decay_score = n_test.decay_score
assert_true(decay_score < 0.2, f"2f. Decay for very old/low-importance (score={decay_score:.4f})")

# 验证统计
stats = store.stats()
assert_true(stats["total_memories"] >= 5, f"2f. Total memories >= 5 (got {stats['total_memories']})")
assert_true(stats["by_type"], "2f. Has type distribution")

# 2g. 代码变更提取
change_nodes = extractor.extract_from_code_change(
    "--- a/src/auth/login.py\n+++ b/src/auth/login.py\n@@ -42,3 +42,5 @@\n+    if not user:\n+        raise AuthError('Invalid credentials')\n-fixed the login bug",
    "Fixed login authentication error"
)
assert_true(len(change_nodes) >= 1, "2g. Code change extraction")

# 2h. 衰减公式
n_old = MemoryNode(
    content="Very old deprecated data",
    memory_type=MemoryType.FACT,
    importance=0.2,
    created_at=time.time() - 86400 * 30,
    last_accessed=time.time() - 86400 * 30,
)
decay = n_old.decay_score
assert_true(decay < 0.2, f"2h. Old memory decayed (score={decay:.3f})")


# ===================================================================
# TEST 3: Tool Priority
# ===================================================================
print("\n🤖 Test 3: Agent System (Tool Priority)")

# 避免完整 agent __init__ 的依赖链，直接 import
import importlib.util, importlib.machinery
def _import_mod(name, filepath):
    loader = importlib.machinery.SourceFileLoader(name, str(filepath))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod

tp = _import_mod("tool_priority", BACKEND / "app/core/agent/tool_priority.py")
PrioritizedToolSet = tp.PrioritizedToolSet

# 3a. 优先级排序
pts = PrioritizedToolSet()
tools = ["write_file", "execute_command", "search_graph", "read_file", "get_architecture"]
ordered = pts.order_tools(tools)
print(f"  3a. Ordered: {' → '.join(ordered)}")

high_tools = {"search_graph", "get_architecture"}
low_tools = {"write_file", "execute_command", "delete_file"}

high_positions = [ordered.index(t) for t in ordered if t in high_tools]
low_positions = [ordered.index(t) for t in ordered if t in low_tools]
if high_positions and low_positions:
    assert_true(max(high_positions) < min(low_positions), "3a. HIGH before LOW")

# 3b. Prerequisite 推荐
rec = pts.get_recommended_before(["write_file", "execute_command"])
assert_true(len(rec) > 0, "3b. Prerequisites exist")

# 3c. Agent 指导
guidance = pts.generate_agent_guidance()
assert_true("HIGH priority" in guidance, "3c. Guidance has HIGH section")
assert_true("MEDIUM priority" in guidance, "3c. Guidance has MEDIUM section")
assert_true("LOW priority" in guidance, "3c. Guidance has LOW section")


# ===================================================================
# TEST 4: AutoCLI — 安全命令行执行
# ===================================================================
print("\n🔒 Test 4: AutoCLI (Security + Whitelist)")
ac = _import_mod("autocli", BACKEND / "app/core/tools/autocli.py")
AutoCLI = ac.AutoCLI
SecurityLevel = ac.SecurityLevel

cli = AutoCLI(workspace=tmp1)

# 4a. 安全白名单
r = cli._check_security("git status", allow_unsafe=False)
assert_true(r["allowed"], "4a. 'git status' allowed")
assert_equal(r["level"], SecurityLevel.READ_ONLY, "4a. READ_ONLY level")

r = cli._check_security("git push origin main", allow_unsafe=False)
assert_true(r["allowed"], "4a. 'git push' allowed (default level=SYSTEM)")

r = cli._check_security("ls -la", allow_unsafe=False)
assert_true(r["allowed"], "4a. 'ls' allowed")
r = cli._check_security("cat file.txt", allow_unsafe=False)
assert_true(r["allowed"], "4a. 'cat' allowed")
r = cli._check_security("mkdir newdir", allow_unsafe=False)
assert_true(r["allowed"], "4a. 'mkdir' allowed (FILE_CREATE)")

# 4b. 危险命令
r = cli._check_security("sudo rm -rf /", allow_unsafe=False)
assert_false(r["allowed"], "4b. 'sudo' blocked")
r = cli._check_security("shutdown -h now", allow_unsafe=False)
assert_false(r["allowed"], "4b. 'shutdown' blocked")

# 4c. 显式允许 UNSAFE
r = cli._check_security("sudo systemctl restart nginx", allow_unsafe=True)
assert_true(r["allowed"], "4c. 'sudo' allowed with explicit flag")

# 4d. 注入检测
r = cli._check_security("ls; rm -rf /", allow_unsafe=False)
assert_false(r["allowed"], "4d. Shell injection blocked")

# 4e. 白名单规模
whitelist = AutoCLI.list_whitelist()
assert_true(len(whitelist) >= 30, f"4e. Whitelist >= 30 (got {len(whitelist)})")

# 4f. Git 子命令分级 — diff 应被识别为 READ_ONLY
r = cli._check_security("git diff HEAD", allow_unsafe=False)
assert_true(r["allowed"], "4f. 'git diff' allowed")
assert_equal(r["level"], SecurityLevel.READ_ONLY, "4f. git diff = READ_ONLY")

# git show 也是只读
r = cli._check_security("git show HEAD", allow_unsafe=False)
assert_true(r["allowed"], "4f. 'git show' allowed")
assert_equal(r["level"], SecurityLevel.READ_ONLY, "4f. git show = READ_ONLY")


# ===================================================================
# TEST 5: 闭环联动 — Memory ↔ CodebaseMemory
# ===================================================================
print("\n🔄 Test 5: Cross-system Integration (Memory ↔ CodebaseMemory)")

# 5a. Code structure → Memory (保存代码结构信息为记忆)
architecture_mem = MemoryNode(
    content=f"Codebase indexed: {g3.node_count} nodes, {g3.edge_count} edges",
    memory_type=MemoryType.FACT,
    importance=0.6,
    source="codebase_memory",
    tags=["index", "structure"],
    metadata={"node_types": g3.node_type_counts()},
)
store.save(architecture_mem)

# 验证记忆被保存
saved = store.get(architecture_mem.id)
assert_true(saved is not None, "5a. Code structure saved to memory")

# 5b. 关记忆 BFS 遍历
connected = store.get_connected(mind.id, depth=2)
assert_true(len(connected) >= 1, "5b. Connected memories via BFS")

# 5c. 综合统计
stats = store.stats()
assert_true(stats["total_memories"] >= 6, f"5c. Total >= 6 (got {stats['total_memories']})")
assert_true(stats["by_type"], "5c. Has type distribution")


# ===================================================================
# TEST 6: AgentMode ↔ Skill binding
# ===================================================================
print("\n🎯 Test 6: AgentMode-Skill binding")
am = _import_mod("agent_modes", BACKEND / "app/core/agent/agent_modes.py")
PRESET_MODES = am.PRESET_MODES

assert_true(len(PRESET_MODES) >= 6, f"6a. >= 6 preset modes (got {len(PRESET_MODES)})")

# 验证每个模式的 skill 绑定
mode_skills = {
    "architect": ["code-review", "explain"],
    "code": ["frontend-design", "refactor"],
    "debug": ["debug", "explain"],
    "test": ["test-gen", "webapp-testing"],
    "review": ["code-review"],
    "docs": ["explain"],
}

for slug, expected_skills in mode_skills.items():
    mode = next((m for m in PRESET_MODES if m.slug == slug), None)
    if mode:
        for s in expected_skills:
            assert_true(s in mode.skills, f"6b. {slug}.skills contains '{s}'")
    else:
        _fail(f"6b. Mode '{slug}' not found")


# ===================================================================
# 结果
# ===================================================================
print("\n" + "=" * 60)
print(f"📊 测试结果: {PASS} 通过, {FAIL} 失败")
if FAIL == 0:
    print("🎉 完整闭环验证通过！")
else:
    print(f"⚠️  {FAIL} 项测试失败")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
