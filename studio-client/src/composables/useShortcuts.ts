/**
 * Global Shortcut System - Command Palette & Keybinding Registry
 */
import { ref, computed, reactive } from 'vue'

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

const defaultCommands: Omit<ShortcutDefinition, 'handler'>[] = [
  { id: 'file.new', title: '新建文件', category: '文件', key: 'Ctrl+N', icon: 'FilePlus' },
  { id: 'file.open', title: '打开文件...', category: '文件', key: 'Ctrl+O', icon: 'FolderOpen' },
  { id: 'file.save', title: '保存', category: '文件', key: 'Ctrl+S', icon: 'Save' },
  { id: 'file.saveAll', title: '全部保存', category: '文件', key: 'Ctrl+K S' },
  { id: 'file.closeEditor', title: '关闭编辑器', category: '文件', key: 'Ctrl+W' },
  { id: 'edit.undo', title: '撤销', category: '编辑', key: 'Ctrl+Z', icon: 'Undo2' },
  { id: 'edit.redo', title: '重做', category: '编辑', key: 'Ctrl+Y', icon: 'Redo' },
  { id: 'edit.find', title: '查找', category: '编辑', key: 'Ctrl+F', icon: 'Search' },
  { id: 'edit.replace', title: '替换', category: '编辑', key: 'Ctrl+H' },
  { id: 'edit.findInFiles', title: '在文件中查找', category: '编辑', key: 'Ctrl+Shift+F' },
  { id: 'view.commandPalette', title: '命令面板...', category: '视图', key: 'Ctrl+Shift+P' },
  { id: 'view.toggleSidebar', title: '切换侧边栏', category: '视图', key: 'Ctrl+B', icon: 'PanelLeftClose' },
  { id: 'view.togglePanel', title: '切换面板', category: '视图', key: 'Ctrl+J', icon: 'PanelBottomClose' },
  { id: 'nav.quickOpen', title: '快速打开文件...', category: '导航', key: 'Ctrl+P', icon: 'FileSearch' },
  { id: 'terminal.toggle', title: '切换终端', category: '终端', key: 'Ctrl+`', icon: 'Terminal' },
  { id: 'ai.chatPanel', title: 'AI 对话面板', category: 'AI', key: 'Ctrl+L', icon: 'MessageSquare' },
  { id: 'settings.open', title: '设置', category: '偏好设置', key: 'Ctrl+,', icon: 'Settings' },
  { id: 'dev.openDevTools', title: '打开开发工具', category: '开发者', key: 'F12', icon: 'Code' },
]

class ShortcutManager {
  private commands = reactive(new Map<string, ShortcutDefinition>())
  public isCommandPaletteVisible = ref(false)
  public commandPaletteQuery = ref('')
  public activeCategory = ref<string | null>(null)

  constructor() {
    this.registerDefaults()
    this.setupGlobalKeybindings()
  }

  private registerDefaults() {
    for (const cmd of defaultCommands) {
      this.commands.set(cmd.id, { ...cmd, handler: () => {} })
    }
  }

  register(definition: ShortcutDefinition): void {
    this.commands.set(definition.id, definition)
  }

  on(id: string, handler: ShortcutDefinition['handler']): void {
    const existing = this.commands.get(id)
    if (existing) existing.handler = handler
    else this.register({ id, title: id, category: '自定义', handler })
  }

  async execute(id: string): Promise<void> {
    const cmd = this.commands.get(id)
    if (cmd) {
      try { await cmd.handler(); console.log(`[Shortcut] Executed: ${cmd.title}`) }
      catch (e) { console.error(`[Shortcut] Error ${id}:`, e) }
    } else console.warn(`[Shortcut] Unknown: ${id}`)
  }

  getAll(): ShortcutDefinition[] { return Array.from(this.commands.values()) }

  getFiltered(query: string, category?: string | null): CommandPaletteItem[] {
    return this.getAll()
      .filter(item => !category || item.category === category)
      .map(item => ({ ...item, keywords: [item.title, item.category, item.id].join(' ').toLowerCase() }))
      .map(item => ({ ...item, score: this.calculateScore(item.keywords, query.toLowerCase()) }))
      .filter(item => item.score! > 0).sort((a, b) => b.score! - a.score!)
  }

  private calculateScore(keywords: string, query: string): number {
    if (!query) return 1
    if (keywords.includes(query)) return 100
    if (keywords.startsWith(query)) return 80
    let score = 0
    for (const word of query.split(/\s+/)) {
      if (keywords.includes(word)) score += 50
      else if (keywords.split(/\s+/).some(kw => kw.includes(word))) score += 20
    }
    return score
  }

  toggleCommandPalette(show?: boolean) {
    this.isCommandPaletteVisible.value = show ?? !this.isCommandPaletteVisible.value
    if (this.isCommandPaletteVisible.value) { this.commandPaletteQuery.value = ''; this.activeCategory.value = null }
  }

  private setupGlobalKeybindings() {
    if (typeof window === 'undefined') return
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'P') {
        e.preventDefault(); e.stopPropagation(); this.toggleCommandPalette(true); return
      }
      if (e.key === 'Escape' && this.isCommandPaletteVisible.value) {
        e.preventDefault(); this.toggleCommandPalette(false); return
      }
      this.resolveAndExecute(e)
    }, true)
  }

  private resolveAndExecute(e: KeyboardEvent) {
    const key = this.normalizeKeyEvent(e)
    const match = this.getAll().find(cmd => cmd.key === key && this.evaluateWhen(cmd.when))
    if (match) { e.preventDefault(); e.stopPropagation(); this.execute(match.id) }
  }

  private normalizeKeyEvent(e: KeyboardEvent): string {
    const parts: string[] = []
    if (e.ctrlKey) parts.push('Ctrl')
    if (e.metaKey) parts.push('Cmd')
    if (e.altKey) parts.push('Alt')
    if (e.shiftKey && e.key !== 'Shift' && e.key.length === 1) parts.push('Shift')
    let key = e.key
    if (key === ' ') key = 'Space'
    if (key.length === 1) key = key.toUpperCase()
    parts.push(key)
    return parts.join('+')
  }

  private evaluateWhen(when?: string): boolean { return true }

  getCategories(): string[] { return Array.from(new Set(this.getAll().map(c => c.category))).sort() }

  getByKeybinding(key: string): ShortcutDefinition[] { return this.getAll().filter(cmd => cmd.key === key) }
}

export const shortcutManager = new ShortcutManager()

export function useShortcuts() {
  return {
    isCommandPaletteVisible: shortcutManager.isCommandPaletteVisible,
    commandPaletteQuery: shortcutManager.commandPaletteQuery,
    activeCategory: shortcutManager.activeCategory,
    register: (def: ShortcutDefinition) => shortcutManager.register(def),
    on: (id: string, fn: ShortcutDefinition['handler']) => shortcutManager.on(id, fn),
    execute: (id: string) => shortcutManager.execute(id),
    toggleCommandPalette: (show?: boolean) => shortcutManager.toggleCommandPalette(show),
    getAll: () => shortcutManager.getAll(),
    getFiltered: (q: string, c?: string | null) => shortcutManager.getFiltered(q, c),
    getCategories: () => shortcutManager.getCategories(),
    getByKeybinding: (k: string) => shortcutManager.getByKeybinding(k),
  }
}
