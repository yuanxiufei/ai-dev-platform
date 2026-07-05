"""终端快速修复 API (Session 47) — 对标 VSCode terminalContrib/quickFix"""
import re, logging
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/system/terminal/quickfix", tags=["terminal-quickfix"])
logger = logging.getLogger(__name__)

class TQRequest(BaseModel):
    output: str = Field(..., description="终端输出最后几行")
    last_command: str = Field(default="")
    working_directory: str = Field(default="")

class QuickFixAction(BaseModel):
    id: str; label: str; description: str = ""; command: str = ""
    tooltip: str = ""; severity: str = "info"

class QuickFixCategory(BaseModel):
    category: str; pattern_matched: str = ""
    suggestions: list[QuickFixAction] = []

class TQResponse(BaseModel):
    has_issues: bool = False
    categories: list[QuickFixCategory] = []
    summary: str = ""

class TExplainRequest(BaseModel):
    output: str; last_command: str = ""

class TExplainResponse(BaseModel):
    error_type: str = "unknown"
    explanation: str = ""
    suggestions: list[str] = []

# ── 错误模式: (regex, category, label) ──
ERROR_PATTERNS = [
    (r"(?:command not found|不是内部或外部命令|is not recognized)", "cmd-not-found", "命令未找到"),
    (r"No module named '(\w+)'", "python-module", "Python 模块未安装"),
    (r"(?:[Pp]ermission denied|EACCES|Access is denied)", "permission", "权限不足"),
    (r"(?:port \d+ already in use|address already in use)", "port-in-use", "端口已被占用"),
    (r"(?:fatal:|error:).*[Pp]ermission denied.*git", "git-auth", "Git 认证问题"),
    (r"error: failed to push some refs to", "git-push-rejected", "Git 推送被拒绝"),
    (r"You have divergent branches", "git-divergent", "Git 分支分叉"),
    (r"fatal: not a git repository", "git-not-repo", "非 Git 仓库"),
    (r"Please tell me who you are", "git-config", "Git 未配置用户"),
    (r"CONFLICT.*Merge conflict", "git-merge-conflict", "Git 合并冲突"),
    (r"(?:Could not resolve host|Name or service not known)", "dns-error", "DNS 解析失败"),
    (r"(?:Connection refused|Failed to connect)", "connection-refused", "连接被拒绝"),
    (r"(?:SSL.*certificate.*verify|SSL.*证书)", "ssl-error", "SSL 证书错误"),
    (r"(?:node_modules.*not found|npm ERR!|pnpm ERR!|yarn ERR!)", "npm-error", "包管理器错误"),
    (r"Error: Cannot find module", "node-module", "Node 模块未找到"),
    (r"docker: Cannot connect to the Docker daemon", "docker-daemon", "Docker 未运行"),
    (r"SyntaxError.*invalid syntax", "python-syntax", "Python 语法错误"),
    (r"No such file or directory", "file-not-found", "文件不存在"),
    (r"(?:No space left on device|Disk quota exceeded)", "disk-full", "磁盘空间不足"),
    (r"npm ERR!.*ERESOLVE", "npm-eresolve", "npm 依赖冲突"),
]

