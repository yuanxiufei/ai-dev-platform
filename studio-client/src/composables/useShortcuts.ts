/**
 * Global Shortcut System - Command Palette & Keybinding Registry
 */
import { reactive, ref } from "vue"

export interface ShortcutDefinition {
  id: string
  title: string
  category: string
  key: string
  when?: string
  icon?: string
  handler: () => void | Promise<void>
}

export interface CommandPaletteItem extends ShortcutDefinition {
  score?: number
  keywords: string[]
}

const defaultCommands: Omit<ShortcutDefinition, "handler">[] = [
  {
    id: "file.new",
    title: "新建文件",
    category: "文件",
    key: "Ctrl+N",
    icon: "FilePlus",
  },
  {
    id: "file.open",
    title: "打开文件...",
    category: "文件",
    key: "Ctrl+O",
    icon: "FolderOpen",
  },
  {
    id: "file.save",
    title: "保存",
    category: "文件",
    key: "Ctrl+S",
    icon: "Save",
  },
  { id: "file.saveAll", title: "全部保存", category: "文件", key: "Ctrl+K S" },
  {
    id: "file.closeEditor",
    title: "关闭编辑器",
    category: "文件",
    key: "Ctrl+W",
  },
  {
    id: "edit.undo",
    title: "撤销",
    category: "编辑",
    key: "Ctrl+Z",
    icon: "Undo2",
  },
  {
    id: "edit.redo",
    title: "重做",
    category: "编辑",
    key: "Ctrl+Y",
    icon: "Redo",
  },
  {
    id: "edit.find",
    title: "查找",
    category: "编辑",
    key: "Ctrl+F",
    icon: "Search",
  },
  { id: "edit.replace", title: "替换", category: "编辑", key: "Ctrl+H" },
  {
    id: "edit.findInFiles",
    title: "在文件中查找",
    category: "编辑",
    key: "Ctrl+Shift+F",
  },
  {
    id: "view.commandPalette",
    title: "命令面板...",
    category: "视图",
    key: "Ctrl+Shift+P",
  },
  {
    id: "view.toggleSidebar",
    title: "切换侧边栏",
    category: "视图",
    key: "Ctrl+B",
    icon: "PanelLeftClose",
  },
  {
    id: "view.togglePanel",
    title: "切换面板",
    category: "视图",
    key: "Ctrl+J",
    icon: "PanelBottomClose",
  },
  {
    id: "nav.quickOpen",
    title: "快速打开文件...",
    category: "导航",
    key: "Ctrl+P",
    icon: "FileSearch",
  },
  {
    id: "terminal.toggle",
    title: "切换终端",
    category: "终端",
    key: "Ctrl+`",
    icon: "Terminal",
  },
  {
    id: "ai.chatPanel",
    title: "AI 对话面板",
    category: "AI",
    key: "Ctrl+L",
    icon: "MessageSquare",
  },
  {
    id: "settings.open",
    title: "设置",
    category: "偏好设置",
    key: "Ctrl+,",
    icon: "Settings",
  },
  {
    id: "view.resetLayout",
    title: "重置布局",
    category: "视图",
    key: "",
    icon: "PanelLeftClose",
  },
  {
    id: "dev.openDevTools",
    title: "打开开发工具",
    category: "开发者",
    key: "F12",
    icon: "Code",
  },
]

class ShortcutManager {
  private commands = reactive(new Map<string, ShortcutDefinition>())
  public isCommandPaletteVisible = ref(false)
  public commandPaletteQuery = ref("")
  public activeCategory = ref<string | null>(null)
  /** 🆕 最近使用命令 (Zed 风格) — 记录最近 10 条命令 ID */
  private recentCommandIds: string[] = []
  private readonly MAX_RECENT = 10
  private readonly RECENT_STORAGE_KEY = "ide_recent_commands"

  constructor() {
    this.registerDefaults()
    this.setupGlobalKeybindings()
    this.loadRecentCommands()
  }

  private registerDefaults() {
    for (const cmd of defaultCommands) {
      this.commands.set(cmd.id, { ...cmd, handler: () => {} })
    }
  }

  /** 🆕 记录命令使用 (Zed 最近使用) */
  private recordRecent(id: string) {
    this.recentCommandIds = [
      id,
      ...this.recentCommandIds.filter((r) => r !== id),
    ].slice(0, this.MAX_RECENT)
    try {
      localStorage.setItem(
        this.RECENT_STORAGE_KEY,
        JSON.stringify(this.recentCommandIds),
      )
    } catch {
      /* ignore */
    }
  }

  /** 🆕 加载最近命令 */
  private loadRecentCommands() {
    try {
      const raw = localStorage.getItem(this.RECENT_STORAGE_KEY)
      if (raw) {
        this.recentCommandIds = JSON.parse(raw).slice(0, this.MAX_RECENT)
      }
    } catch {
      this.recentCommandIds = []
    }
  }

  /** 🆕 获取最近使用命令 */
  getRecent(): ShortcutDefinition[] {
    return this.recentCommandIds
      .map((id) => this.commands.get(id))
      .filter(Boolean) as ShortcutDefinition[]
  }

  register(definition: ShortcutDefinition): void {
    this.commands.set(definition.id, definition)
  }

  on(id: string, handler: ShortcutDefinition["handler"]): void {
    const existing = this.commands.get(id)
    if (existing) existing.handler = handler
    else this.register({ id, title: id, category: "自定义", handler })
  }

