/**
 * LSP 客户端 — 连接后端 /api/v1/system/lsp/ 全 24 个 Provider
 *
 * 对标 VSCode ILanguageFeaturesService，覆盖:
 *   completion/hover/definition/references/symbols/signatureHelp
 *   rename/codeAction/formatting/semanticTokens/typeDefinition
 *   declaration/implementation/inlayHint/codeLens/folding
 *   documentHighlight/link/inlineCompletion/onTypeFormatting
 *
 * Session 53: 新增 14 个 Provider 连接
 */
import apiClient from "./client"

const LSP_BASE = "/system/lsp"

/* ========== 类型定义 ========== */

export interface LspRange {
  start_line: number
  start_column: number
  end_line: number
  end_column: number
}

export interface LspLocation {
  uri: string
  name: string
  start_line: number
  start_column: number
  end_line: number
  end_column: number
}

export interface CompletionItem {
  label: string
  kind: string
  detail: string
  insert_text: string
  documentation: string
  sort_text: string
}

export interface HoverResult {
  contents: string
  range_start_line: number
  range_start_col: number
  range_end_line: number
  range_end_col: number
}

export interface SymbolInfo {
  name: string
  kind: string
  detail: string
  start_line: number
  start_column: number
  end_line: number
  end_column: number
  children: SymbolInfo[]
}

export interface SignatureInfo {
  label: string
  parameters: { label: string }[]
}

export interface SignatureHelpResult {
  signatures: SignatureInfo[]
  active_signature: number
  active_parameter: number
}

export interface TextEdit {
  range: LspRange
  new_text: string
}

export interface PrepareRenameResult {
  range: LspRange
  text: string
  can_rename: boolean
}

export interface RenameResult {
  edits: TextEdit[]
  reject_reason: string | null
}

export interface Diagnostic {
  message: string
  start_line: number
  start_column: number
  end_line: number
  end_column: number
  severity: number
  code: string
  source: string
}

export interface CodeAction {
  title: string
  kind: string
  edits: TextEdit[]
  is_preferred: boolean
}

export interface FormattingResult {
  formatted_content: string
  edits: TextEdit[]
}

export interface SemanticTokenData {
  data: number[]
  result_id: string
}

export interface SemanticTokensLegend {
  token_types: string[]
  token_modifiers: string[]
}

export interface SemanticTokensResult {
  legend: SemanticTokensLegend
  tokens: SemanticTokenData
  range_tokens: SemanticTokenData | null
}

export interface InlayHintItem {
  position_line: number
  position_column: number
  label: string
  kind: string
  padding_left: boolean
  padding_right: boolean
}

export interface CodeLensItem {
  range: LspRange
  title: string
  command_id: string
  command_title: string
}

export interface DocumentHighlight {
  range: LspRange
  kind: string
}

export interface DocumentLink {
  range: LspRange
  url: string
  tooltip: string
}

export interface InlineCompletionItem {
  insert_text: string
  range: LspRange | null
  command_title: string
}

export interface FoldingRange {
  start_line: number
  end_line: number
  kind: string
}

/* ========== 请求体 ========== */

export interface LspRequestPayload {
  content: string
  language?: string
  file_path?: string
  position_line?: number
  position_column?: number
  project_path?: string
  max_results?: number
}

export interface SignatureHelpPayload {
  content: string
  language?: string
  position_line?: number
  position_column?: number
}

export interface RenamePayload {
  content: string
  language?: string
  file_path?: string
  position_line: number
  position_column: number
  new_name?: string
}

export interface CodeActionPayload {
  content: string
  language?: string
  file_path?: string
  range?: LspRange
  diagnostics?: Diagnostic[]
  only_kinds?: string[]
}

export interface FormattingPayload {
  content: string
  language?: string
  file_path?: string
  tab_size?: number
  insert_spaces?: boolean
  range?: LspRange | null
}

export interface SemanticTokensPayload {
  content: string
  language?: string
  file_path?: string
  last_result_id?: string | null
  range?: LspRange | null
}

export interface InlayHintPayload {
  content: string
  language?: string
  file_path?: string
  range?: LspRange
}

export interface CodeLensPayload {
  content: string
  language?: string
  file_path?: string
  range?: LspRange | null
}

export interface InlineCompletionPayload {
  content: string
  language?: string
  file_path?: string
  position_line: number
  position_column: number
  trigger_kind?: string
}

export interface OnTypeFormattingPayload {
  content: string
  language?: string
  file_path?: string
  position_line: number
  position_column: number
  typed_char: string
  options?: Record<string, unknown>
}

export interface LspCapabilities {
  providers: string[]
  providers_count: number
  supported_languages: string[]
  engine: string
  session: string
}

/* ========== API 方法 ========== */

/** 代码补全 */
export async function getCompletions(payload: LspRequestPayload): Promise<CompletionItem[]> {
  const r = await apiClient.post(`${LSP_BASE}/completions`, payload)
  return r.data
}

/** 悬停提示 */
export async function getHover(payload: LspRequestPayload): Promise<HoverResult> {
  const r = await apiClient.post(`${LSP_BASE}/hover`, payload)
  return r.data
}