FIX_MAP = {
    "cmd-not-found": [("install-suggest","🔍 搜索安装方法","","","info")],
    "python-module": [("pip-install","📦 pip install {module}","","pip install {module}","安装缺失的 Python 模块","info")],
    "permission": [("sudo-retry","🔐 以 sudo 重试","","sudo {cmd}","需要管理员权限","warning")],
    "port-in-use": [("kill-port","💀 终止端口进程","","lsof -ti :{port} | xargs kill -9","终止占用端口的进程","warning")],
    "git-auth": [("git-config","👤 配置 Git SSH","","ssh -T git@github.com","验证 SSH 配置","error")],
    "git-push-rejected": [("git-pull","🔄 git pull --rebase","","git pull --rebase origin $(git branch --show-current)","先同步远程再推送","warning")],
    "git-divergent": [("git-merge","🔄 git merge","","git merge origin/$(git branch --show-current)","合并远程分支","info")],
    "git-merge-conflict": [("git-abort","⏪ 放弃合并","","git merge --abort","取消合并","warning"),("git-status","📋 查看冲突","","git status","","info")],
    "git-not-repo": [("git-init","📂 git init","","git init","初始化 Git 仓库","info")],
    "git-config": [("set-user",'👤 git config user.name "..."',"","git config --global user.name \"Your Name\" && git config --global user.email \"email@example.com\"","设置 Git 身份","info")],
    "dns-error": [("ping-test","🌐 测试网络","","ping -c 3 8.8.8.8","验证网络连通","info")],
    "connection-refused": [("curl-test","🌐 curl 测试","","curl -v http://localhost","测试连接","info")],
    "ssl-error": [("trusted-host","🔒 pip --trusted-host","","pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org <package>","内网环境跳过 SSL","warning")],
    "npm-error": [("npm-install","📦 npm install","","npm install","重新安装依赖","info")],
    "node-module": [("npm-install","📦 npm install","","npm install","安装缺失的 Node 模块","info")],
    "docker-daemon": [("docker-start","🐳 启动 Docker","","sudo systemctl start docker","启动 Docker 守护进程","warning")],
    "python-syntax": [("check-syntax","🔍 检查 Python 语法","","python -m py_compile <file>","编译检查语法","error")],
    "file-not-found": [("ls-dir","📂 ls 目录","","ls -la","查看当前目录","info")],
    "disk-full": [("df-check","📊 检查磁盘","","df -h","查看磁盘使用","error")],
    "npm-eresolve": [("npm-legacy","📦 npm install --legacy-peer-deps","","npm install --legacy-peer-deps","使用宽松依赖解析","warning")],
}

def _extract_args(m: re.Match, c: str, cmd: str) -> tuple[str, str]:
    """提取 module/port/cmd 参数"""
    kw = ""
    if c == "python-module" and m.groups():
        kw = m.group(1)
    elif c == "port-in-use":
        pm = re.search(r'port (\d+)', m.group(0), re.IGNORECASE)
        kw = pm.group(1) if pm else ""
    return kw.replace("{module}", kw).replace("{port}", kw), cmd.replace("{module}", kw).replace("{port}", kw).replace("{cmd}", cmd)

@router.post("", response_model=TQResponse)
async def terminal_quickfix(req: TQRequest):
    """分析终端输出，返回修复建议列表"""
    if not req.output.strip():
        return TQResponse()
    cats: list[QuickFixCategory] = []
    for pattern, cat, label in ERROR_PATTERNS:
        m = re.search(pattern, req.output, re.IGNORECASE | re.MULTILINE)
        if not m: continue
        fx = []
        for f_id, f_label, f_desc, f_cmd, f_tip, f_sev in FIX_MAP.get(cat, []):
            kw, new_cmd = _extract_args(m, cat, req.last_command)
            fx.append(QuickFixAction(id=f_id, label=f_label, description=f_desc,
                         command=f_cmd, tooltip=f_tip, severity=f_sev))
        cats.append(QuickFixCategory(category=cat, pattern_matched=label, suggestions=fx))
    summary = f"检测到 {len(cats)} 个问题" if cats else "无已知问题"
    return TQResponse(has_issues=bool(cats), categories=cats, summary=summary)

@router.post("/explain", response_model=TExplainResponse)
async def explain_terminal_error(req: TExplainRequest):
    """解释终端错误输出"""
    if not req.output.strip():
        return TExplainResponse()
    for pattern, cat, label in ERROR_PATTERNS:
        if re.search(pattern, req.output, re.IGNORECASE):
            return TExplainResponse(
                error_type=cat, explanation=label,
                suggestions=[s.label for s in [QuickFixAction(**{k:v for k,v in zip(["id","label","description","command","tooltip","severity"],a)}) for a in FIX_MAP.get(cat, [])] if s]
            )
    return TExplainResponse(error_type="unknown", explanation="未识别的错误模式",
        suggestions=["复制错误信息并尝试搜索", "使用 --help 查看命令用法"])
