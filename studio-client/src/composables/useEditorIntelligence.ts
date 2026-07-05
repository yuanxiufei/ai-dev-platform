/**
 * CodeBuddy IDE — Editor Intelligence (HoverProvider + SignatureHelp)
 *
 * 借鉴: VSCode hoverProvider + signatureHelpProvider
 * Session 38: 智能悬停提示 + 函数签名帮助
 */
import type * as monacoNs from "monaco-editor"
import type { Ref } from "vue"

/** 函数签名信息 */
interface FunctionSignature {
  name: string
  params: { name: string; type: string; optional: boolean }[]
  returnType: string
  doc?: string
}

/** 内建常用函数签名库 */
const BUILTIN_SIGNATURES: Record<string, FunctionSignature[]> = {
  "console.log": [
    { name: "log", params: [{ name: "message", type: "any", optional: false }, { name: "...args", type: "any[]", optional: true }], returnType: "void", doc: "将消息输出到控制台（标准输出）" },
  ],
  "console.error": [
    { name: "error", params: [{ name: "message", type: "any", optional: false }, { name: "...args", type: "any[]", optional: true }], returnType: "void", doc: "将错误消息输出到控制台（标准错误）" },
  ],
  "console.warn": [
    { name: "warn", params: [{ name: "message", type: "any", optional: false }, { name: "...args", type: "any[]", optional: true }], returnType: "void", doc: "将警告消息输出到控制台" },
  ],
  "setTimeout": [
    { name: "setTimeout", params: [{ name: "callback", type: "Function", optional: false }, { name: "delay", type: "number", optional: false }, { name: "...args", type: "any[]", optional: true }], returnType: "number", doc: "延迟指定毫秒后执行回调函数" },
  ],
  "setInterval": [
    { name: "setInterval", params: [{ name: "callback", type: "Function", optional: false }, { name: "delay", type: "number", optional: false }, { name: "...args", type: "any[]", optional: true }], returnType: "number", doc: "每隔指定毫秒重复执行回调函数" },
  ],
  "Array.map": [
    { name: "map", params: [{ name: "callback", type: "(value, index, array) => any", optional: false }, { name: "thisArg", type: "any", optional: true }], returnType: "Array", doc: "创建一个新数组，其中包含对原数组每个元素调用回调函数的结果" },
  ],
  "Array.filter": [
    { name: "filter", params: [{ name: "callback", type: "(value, index, array) => boolean", optional: false }, { name: "thisArg", type: "any", optional: true }], returnType: "Array", doc: "创建一个新数组，包含所有通过回调函数测试的元素" },
  ],
  "Array.reduce": [
    { name: "reduce", params: [{ name: "callback", type: "(accumulator, value, index, array) => any", optional: false }, { name: "initialValue", type: "any", optional: true }], returnType: "any", doc: "对数组中的每个元素执行归约回调函数，将其结果汇总为单个返回值" },
  ],
  "Array.forEach": [
    { name: "forEach", params: [{ name: "callback", type: "(value, index, array) => void", optional: false }, { name: "thisArg", type: "any", optional: true }], returnType: "void", doc: "对数组的每个元素执行一次给定的函数" },
  ],
  "String.includes": [
    { name: "includes", params: [{ name: "searchString", type: "string", optional: false }, { name: "position", type: "number", optional: true }], returnType: "boolean", doc: "判断一个字符串是否包含在另一个字符串中" },
  ],
  "String.replace": [
    { name: "replace", params: [{ name: "searchValue", type: "string | RegExp", optional: false }, { name: "replaceValue", type: "string | Function", optional: false }], returnType: "string", doc: "返回一个由替换值替换部分或全部匹配项后的新字符串" },
  ],
  "String.match": [
    { name: "match", params: [{ name: "regexp", type: "RegExp", optional: false }], returnType: "RegExpMatchArray | null", doc: "检索字符串与正则表达式的匹配结果" },
  ],
  "JSON.stringify": [
    { name: "stringify", params: [{ name: "value", type: "any", optional: false }, { name: "replacer", type: "Function | Array", optional: true }, { name: "space", type: "number | string", optional: true }], returnType: "string", doc: "将 JavaScript 值转换为 JSON 字符串" },
  ],
  "JSON.parse": [
    { name: "parse", params: [{ name: "text", type: "string", optional: false }, { name: "reviver", type: "Function", optional: true }], returnType: "any", doc: "将 JSON 字符串解析为 JavaScript 值" },
  ],
  "Promise.all": [
    { name: "all", params: [{ name: "iterable", type: "Iterable", optional: false }], returnType: "Promise", doc: "等待所有 Promise 完成（或第一个拒绝）" },
  ],
  "Promise.race": [
    { name: "race", params: [{ name: "iterable", type: "Iterable", optional: false }], returnType: "Promise", doc: "返回第一个完成的 Promise 的结果" },
  ],
  "Object.keys": [
    { name: "keys", params: [{ name: "obj", type: "object", optional: false }], returnType: "string[]", doc: "返回给定对象自身可枚举属性的键名数组" },
  ],
  "Object.values": [
    { name: "values", params: [{ name: "obj", type: "object", optional: false }], returnType: "any[]", doc: "返回给定对象自身可枚举属性的键值数组" },
  ],
  "Object.entries": [
    { name: "entries", params: [{ name: "obj", type: "object", optional: false }], returnType: "[string, any][]", doc: "返回给定对象自身可枚举属性的键值对数组" },
  ],
  "document.querySelector": [
    { name: "querySelector", params: [{ name: "selectors", type: "string", optional: false }], returnType: "Element | null", doc: "返回文档中与指定 CSS 选择器匹配的第一个元素" },
  ],
  "document.querySelectorAll": [
    { name: "querySelectorAll", params: [{ name: "selectors", type: "string", optional: false }], returnType: "NodeList", doc: "返回文档中与指定 CSS 选择器匹配的所有元素的静态 NodeList" },
  ],
}

