/**
 * Plugin System - Plugin Loading, Lifecycle & API Sandbox
 */
import { computed, reactive } from "vue"

export interface PluginManifest {
  id: string
  name: string
  version: string
  description: string
  author: string
  license?: string
  entry: string
  icon?: string
  category?: string
  contributes?: {
    commands?: PluginCommand[]
    views?: PluginView[]
    menus?: PluginMenuItem[]
    themes?: PluginTheme[]
    languages?: PluginLanguage[]
    keybindings?: PluginKeybinding[]
    configuration?: PluginConfigSchema[]
  }
  dependencies?: Record<string, string>
  activationEvents?: string[]
}
export interface PluginCommand {
  id: string
  title: string
  category?: string
  icon?: string
  when?: string
  handler?: Function
}
export interface PluginView {
  id: string
  type: "sidebar" | "panel" | "editor"
  name: string
  icon?: string
  component?: string
}
export interface PluginMenuItem {
  command: string
  when?: string
  group?: string
  alt?: string
}
export interface PluginTheme {
  id: string
  label: string
  path: string
  uiTheme?: "vs-dark" | "vs" | "hc-black"
}
export interface PluginLanguage {
  id: string
  extensions: string[]
  aliases?: string[]
  configurations?: Record<string, any>
}
export interface PluginKeybinding {
  key: string
  command: string
  when?: string
  mac?: string
  linux?: string
  win?: string
}
export interface PluginConfigSchema {
  properties: Record<
    string,
    {
      type: string
      default?: any
      description?: string
      enum?: string[]
      minimum?: number
      maximum?: number
    }
  >
}
export interface LoadedPlugin extends PluginManifest {
  enabled: boolean
  active: boolean
  status: "loaded" | "activated" | "error" | "disabled"
  error?: string
  api?: PluginAPI
}
export interface PluginAPI {
  editor: {
    getActiveTextEditor: () => any
    getTextEditors: () => any[]
    showTextDocument: (uri: string) => Promise<any>
  }
  window: {
    showInformationMessage: (msg: string) => Promise<string | undefined>
    showErrorMessage: (msg: string) => Promise<void>
    showInputBox: (options?: any) => Promise<string | undefined>
    showQuickPick: (items: any[]) => Promise<any | undefined>
  }
  workspace: {
    rootPath: () => string | undefined
    getConfiguration: (section?: string) => any
    openTextDocument: (path: string) => Promise<any>
    asRelativePath: (absolutePath: string) => string
  }
  commands: {
    registerCommand: (id: string, handler: Function) => void
    executeCommand: (id: string, ...args: any[]) => Promise<any>
  }
  terminal: {
    createTerminal: (options?: any) => any
    sendText: (text: string) => void
  }
  output: {
    appendLine: (channel: string, text: string) => void
    createChannel: (name: string) => string
  }
  on: (event: string, callback: (...args: any[]) => void) => void
  emit: (event: string, ...args: any[]) => void
}

const builtInPlugins: PluginManifest[] = [
  {
    id: "file-explorer-enhanced",
    name: "文件浏览器增强",
    version: "1.0.0",
    description: "增强的文件浏览器功能",
    author: "CodeBuddy",
    entry: "",
    activationEvents: ["onStartupFinished"],
    contributes: {
      commands: [
        {
          id: "fileExplorer.toggleBookmarks",
          title: "切换书签面板",
          category: "文件浏览器",
          icon: "Bookmark",
        },
        {
          id: "fileExplorer.showRecentFiles",
          title: "显示最近文件",
          category: "文件浏览器",
          icon: "History",
        },
        {
          id: "fileExplorer.refreshExplorer",
          title: "刷新文件浏览器",
          category: "文件浏览器",
          icon: "RefreshCw",
        },
      ],
    },
  },
  {
    id: "git-integration",
    name: "Git 集成",
    version: "1.0.0",
    description: "完整的 Git 集成",
    author: "CodeBuddy",
    entry: "",
    activationEvents: ["workspaceContains:.git"],
    contributes: {
      commands: [
        {
          id: "git.init",
          title: "初始化仓库",
          category: "Git",
          icon: "GitBranchPlus",
        },
        {
          id: "git.status",
          title: "查看状态",
          category: "Git",
          icon: "GitCommit",
        },
        {
          id: "git.commit",
          title: "提交...",
          category: "Git",
          icon: "CheckCircle2",
        },
        {
          id: "git.push",
          title: "推送",
          category: "Git",
          icon: "ArrowUpFromLine",
        },
        {
          id: "git.pull",
          title: "拉取",
          category: "Git",
          icon: "ArrowDownToLine",
        },
        {
          id: "git.branches",
          title: "分支...",
          category: "Git",
          icon: "GitBranch",
        },
        { id: "git.clone", title: "克隆...", category: "Git", icon: "Clone" },
      ],
    },
  },
  {
    id: "ai-assistant",
    name: "AI 助手",
    version: "1.0.0",
    description: "AI 编程助手",
    author: "CodeBuddy",
    entry: "",
    activationEvents: ["*"],
    contributes: {
      commands: [
        {
          id: "ai.openChat",
          title: "打开 AI 对话",
          category: "AI",
          key: "Ctrl+L",
          icon: "MessageSquare",
        },
        {
          id: "ai.explainSelection",
          title: "解释选中的代码",
          category: "AI",
          icon: "Lightbulb",
        },
        {
          id: "ai.generateCode",
          title: "生成代码",
          category: "AI",
          icon: "Sparkles",
        },
        { id: "ai.refactor", title: "重构代码", category: "AI", icon: "Wand2" },
        {
          id: "ai.addTests",
          title: "生成单元测试",
          category: "AI",
          icon: "TestTube2",
        },
      ],
    },
  },
]

