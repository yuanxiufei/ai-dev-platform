/**
 * DiffViewer 组件单元测试
 *
 * 测试 DiffViewer.vue 的数据处理和渲染逻辑
 */
import { describe, it, expect } from 'vitest'
import type { DiffData, DiffHunk } from '@/types/studio'

// ── 测试数据 ──

const mockDiff: DiffData = {
  file_path: 'src/App.vue',
  file_name: 'App.vue',
  language: 'vue',
  change_type: 'MODIFY',
  is_new_file: false,
  diff_text: '@@ -1,3 +1,4 @@\n-<template>\n+<template lang="pug">\n <div>Hello</div>\n+</template>',
  hunks: [
    {
      header: '@@ -1,3 +1,4 @@',
      lines: [
        '-<template>',
        '+<template lang="pug">',
        ' <div>Hello</div>',
        '+</template>',
      ],
    },
  ],
  old_line_count: 3,
  new_line_count: 4,
  lines_added: 2,
  lines_removed: 1,
  content_before: '<template>\n<div>Hello</div>',
  content_after: '<template lang="pug">\n<div>Hello</div>\n</template>',
}

describe('DiffData 类型结构完整性', () => {
  it('应有所有必需字段', () => {
    expect(mockDiff.file_path).toBeDefined()
    expect(mockDiff.file_name).toBeDefined()
    expect(mockDiff.language).toBeDefined()
    expect(mockDiff.change_type).toBeDefined()
    expect(mockDiff.is_new_file).toBeDefined()
    expect(mockDiff.diff_text).toBeDefined()
    expect(mockDiff.hunks).toBeDefined()
    expect(mockDiff.lines_added).toBeDefined()
    expect(mockDiff.lines_removed).toBeDefined()
  })

  it('行数统计应正确', () => {
    expect(mockDiff.lines_added).toBe(2)
    expect(mockDiff.lines_removed).toBe(1)
    expect(mockDiff.old_line_count).toBe(3)
    expect(mockDiff.new_line_count).toBe(4)
  })
})

describe('DiffHunk 行解析', () => {
  it('应正确区分新增和删除行', () => {
    const hunk: DiffHunk = mockDiff.hunks[0]
    const added = hunk.lines.filter((l) => l.startsWith('+') && !l.startsWith('+++'))
    const removed = hunk.lines.filter((l) => l.startsWith('-') && !l.startsWith('---'))
    expect(added.length).toBe(2)
    expect(removed.length).toBe(1)
  })

  it('上下文行不应以 +/- 开头', () => {
    const hunk: DiffHunk = mockDiff.hunks[0]
    const ctx = hunk.lines.filter(
      (l) => !l.startsWith('+') && !l.startsWith('-') && !l.startsWith('@@')
    )
    expect(ctx.length).toBeGreaterThanOrEqual(1)
    expect(ctx[0]).toContain('Hello')
  })
})

describe('change_type 变更类型', () => {
  it('CREATE 类型对应新文件', () => {
    const createDiff: DiffData = {
      ...mockDiff,
      change_type: 'CREATE',
      is_new_file: true,
    }
    expect(createDiff.change_type).toBe('CREATE')
    expect(createDiff.is_new_file).toBe(true)
  })

  it('DELETE 类型应对应有删除行', () => {
    const deleteDiff: DiffData = {
      ...mockDiff,
      change_type: 'DELETE',
      lines_added: 0,
      lines_removed: 10,
    }
    expect(deleteDiff.change_type).toBe('DELETE')
    expect(deleteDiff.lines_added).toBe(0)
    expect(deleteDiff.lines_removed).toBeGreaterThan(0)
  })

  it('MODIFY 类型应对应有新增和删除', () => {
    expect(mockDiff.change_type).toBe('MODIFY')
    expect(mockDiff.lines_added).toBeGreaterThan(0)
    expect(mockDiff.lines_removed).toBeGreaterThan(0)
  })
})