/** CSS 内建属性文档 */
const CSS_PROPERTY_DOCS: Record<string, string> = {
  display: "控制元素的显示类型。常用值: `none`, `block`, `inline`, `flex`, `grid`, `inline-flex`",
  position: "控制元素的定位方式。`static` | `relative` | `absolute` | `fixed` | `sticky`",
  "z-index": "控制定位元素的堆叠顺序。数值越大越靠前。",
  flex: "`flex: <grow> <shrink> <basis>` — flex 项目的缩写属性",
  "flex-direction": "定义主轴方向。`row` | `row-reverse` | `column` | `column-reverse`",
  "justify-content": "沿主轴对齐 flex 项目。`flex-start` | `flex-end` | `center` | `space-between` | `space-around` | `space-evenly`",
  "align-items": "沿交叉轴对齐 flex 项目。`stretch` | `flex-start` | `flex-end` | `center` | `baseline`",
  gap: "flex/grid 容器中项目间的间距。",
  padding: "内边距。`padding: <top> <right> <bottom> <left>`",
  margin: "外边距。`margin: <top> <right> <bottom> <left>`",
  width: "元素宽度。可用 `px`, `%`, `vw`, `rem`, `em` 等单位。",
  height: "元素高度。可用 `px`, `%`, `vh`, `rem`, `em` 等单位。",
  "max-width": "元素最大宽度。",
  "min-height": "元素最小高度，对 flex/grid 布局有特殊意义。",
  overflow: "内容溢出时的处理方式。`visible` | `hidden` | `scroll` | `auto`",
  "border-radius": "圆角半径。`<top-left> <top-right> <bottom-right> <bottom-left>`",
  opacity: "元素透明度。`0` (完全透明) ~ `1` (完全不透明)",
  transition: "`transition: <property> <duration> <timing-function> <delay>` — 过渡动画",
  transform: "应用于元素的 2D/3D 变换。如 `translate()`, `scale()`, `rotate()`, `skew()`",
  "box-shadow": "`<h-offset> <v-offset> <blur> <spread> <color>` — 阴影效果",
  "pointer-events": "控制元素是否为鼠标事件的目标。`auto` | `none`",
  "user-select": "控制用户能否选中文本。`none` | `auto` | `text` | `all`",
  cursor: "鼠标指针样式。`pointer` | `default` | `text` | `not-allowed` | `grab`",
  "background-color": "元素背景色。",
  color: "文本颜色。",
  "font-size": "字体大小。",
  "font-weight": "字体粗细。`normal(400)` | `bold(700)` | `100-900`",
  "line-height": "行高。`normal` ~ `1.5`",
  "text-align": "文本对齐。`left` | `center` | `right` | `justify`",
}

/**
 * 注册智能编辑器功能（HoverProvider + SignatureHelpProvider）
 * 返回清理函数 dispose
 */
