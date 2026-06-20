import apiClient from './client'

/* ========== 技能 (Skills) 管理 ========== */

export interface SkillInfo {
  name: string
  description: string
  category: string
  content: string
  author: string
  version: string
  tags: string[]
  path: string
  enabled: boolean
  usage_count: number
}

export interface SkillCreate {
  name: string
  description?: string
  category?: string
  content: string
  author?: string
  version?: string
  tags?: string[]
}

export const skillsApi = {
  /** 从磁盘重新加载技能 */
  load: () =>
    apiClient.post<{ message: string; count: number }>('/skills/load'),

  /** 列出所有技能 (可按分类过滤) */
  list: (category?: string) =>
    apiClient.get<{ skills: SkillInfo[]; count: number }>('/skills', {
      params: { category },
    }),

  /** 获取全部分类及其技能数量 */
  categories: () =>
    apiClient.get<{ categories: { name: string; count: number }[] }>(
      '/skills/categories',
    ),

  /** 创建新技能（用户自建） */
  create: (data: SkillCreate) =>
    apiClient.post<{ skill: SkillInfo; path: string }>('/skills', data),

  /** 获取单个技能详情 */
  get: (name: string) =>
    apiClient.get<{ skill: SkillInfo }>(`/skills/${name}`),

  /** 启用/禁用技能 */
  toggle: (name: string) =>
    apiClient.post<{ name: string; enabled: boolean }>(
      `/skills/${name}/toggle`,
    ),

  /** 更新技能 */
  update: (name: string, data: SkillCreate) =>
    apiClient.put<{ skill: SkillInfo; path: string }>(`/skills/${name}`, data),

  /** 删除技能 */
  delete: (name: string) =>
    apiClient.delete<{ message: string }>(`/skills/${name}`),

  /** 将多个技能组合为 System Prompt，注入当前对话 */
  apply: (skills: string[]) =>
    apiClient.post<{ system_prompt: string; skills_applied: number }>(
      '/skills/apply',
      { skills },
    ),
}
