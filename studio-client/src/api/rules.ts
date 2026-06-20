/**
 * Rules API — AI 行为规则管理
 */
import { apiClient } from './client'

export interface RuleItem {
  id: string
  name: string
  description: string
  rule_type: 'always' | 'requested' | 'manual'
  scope: 'project' | 'user'
  content: string
  enabled: boolean
  triggers: string[] | null
  priority: number
  created_at: string | null
  updated_at: string | null
}

export interface RuleListParams {
  page?: number
  size?: number
  scope?: string
  type?: string
  search?: string
}

export interface RuleCreatePayload {
  name: string
  description?: string
  rule_type?: string
  scope?: string
  content: string
  triggers?: string[]
  priority?: number
}

export interface RuleUpdatePayload {
  name?: string
  description?: string
  rule_type?: string
  scope?: string
  content?: string
  triggers?: string[]
  priority?: number
}

// ── API Functions ────────────────────────────────────────

export async function listRules(params?: RuleListParams) {
  return apiClient.get('/rules', { params })
}

export async function getRule(id: string) {
  return apiClient.get(`/rules/${id}`)
}

export async function createRule(payload: RuleCreatePayload) {
  return apiClient.post('/rules', payload)
}

export async function updateRule(id: string, payload: RuleUpdatePayload) {
  return apiClient.put(`/rules/${id}`, payload)
}

export async function deleteRule(id: string) {
  return apiClient.delete(`/rules/${id}`)
}

export async function toggleRule(id: string) {
  return apiClient.post(`/rules/${id}/toggle`)
}

export async function getRulesStats() {
  return apiClient.get('/rules/stats')
}
