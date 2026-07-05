"""
Keybindings Export API — 快捷键导出

对标 VSCode workbench/contrib/keybindingsExport
将当前配置的快捷键导出为平台特定的 JSON 文件。

路由:
  GET /api/v1/system/keybindings/export?platform=win
  GET /api/v1/system/keybindings/export?platform=mac
  GET /api/v1/system/keybindings/export?platform=linux

导出格式 (VSCode 标准):
  [
    { "key": "Ctrl+Shift+P", "command": "workbench.action.showCommands", "when": "global" },
    ...
  ]
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Query, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/system/keybindings", tags=["keybindings"])

# ── 平台键位映射 ──
# Windows 上 Alt 标记为 Alt, macOS 上 Alt 标记为 Option
PLATFORM_KEY_MODS = {
    "win": {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "meta": "Win"},
    "mac": {"ctrl": "⌃", "shift": "⇧", "alt": "⌥", "meta": "⌘"},
    "linux": {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "meta": "Super"},
}

# 各平台默认键位优先级
PLATFORM_NAMES = {
    "win": "Windows",
    "mac": "macOS",
    "linux": "Linux",
}

# 默认快捷键定义 (与前端 useKeybindingStore 保持同步)
DEFAULT_KEYBINDINGS = [
    {"key": "Ctrl+Shift+P", "command": "workbench.action.showCommands", "when": "global"},
    {"key": "Ctrl+P", "command": "workbench.action.quickOpen", "when": "global"},
    {"key": "F1", "command": "workbench.action.showCommands", "when": "global"},
    {"key": "Ctrl+S", "command": "workbench.action.files.save", "when": "editor"},
    {"key": "Ctrl+W", "command": "workbench.action.closeActiveEditor", "when": "editor"},
    {"key": "Ctrl+\\", "command": "workbench.action.splitEditor", "when": "editor"},
    {"key": "Ctrl+Shift+E", "command": "workbench.view.explorer", "when": "global"},
    {"key": "Ctrl+`", "command": "workbench.action.terminal.toggle", "when": "global"},
    {"key": "Ctrl+B", "command": "workbench.action.toggleSidebarVisibility", "when": "global"},
    {"key": "Ctrl+J", "command": "workbench.action.togglePanel", "when": "global"},
    {"key": "Ctrl+Shift+F", "command": "workbench.action.findInFiles", "when": "global"},
    {"key": "Ctrl+N", "command": "workbench.action.files.newUntitledFile", "when": "global"},
    {"key": "Ctrl+T", "command": "workbench.action.gotoSymbol", "when": "global"},
    {"key": "Ctrl+Shift+V", "command": "markdown.showPreview", "when": "editor"},
    {"key": "Ctrl+K V", "command": "markdown.showPreviewToSide", "when": "editor"},
    {"key": "Ctrl+Shift+T", "command": "workbench.action.focusCallHierarchy", "when": "global"},
    {"key": "Ctrl+Shift+Y", "command": "workbench.action.focusLocalHistory", "when": "global"},
    {"key": "Ctrl+K Ctrl+H", "command": "workbench.action.focusTypeHierarchy", "when": "editor"},
    {"key": "Ctrl+Shift+C", "command": "workbench.action.focusComments", "when": "global"},
    {"key": "Ctrl+Shift+M", "command": "workbench.action.focusMergeConflicts", "when": "global"},
    {"key": "Ctrl+Shift+Alt+B", "command": "workbench.action.toggleBlame", "when": "editor"},
    {"key": "Ctrl+Shift+B", "command": "workbench.action.focusTasks", "when": "global"},
    {"key": "Ctrl+I", "command": "workbench.action.inlineChat", "when": "editor"},
    {"key": "Ctrl+Shift+U", "command": "workbench.action.openSearchEditor", "when": "global"},
    {"key": "Ctrl+Shift+D", "command": "workbench.action.openMultiDiff", "when": "global"},
    {"key": "Ctrl+Shift+Alt+L", "command": "workbench.action.toggleLockedScrolling", "when": "global"},
    # VSCode 原生快捷键 (用户可能覆盖)
    {"key": "Ctrl+Z", "command": "undo", "when": "editor"},
    {"key": "Ctrl+Y", "command": "redo", "when": "editor"},
    {"key": "Ctrl+X", "command": "editor.action.clipboardCutAction", "when": "editor"},
    {"key": "Ctrl+C", "command": "editor.action.clipboardCopyAction", "when": "editor"},
    {"key": "Ctrl+V", "command": "editor.action.clipboardPasteAction", "when": "editor"},
    {"key": "Ctrl+A", "command": "editor.action.selectAll", "when": "editor"},
    {"key": "Ctrl+F", "command": "editor.action.startFindReplaceAction", "when": "editor"},
    {"key": "Ctrl+H", "command": "editor.action.startFindReplaceAction", "when": "editor"},
    {"key": "Ctrl+D", "command": "editor.action.addSelectionToNextFindMatch", "when": "editor"},
    {"key": "Ctrl+K Ctrl+C", "command": "editor.action.addCommentLine", "when": "editor"},
    {"key": "Ctrl+K Ctrl+U", "command": "editor.action.removeCommentLine", "when": "editor"},
    {"key": "Ctrl+/", "command": "editor.action.commentLine", "when": "editor"},
    {"key": "Alt+Up", "command": "editor.action.moveLinesUpAction", "when": "editor"},
    {"key": "Alt+Down", "command": "editor.action.moveLinesDownAction", "when": "editor"},
    {"key": "Ctrl+Shift+K", "command": "editor.action.deleteLines", "when": "editor"},
    {"key": "Ctrl+Enter", "command": "editor.action.insertLineAfter", "when": "editor"},
    {"key": "Ctrl+Shift+Enter", "command": "editor.action.insertLineBefore", "when": "editor"},
    {"key": "Ctrl+Shift+\\", "command": "editor.action.jumpToBracket", "when": "editor"},
    {"key": "Ctrl+]", "command": "editor.action.indentLines", "when": "editor"},
    {"key": "Ctrl+[", "command": "editor.action.outdentLines", "when": "editor"},
    {"key": "Ctrl+Home", "command": "cursorTop", "when": "editor"},
    {"key": "Ctrl+End", "command": "cursorBottom", "when": "editor"},
    {"key": "Ctrl+G", "command": "workbench.action.gotoLine", "when": "editor"},
    {"key": "Ctrl+Shift+O", "command": "workbench.action.gotoSymbol", "when": "editor"},
    {"key": "F2", "command": "editor.action.rename", "when": "editor"},
    {"key": "F8", "command": "editor.action.marker.nextInFiles", "when": "global"},
    {"key": "Shift+F8", "command": "editor.action.marker.prevInFiles", "when": "global"},
    {"key": "F11", "command": "workbench.action.toggleFullScreen", "when": "global"},
    {"key": "Ctrl+K Z", "command": "workbench.action.toggleZenMode", "when": "global"},
    {"key": "Ctrl+Shift+L", "command": "editor.action.selectHighlights", "when": "editor"},
    {"key": "Ctrl+F2", "command": "editor.action.changeAll", "when": "editor"},
    {"key": "F12", "command": "editor.action.goToDefinition", "when": "editor"},
    {"key": "Ctrl+F12", "command": "editor.action.goToImplementation", "when": "editor"},
    {"key": "Shift+F12", "command": "editor.action.referenceSearch.trigger", "when": "editor"},
    {"key": "Ctrl+.", "command": "editor.action.quickFix", "when": "editor"},
    {"key": "Ctrl+Space", "command": "editor.action.triggerSuggest", "when": "editor"},
    {"key": "Ctrl+Shift+Space", "command": "editor.action.triggerParameterHints", "when": "editor"},
    {"key": "Ctrl+K Ctrl+F", "command": "editor.action.formatDocument", "when": "editor"},
    {"key": "Ctrl+Shift+I", "command": "editor.action.formatSelection", "when": "editor"},
    {"key": "Ctrl+K Ctrl+X", "command": "editor.toggleStickyScroll", "when": "editor"},
    {"key": "F6", "command": "workbench.action.focusNextPart", "when": "global"},
    {"key": "Shift+F6", "command": "workbench.action.focusPreviousPart", "when": "global"},
]


def _translate_key_for_platform(key: str, platform: str) -> str:
    """将通用键位映射为平台特定展示格式。

    Args:
        key: 通用快捷键字符串 (如 "Ctrl+Shift+P")
        platform: "win" | "mac" | "linux"

    Returns:
        平台特定的快捷键字符串
    """
    mods = PLATFORM_KEY_MODS.get(platform, PLATFORM_KEY_MODS["win"])

    if platform == "mac":
        # macOS 风格: ⌘⇧P
        key = key.replace("Ctrl+", "⌘")
        key = key.replace("⌘", "⌘+", 1) if "⌘+" not in key else key
        key = key.replace("Shift+", "⇧")
        key = key.replace("Alt+", "⌥")
        key = key.replace("Win+", "⌘")
        # 清理多余的 +
        key = key.replace("++", "+").rstrip("+")
    else:
        # Windows/Linux 风格保持不变 (Ctrl+Shift+P)
        pass

    return key


@router.get("/export")
async def export_keybindings(
    platform: str = Query("win", description="目标平台: win, mac, linux"),
):
    """导出当前平台的快捷键绑定为 JSON 文件。

    对标 VSCode 的 keybindingsExport.contribution.ts，
    生成平台特定的键盘快捷键参考文档。

    Args:
        platform: 目标平台 (win | mac | linux)

    Returns:
        StreamingResponse: JSON 文件下载
    """
    if platform not in ("win", "mac", "linux"):
        platform = "win"

    # 生成平台特定的键位映射
    result = []
    for binding in DEFAULT_KEYBINDINGS:
        translated_key = _translate_key_for_platform(binding["key"], platform)
        result.append({
            "key": translated_key,
            "command": binding["command"],
            "when": binding.get("when", "global"),
        })

    # 排序：先 global 后 editor
    result.sort(key=lambda x: (0 if x["when"] == "global" else 1, x["command"]))

    content = json.dumps(result, indent=2, ensure_ascii=False)

    filename = f"keybindings.{platform}.json"
    plat_name = PLATFORM_NAMES.get(platform, "Windows")

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Platform": plat_name,
            "X-Total-Bindings": str(len(result)),
        },
    )


@router.get("/list")
async def list_keybindings(
    platform: str = Query("win", description="目标平台: win, mac, linux"),
):
    """列出当前平台的快捷键绑定（不下载，直接返回 JSON 数组）。

    Args:
        platform: 目标平台 (win | mac | linux)

    Returns:
        dict: { bindings: [...], platform: str, total: int }
    """
    if platform not in ("win", "mac", "linux"):
        platform = "win"

    result = []
    for binding in DEFAULT_KEYBINDINGS:
        translated_key = _translate_key_for_platform(binding["key"], platform)
        result.append({
            "key": translated_key,
            "command": binding["command"],
            "when": binding.get("when", "global"),
        })

    result.sort(key=lambda x: (0 if x["when"] == "global" else 1, x["command"]))

    return {
        "platform": PLATFORM_NAMES.get(platform, "Windows"),
        "total": len(result),
        "bindings": result,
    }