class PluginManager {
  private plugins = reactive(new Map<string, LoadedPlugin>())
  private eventListeners = new Map<string, Set<(...args: any[]) => void>>()

  constructor() {
    this.loadBuiltIn()
  }

  private loadBuiltIn() {
    for (const m of builtInPlugins)
      this.plugins.set(m.id, {
        ...m,
        enabled: true,
        active: false,
        status: "loaded",
      })
    // Built-in plugins initialized
  }

  async load(manifest: PluginManifest): Promise<boolean> {
    if (this.plugins.has(manifest.id)) return false
    this.plugins.set(manifest.id, {
      ...manifest,
      enabled: true,
      active: false,
      status: "loaded",
    })
    return true
  }

  async activate(pluginId: string): Promise<boolean> {
    const plugin = this.plugins.get(pluginId)
    if (!plugin?.enabled || plugin.active) return false
    plugin.status = "activated"
    plugin.active = true
    this.emit("plugin:activated", pluginId)
    return true
  }

  deactivate(pluginId: string): boolean {
    const p = this.plugins.get(pluginId)
    if (!p?.active) return false
    p.active = false
    p.status = "loaded"
    this.emit("plugin:deactivated", pluginId)
    return true
  }

  enable(pluginId: string): boolean {
    const p = this.plugins.get(pluginId)
    if (p) {
      p.enabled = true
      p.status = "loaded"
      this.emit("plugin:enabled", pluginId)
    }
    return !!p
  }
  disable(pluginId: string): boolean {
    this.deactivate(pluginId)
    const p = this.plugins.get(pluginId)
    if (p) {
      p.enabled = false
      p.status = "disabled"
      this.emit("plugin:disabled", pluginId)
    }
    return !!p
  }
  uninstall(pluginId: string): boolean {
    this.deactivate(pluginId)
    return this.plugins.delete(pluginId)
  }
  get(id: string): LoadedPlugin | undefined {
    return this.plugins.get(id)
  }
  getAll(): LoadedPlugin[] {
    return Array.from(this.plugins.values())
  }
  getEnabled(): LoadedPlugin[] {
    return this.getAll().filter((p) => p.enabled)
  }
  getActive(): LoadedPlugin[] {
    return this.getAll().filter((p) => p.active)
  }
  getAllCommands(): PluginCommand[] {
    return this.getEnabled().flatMap((p) =>
      (p.contributes?.commands || []).map((c) => ({
        ...c,
        when: `plugin:${p.id}`,
      })),
    )
  }
  getAllViews(): PluginView[] {
    return this.getEnabled().flatMap((p) => p.contributes?.views || [])
  }
  on(event: string, cb: (...a: any[]) => void): () => void {
    if (!this.eventListeners.has(event))
      this.eventListeners.set(event, new Set())
    this.eventListeners.get(event)!.add(cb)
    return () => {
      this.eventListeners.get(event)?.delete(cb)
    }
  }
  emit(event: string, ...args: any[]): void {
    this.eventListeners.get(event)?.forEach((cb) => cb(...args))
  }
}

export const pluginManager = new PluginManager()

export function usePlugins() {
  const installedPlugins = computed(() => pluginManager.getAll())
  const enabledPlugins = computed(() => pluginManager.getEnabled())
  const activePlugins = computed(() => pluginManager.getActive())
  const allCommands = computed(() => pluginManager.getAllCommands())
  const allViews = computed(() => pluginManager.getAllViews())

  async function activateAll(): Promise<void> {
    for (const p of enabledPlugins.value) {
      if (!p.active) await pluginManager.activate(p.id)
    }
  }

  return {
    installedPlugins,
    enabledPlugins,
    activePlugins,
    allCommands,
    allViews,
    activateAll,
    load: (m: PluginManifest) => pluginManager.load(m),
    activate: (id: string) => pluginManager.activate(id),
    deactivate: (id: string) => pluginManager.deactivate(id),
    enable: (id: string) => pluginManager.enable(id),
    disable: (id: string) => pluginManager.disable(id),
    uninstall: (id: string) => pluginManager.uninstall(id),
    get: (id: string) => pluginManager.get(id),
    on: (e: string, cb: (...a: any[]) => void) => pluginManager.on(e, cb),
    emit: (e: string, ...args: any[]) => pluginManager.emit(e, ...args),
  }
}