export function useEditorIntelligence(
  monacoRef: Ref<typeof monacoNs | null>,
): { dispose: () => void } {
  const disposables: monacoNs.IDisposable[] = []

  function init(m: typeof monacoNs): void {
    if (!m) return

    // ── HoverProvider: CSS 属性文档 ──
    const cssHoverDisposable = m.languages.registerHoverProvider("css", {
      provideHover(model, position) {
        const word = model.getWordAtPosition(position)
        if (!word) return null

        const doc = CSS_PROPERTY_DOCS[word.word]
        if (!doc) return null

        return {
          range: new m.Range(
            position.lineNumber,
            word.startColumn,
            position.lineNumber,
            word.endColumn,
          ),
          contents: [
            { value: `**${word.word}**` },
            { value: doc },
          ],
        }
      },
    })
    disposables.push(cssHoverDisposable)

    // ── HoverProvider: SCSS/Less 同 CSS ──
    for (const lang of ["scss", "less"]) {
      const h = m.languages.registerHoverProvider(lang, {
        provideHover(model, position) {
          const word = model.getWordAtPosition(position)
          if (!word) return null

          const doc = CSS_PROPERTY_DOCS[word.word]
          if (!doc) return null

          return {
            range: new m.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn,
            ),
            contents: [
              { value: `**${word.word}**` },
              { value: doc },
            ],
          }
        },
      })
      disposables.push(h)
    }

    // ── SignatureHelpProvider: JavaScript/TypeScript 内建函数 ──
    for (const lang of ["javascript", "typescript", "javascriptreact", "typescriptreact"]) {
      const sigHelpDisposable = m.languages.registerSignatureHelpProvider(lang, {
        signatureHelpTriggerCharacters: ["(", ","],
        signatureHelpRetriggerCharacters: [","],
        provideSignatureHelp(model, position) {
          // 获取当前行光标前的内容
          const lineContent = model.getLineContent(position.lineNumber)
          const textBeforeCursor = lineContent.substring(0, position.column - 1)

          // 找到调用的函数名
          // 模式: obj.method( 或 function(
          const callMatch = textBeforeCursor.match(/([\w.]+)\s*\($/)
          if (!callMatch) return null

          const fullName = callMatch[1]
          const signatures = BUILTIN_SIGNATURES[fullName]
          if (!signatures) return null

          return {
            dispose: () => {},
            value: {
              signatures: signatures.map(s => ({
                label: `${s.name}(${s.params.map(p => `${p.name}${p.optional ? "?" : ""}: ${p.type}`).join(", ")})`,
                documentation: s.doc ?? "",
                parameters: s.params.map(p => ({
                  label: `${p.name}${p.optional ? "?" : ""}: ${p.type}`,
                  documentation: "",
                })),
              })),
              activeSignature: 0,
              activeParameter: 0,
            },
          }
        },
      })
      disposables.push(sigHelpDisposable)

      // ── HoverProvider: JS/TS 内建函数文档 ──
      const jsHoverDisposable = m.languages.registerHoverProvider(lang, {
        provideHover(model, position) {
          const word = model.getWordAtPosition(position)
          if (!word) return null

          // 查找内建函数签名
          const signatures = BUILTIN_SIGNATURES[word.word]
          if (!signatures) return null

          const markdownParts: { value: string }[] = []
          for (const s of signatures) {
            markdownParts.push({
              value: [
                `**${s.name}**(${s.params.map(p => `\`${p.name}${p.optional ? "?" : ""}: ${p.type}\``).join(", ")})`,
                `→ \`${s.returnType}\``,
                s.doc ? `\n\n${s.doc}` : "",
                "",
              ].join("  \n"),
            })
          }

          return {
            range: new m.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn,
            ),
            contents: markdownParts,
          }
        },
      })
      disposables.push(jsHoverDisposable)
    }

    // ── HoverProvider: HTML/Vue 属性文档 ──
    const htmlAttrDocs: Record<string, string> = {
      class: "CSS 类名，用于样式和 JS 选择器。",
      id: "元素的唯一标识符。在同文档中必须唯一。",
      style: "内联 CSS 样式。",
      "v-if": "**Vue**: 条件渲染。为 `false` 时不渲染元素。",
      "v-show": "**Vue**: 条件显示。通过 `display` CSS 属性切换可见性。",
      "v-for": "**Vue**: 列表渲染。`v-for=\"item in items\" :key=\"item.id\"`",
      "v-model": "**Vue**: 双向数据绑定。",
      "v-bind": "**Vue**: 动态绑定属性。简写 `:attr=\"value\"`",
      "v-on": "**Vue**: 事件监听。简写 `@event=\"handler\"`",
      ":key": "**Vue**: 列表渲染的唯一键值，帮助 Vue 追踪元素身份。",
      ref: "**Vue**: 模板引用，用于访问 DOM 元素或子组件实例。",
      slot: "**Vue**: 插槽，用于内容分发。",
    }

    for (const lang of ["html", "vue"]) {
      const h = m.languages.registerHoverProvider(lang, {
        provideHover(model, position) {
          const word = model.getWordAtPosition(position)
          if (!word) return null

          // HTML 属性（如 class, id, v-if）
          const attrName = word.word.replace(/^[:@v]-?/, "") // strip Vue prefixes
          const doc = htmlAttrDocs[word.word] || htmlAttrDocs[attrName]
          if (!doc) return null

          return {
            range: new m.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn,
            ),
            contents: [
              { value: `**${word.word}**` },
              { value: doc },
            ],
          }
        },
      })
      disposables.push(h)
    }
  }

  return {
    dispose: () => {
      for (const d of disposables) d.dispose()
    },
    init,
  }
}
