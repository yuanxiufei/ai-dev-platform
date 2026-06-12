import apiClient from './client'
import type { ApiResponse, Project, Template } from '@/types/studio'

/* ========== 项目管理 ========== */

export const listProjects = () =>
  apiClient.get<ApiResponse<Project[]>>('/studio/projects/')

export const getProject = (id: string) =>
  apiClient.get<ApiResponse<Project>>(`/studio/projects/${id}`)

export const createProject = (data: Partial<Project>) =>
  apiClient.post<ApiResponse<Project>>('/studio/projects/', data)

export const updateProject = (id: string, data: Partial<Project>) =>
  apiClient.put<ApiResponse<Project>>(`/studio/projects/${id}`, data)

export const deleteProject = (id: string) =>
  apiClient.delete<ApiResponse>(`/studio/projects/${id}`)

export const buildProject = (id: string) =>
  apiClient.post<ApiResponse>(`/studio/projects/${id}/build`)

export const deployProject = (id: string) =>
  apiClient.post<ApiResponse>(`/studio/projects/${id}/deploy`)

/* ========== 模板管理 ========== */

export const listTemplates = () =>
  apiClient.get<ApiResponse<Template[]>>('/studio/templates/')

export const getTemplate = (id: string) =>
  apiClient.get<ApiResponse<Template>>(`/studio/templates/${id}`)

export const useTemplate = (id: string) =>
  apiClient.post<ApiResponse>(`/studio/templates/${id}/use`)
