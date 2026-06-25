import type { Project } from "@/types/studio"
import apiClient from "./client"

export interface PaginatedResponse<T> {
  data: T[]
  count: number
}

const wrap = async <T>(promise: Promise<{ data: T }>): Promise<{ data: T }> => {
  return promise
}

export const listProjects = () =>
  wrap<PaginatedResponse<Project>>(apiClient.get("/projects/"))

export const getProject = (id: string) =>
  wrap<Project>(apiClient.get(`/projects/${id}`))

export const deleteProject = (id: string) => apiClient.delete(`/projects/${id}`)
