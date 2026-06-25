// ============================================
// Shared utilities for IDE stores
// ============================================

/** Detect Tauri runtime vs web-only mode */
let _isTauri: boolean | null = null
export function isTauriEnv(): boolean {
  if (_isTauri !== null) return _isTauri
  try {
    _isTauri = !!(window as any).__TAURI_INTERNALS__ || !!(window as any).__TAURI__
    return !!_isTauri
  } catch {
    _isTauri = false
    return false
  }
}

let idCounter = 0
export function uid(): string {
  return `id_${Date.now()}_${++idCounter}`
}

export const extToLang: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescriptreact',
  js: 'javascript',
  jsx: 'javascriptreact',
  vue: 'html',
  py: 'python',
  rs: 'rust',
  go: 'go',
  java: 'java',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  md: 'markdown',
  css: 'css',
  scss: 'scss',
  less: 'less',
  html: 'html',
  xml: 'xml',
  sh: 'shell',
  bat: 'batch',
  ps1: 'powershell',
  sql: 'sql',
  dockerfile: 'dockerfile',
  env: 'plaintext',
  txt: 'plaintext',
  log: 'plaintext',
  gitignore: 'plaintext',
  lock: 'toml',
  mod: 'go',
  c: 'cpp',
  cpp: 'cpp',
  h: 'cpp',
}

export function getLanguageFromPath(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  if (filePath.toLowerCase().includes('dockerfile')) return 'dockerfile'
  const fileName = filePath.split(/[/\\]/).pop() ?? ''
  if (fileName.startsWith('.')) return 'plaintext'
  return extToLang[ext] ?? 'plaintext'
}

export function generateDemoContent(fileName: string, lang: string): string {
  const contents: Record<string, string> = {
    typescript: `import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

const app = createApp(App)
app.mount('#app')
`,
    python: `"""AI Fullstack Platform — FastAPI Main Entry"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Fullstack Platform API", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/v1/system/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
`,
    json: `{
  "name": "ai-fullstack-platform",
  "private": true,
  "version": "0.1.0",
  "type": "module"
}`,
    markdown: `# CodeBuddy IDE

> AI Fullstack Platform — Studio + IDE

## Getting Started

\`\`\`bash
pnpm install
pnpm dev
\`\`\`
`,
    html: `<template>
  <div class="app">
    <h1>{{ title }}</h1>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
const title = ref('CodeBuddy IDE')
</script>
`,
    yaml: `services:
  app:
    build: .
    ports: ["8000:8000"]
`,
    toml: `[project]
name = "studio-backend"
version = "0.1.0"
requires-python = ">=3.12"
`,
  }
  if (contents[lang]) return contents[lang]
  if (['typescript', 'typescriptreact', 'javascript', 'javascriptreact'].includes(lang))
    return contents.typescript
  if (['python', 'shell'].includes(lang)) return contents.python
  if (lang === 'json') return contents.json
  if (lang === 'markdown') return contents.markdown
  if (lang === 'html') return contents.html
  if (lang === 'yaml') return contents.yaml
  if (lang === 'toml') return contents.toml
  return `// ${fileName}\n// CodeBuddy IDE\n`
}
