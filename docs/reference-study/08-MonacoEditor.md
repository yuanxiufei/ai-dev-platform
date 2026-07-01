# Monaco Editor — 编辑器核心引擎

> **源码位置**: `D:\code\monaco-editor` | **大小**: 21 MB | **语言**: TypeScript  
> **官网**: https://microsoft.github.io/monaco-editor/ | **出品**: Microsoft  
> **定位**: VS Code 内嵌的代码编辑器核心，可独立使用

---

## 一、项目概览

Monaco Editor 是 **VS Code 的编辑器引擎**，作为独立包发布。它是目前功能最完整的 Web 端代码编辑器：

✅ **语法高亮** — 200+ 语言内置支持
✅ **智能提示** — IntelliSense 自动补全
✅ **Diff Editor** — 内置并排对比 Diff
✅ **多光标** — 同时在多处编辑
✅ **Minimap** — 代码缩略图
✅ **快捷键** — Vim/Emacs 键位映射
✅ **主题** — 50+ 内置主题
✅ **LSP 集成** — Language Server Protocol 支持

### 与我们项目的关系
studio-client 如果需要内嵌代码编辑器，Monaco 是不二之选。

---

## 二、关键 API 速查

### 2.1 创建编辑器

```typescript
import * as monaco from 'monaco-editor';

// 创建普通编辑器
const editor = monaco.editor.create(containerEl, {
    value: 'function hello() {\n\tconsole.log("Hello!");\n}',
    language: 'javascript',
    theme: 'vs-dark',        // 'vs' | 'vs-dark' | 'hc-black'
    
    // 基础配置
    fontSize: 14,
    lineNumbers: 'on',
    minimap: { enabled: true },
    wordWrap: 'off',
    automaticLayout: true,
    scrollBeyondLastLine: false,
    
    // 高级配置
    suggestOnTriggerCharacters: true,
    quickSuggestions: { other: true, comments: true, strings: true },
    tabSize: 2,
    insertSpaces: true,
    renderWhitespace: 'selection',
    bracketPairColorization: { enabled: true },
});

// 获取实例引用
const model = editor.getModel();  // ITextModel
```

### 2.2 Diff Editor（最关键！）

```typescript
// 创建 Diff 编辑器（用于 AI 代码变更展示）
const diffEditor = monaco.editor.createDiffEditor(containerEl, {
    originalEditable: false,
    renderSideBySide: true,       // 并排模式（true）或 行内模式（false）
    enableSplitViewResizing: true, // 允许拖动调整左右比例
    ignoreTrimWhitespace: false,   // 忽略尾部空白差异
    renderOverviewRuler: true,     // 右侧差异标记条
    diffAlgorithm: 'advanced',     // 'legacy' | 'advanced'
    
    // 自定义样式
    diffDecorations: {
        addedClassName: 'diff-added',       // 新增行 CSS class
        modifiedClassName: 'diff-modified',  // 修改行
        removedClassName: 'diff-removed',    // 删除行
    },
});

// 设置 Diff 内容
diffEditor.setModel({
    original: monaco.editor.createModel(originalCode, language),
    modified: monaco.editor.createModel(modifiedCode, language),
});

// 行内 Diff 模式（更紧凑）
const inlineDiff = monaco.editor.createDiffEditor(el, {
    renderSideBySide: false,  // ← 关键：false = 行内模式
});
```

### 2.3 Decorations（高亮/AI 标注）

```typescript
// 添加装饰（高亮行、添加背景色、显示文字等）
const decorations = editor.deltaDecorations([], [
    // 整行背景色
    {
        range: new monaco.Range(10, 1, 10, 1),  // 第 10 行
        options: {
            isWholeLine: true,
            className: 'highlight-line',
            glyphMarginClassName: 'line-number-glyph',
            glyphMarginHoverMessage: { value: 'AI suggested change' },
        },
    },
    // 行内文字样式
    {
        range: new monaco.Range(5, 10, 5, 20),
        options: {
            inlineClassName: 'ai-inserted-text',
            hoverMessage: { value: 'Inserted by AI' },
            after: { content: ' 🤖', cursorStops: false },
        },
    },
]);

// 清除所有 decorations
editor.deltaDecorations(decorations, []);
```

### 2.4 自定义语法高亮主题

```typescript
// 定义自定义主题（用于匹配我们的品牌色）
monaco.editor.defineTheme('my-ai-theme', {
    base: 'vs-dark',           // 基于 dark 主题
    inherit: true,             // 继承默认规则
    rules: [
        { token: 'comment', foreground: '6A9955', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'C586C0' },
        { token: 'string', foreground: 'CE9178' },
        
        // AI 相关的自定义 token
        { token: 'ai-inserted', background: '2ea04333', foreground: '3fb950' },    // 绿色新增
        { token: 'ai-deleted', background: 'f8514933', foreground: 'f85149' },     // 红色删除
        { token: 'ai-modified', background: 'd2992233', foreground: 'e3b341' },   // 黄色修改
    ],
    colors: {
        'editor.background': '#1e1e1e',
        'editor.foreground': '#d4d4d4',
        'editor.lineHighlightBackground': '#2a2d2e',
        'editor.selectionBackground': '#264f78',
        'editor.inactiveSelectionBackground': '#3a3d41',
    },
});
monaco.editor.setTheme('my-ai-theme');
```

### 2.5 事件监听

```typescript
// 光标位置变化
editor.onDidChangeCursorPosition((e) => {
    console.log(`Cursor at line ${e.position.lineNumber}, col ${e.position.column}`);
});

// 内容变化
editor.onDidChangeModelContent((e) => {
    const changes = e.changes;
    for (const change of changes) {
        console.log(`Changed range: ${change.range}, text: "${change.text}"`);
    }
});

// 选区变化
editor.onDidChangeCursorSelection((e) => {
    const selection = e.selection;
    console.log(`Selected: ${selection.startLineNumber}:${selection.startColumn} - ${selection.endLineNumber}:${selection.endColumn}`);
});

// 失去焦点（用于自动保存）
editor.onDidBlurEditorText(() => {
    saveCurrentFile();
});
```

### 2.6 WebView 版本

```html
<!-- Monaco 也提供纯 HTML 版本（无需 npm 安装） -->
<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.50.0/min/vs/loader.js"></script>
<script>
require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.50.0/min/vs' }});
require(['vs/editor/editor.main'], function () {
    monaco.editor.create(document.getElementById('container'), {
        value: '// Hello world',
        language: 'javascript',
        theme: 'vs-dark',
    });
});
</script>
```

---

## 三、与 DiffViewer.vue 的对照

| 功能 | Monaco 原生能力 | 我们 DiffViewer.vue |
|------|----------------|---------------------|
| 并排 Diff | ✅ `createDiffEditor` | ✅ 使用 Monaco |
| 行内 Diff | ✅ `renderSideBySide: false` | ❌ 待增加 |
| 逐 hunk Accept | ❌ 需自行实现 | ✅ 已有基础 |
| 语法高亮 | ✅ 内置 200+ 语言 | ✅ 继承 |
| AI 标注装饰 | ✅ `deltaDecorations` | ❌ 待增强 |
| Minimap | ✅ 内置 | ✅ 已启用 |

---

## 四、快速入门

```bash
cd D:\code\monaco-editor
npm install
# 查看示例
npm run website  # 启动 playground
```