/** 跳转到定义 */
export async function getDefinitions(payload: LspRequestPayload): Promise<LspLocation[]> {
  const r = await apiClient.post(`${LSP_BASE}/definitions`, payload)
  return r.data
}

/** 查找引用 */
export async function getReferences(payload: LspRequestPayload): Promise<LspLocation[]> {
  const r = await apiClient.post(`${LSP_BASE}/references`, payload)
  return r.data
}

/** 文档符号 */
export async function getSymbols(payload: LspRequestPayload): Promise<SymbolInfo[]> {
  const r = await apiClient.post(`${LSP_BASE}/symbols`, payload)
  return r.data
}

/** 函数签名帮助 */
export async function getSignatureHelp(payload: SignatureHelpPayload): Promise<SignatureHelpResult> {
  const r = await apiClient.post(`${LSP_BASE}/signature-help`, payload)
  return r.data
}

/** 准备重命名 */
export async function prepareRename(payload: RenamePayload): Promise<PrepareRenameResult> {
  const r = await apiClient.post(`${LSP_BASE}/prepare-rename`, payload)
  return r.data
}

/** 执行重命名 */
export async function rename(payload: RenamePayload): Promise<RenameResult> {
  const r = await apiClient.post(`${LSP_BASE}/rename`, payload)
  return r.data
}

/** 代码操作/快速修复 */
export async function getCodeActions(payload: CodeActionPayload): Promise<CodeAction[]> {
  const r = await apiClient.post(`${LSP_BASE}/code-actions`, payload)
  return r.data
}

/** 格式化文档 */
export async function formatDocument(payload: FormattingPayload): Promise<FormattingResult> {
  const r = await apiClient.post(`${LSP_BASE}/formatting`, payload)
  return r.data
}

/** 格式化选区 */
export async function formatRange(payload: FormattingPayload): Promise<FormattingResult> {
  const r = await apiClient.post(`${LSP_BASE}/range-formatting`, payload)
  return r.data
}

/** 语义高亮 Token */
export async function getSemanticTokens(payload: SemanticTokensPayload): Promise<SemanticTokensResult> {
  const r = await apiClient.post(`${LSP_BASE}/semantic-tokens`, payload)
  return r.data
}

/** 范围语义高亮 */
export async function getSemanticTokensRange(payload: SemanticTokensPayload): Promise<SemanticTokensResult> {
  const r = await apiClient.post(`${LSP_BASE}/semantic-tokens/range`, payload)
  return r.data
}

/** 语义 Token 映射表 */
export async function getSemanticTokensLegend(): Promise<SemanticTokensLegend> {
  const r = await apiClient.get(`${LSP_BASE}/semantic-tokens/legend`)
  return r.data
}

/** 跳转到类型定义 */
export async function getTypeDefinition(payload: LspRequestPayload): Promise<LspLocation[]> {
  const r = await apiClient.post(`${LSP_BASE}/type-definition`, payload)
  return r.data
}

/** 跳转到声明 */
export async function getDeclaration(payload: LspRequestPayload): Promise<LspLocation[]> {
  const r = await apiClient.post(`${LSP_BASE}/declaration`, payload)
  return r.data
}

/** 跳转到实现 */
export async function getImplementation(payload: LspRequestPayload): Promise<LspLocation[]> {
  const r = await apiClient.post(`${LSP_BASE}/implementation`, payload)
  return r.data
}

/** 内联类型提示 */
export async function getInlayHints(payload: InlayHintPayload): Promise<InlayHintItem[]> {
  const r = await apiClient.post(`${LSP_BASE}/inlay-hints`, payload)
  return r.data
}

/** 代码透镜 */
export async function getCodeLens(payload: CodeLensPayload): Promise<CodeLensItem[]> {
  const r = await apiClient.post(`${LSP_BASE}/code-lens`, payload)
  return r.data
}

/** 代码折叠范围 */
export async function getFoldingRanges(payload: LspRequestPayload): Promise<{ ranges: FoldingRange[] }> {
  const r = await apiClient.post(`${LSP_BASE}/folding-ranges`, payload)
  return r.data
}

/** 文档高亮 */
export async function getDocumentHighlights(payload: LspRequestPayload): Promise<DocumentHighlight[]> {
  const r = await apiClient.post(`${LSP_BASE}/document-highlights`, payload)
  return r.data
}

/** 文档链接 */
export async function getDocumentLinks(payload: LspRequestPayload): Promise<DocumentLink[]> {
  const r = await apiClient.post(`${LSP_BASE}/links`, payload)
  return r.data
}

/** 内联补全 */
export async function getInlineCompletions(payload: InlineCompletionPayload): Promise<InlineCompletionItem[]> {
  const r = await apiClient.post(`${LSP_BASE}/inline-completions`, payload)
  return r.data
}

/** 输入时格式化 */
export async function getOnTypeFormatting(payload: OnTypeFormattingPayload): Promise<TextEdit[]> {
  const r = await apiClient.post(`${LSP_BASE}/on-type-formatting`, payload)
  return r.data
}

/** LSP 能力列表 */
export async function getLspCapabilities(): Promise<LspCapabilities> {
  const r = await apiClient.get(`${LSP_BASE}/capabilities`)
  return r.data
}