  async execute(id: string): Promise<void> {
    const cmd = this.commands.get(id)
    if (cmd) {
      this.recordRecent(id) // 🆕 Zed 风格: 记录最近使用
      try {
        await cmd.handler()
      } catch (e) {
        console.error(`[Shortcut] Error ${id}:`, e)
      }
    } else console.warn(`[Shortcut] Unknown: ${id}`)
  }

  getAll(): ShortcutDefinition[] {
    return Array.from(this.commands.values())
  }

  getFiltered(query: string, category?: string | null): CommandPaletteItem[] {
    const ql = query.toLowerCase().trim()
    return this.getAll()
      .filter((item) => !category || item.category === category)
      .map((item) => ({
        ...item,
        keywords: [item.title, item.category, item.id].join(" ").toLowerCase(),
        /** 🆕 Zed 风格: 记录是否为最近使用 */
        _recent: this.recentCommandIds.includes(item.id),
      }))
      .map((item) => ({
        ...item,
        score: this.calculateFuzzyScore(item, ql),
      }))
      .filter((item) => ql === "" || item.score > 0)
      .sort((a, b) => {
        // 🆕 最近使用命令优先
        const recentDiff = (b._recent ? 1 : 0) - (a._recent ? 1 : 0)
        if (recentDiff !== 0) return recentDiff
        return b.score - a.score
      })
  }

  /**
   * 🆕 Zed 风格模糊匹配评分
   * 子串连续匹配 → 高分; 首字母匹配 → 加分; 最近使用 → 额外加分
   */
  private calculateFuzzyScore(
    item: CommandPaletteItem & { _recent?: boolean },
    query: string,
  ): number {
    if (!query) return item._recent ? 50 : 1 // 空查询时最近命令优先
    let score = 0
    // 1. 精确子串匹配 (最高优先级)
    if (item.title.toLowerCase().includes(query)) score += 100
    else if (item.keywords.includes(query)) score += 80
    // 2. 单词前缀匹配 (Zed 风格)
    else {
      for (const word of query.split(/\s+/)) {
        if (!word) continue
        const titleLower = item.title.toLowerCase()
        if (titleLower.startsWith(word)) score += 60
        else if (item.keywords.includes(word)) score += 40
        // 3. 首字母缩写匹配 (Zed 的 "JFP" → "Just File Picker")
        else if (this.matchAbbreviation(word, titleLower)) score += 35
        else if (titleLower.includes(word)) score += 20
      }
    }
    // 4. 最近使用加成
    if (item._recent) score += 15
    return score
  }

  /** 🆕 首字母缩写匹配: "jfp" → "Just File Picker" */
  private matchAbbreviation(abbr: string, title: string): boolean {
    if (abbr.length < 2) return false
    const initials = title
      .split(/\s+/)
      .map((w) => w[0])
      .join("")
    return initials === abbr || initials.startsWith(abbr)
  }

  toggleCommandPalette(show?: boolean) {
    this.isCommandPaletteVisible.value =
      show ?? !this.isCommandPaletteVisible.value
    if (this.isCommandPaletteVisible.value) {
      this.commandPaletteQuery.value = ""
      this.activeCategory.value = null
    }
  }

  private setupGlobalKeybindings() {
    if (typeof window === "undefined") return
    window.addEventListener(
      "keydown",
      (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "P") {
          e.preventDefault()
          e.stopPropagation()
          this.toggleCommandPalette(true)
          return
        }
        if (e.key === "Escape" && this.isCommandPaletteVisible.value) {
          e.preventDefault()
          this.toggleCommandPalette(false)
          return
        }
        this.resolveAndExecute(e)
      },
      true,
    )
  }

  private resolveAndExecute(e: KeyboardEvent) {
    const key = this.normalizeKeyEvent(e)
    const match = this.getAll().find(
      (cmd) => cmd.key === key && this.evaluateWhen(cmd.when),
    )
    if (match) {
      e.preventDefault()
      e.stopPropagation()
      this.execute(match.id)
    }
  }

  private normalizeKeyEvent(e: KeyboardEvent): string {
    const parts: string[] = []
    if (e.ctrlKey) parts.push("Ctrl")
    if (e.metaKey) parts.push("Cmd")
    if (e.altKey) parts.push("Alt")
    if (e.shiftKey && e.key !== "Shift" && e.key.length === 1)
      parts.push("Shift")
    let key = e.key
    if (key === " ") key = "Space"
    if (key.length === 1) key = key.toUpperCase()
    parts.push(key)
    return parts.join("+")
  }

  private evaluateWhen(_when?: string): boolean {
    return true
  }

  getCategories(): string[] {
    return Array.from(new Set(this.getAll().map((c) => c.category))).sort()
  }

  getByKeybinding(key: string): ShortcutDefinition[] {
    return this.getAll().filter((cmd) => cmd.key === key)
  }
}

export const shortcutManager = new ShortcutManager()

export function useShortcuts() {
  return {
    isCommandPaletteVisible: shortcutManager.isCommandPaletteVisible,
    commandPaletteQuery: shortcutManager.commandPaletteQuery,
    activeCategory: shortcutManager.activeCategory,
    register: (def: ShortcutDefinition) => shortcutManager.register(def),
    on: (id: string, fn: ShortcutDefinition["handler"]) =>
      shortcutManager.on(id, fn),
    execute: (id: string) => shortcutManager.execute(id),
    toggleCommandPalette: (show?: boolean) =>
      shortcutManager.toggleCommandPalette(show),
    getAll: () => shortcutManager.getAll(),
    getFiltered: (q: string, c?: string | null) =>
      shortcutManager.getFiltered(q, c),
    getCategories: () => shortcutManager.getCategories(),
    getRecent: () => shortcutManager.getRecent(),
  }
}
