import apiClient from "./client"

/* ========== CKG 代码知识图谱 API ========== */

export interface CkgSymbol {
  name: string
  kind: string
  file_path: string
  line_number: number
  qualified_name: string
  signature: string
  language: string
}

export interface CkgStats {
  total_nodes: number
  total_edges: number
  projects_count: number
  projects: string[]
}

export const indexProject = (projectPath: string, force = false) =>
  apiClient.post<{ status: string; project: string; added: number; skipped: number }>(
    "/agent/ckg/index",
    null,
    { params: { project_path: projectPath, force } }
  )

export const searchSymbols = (params: {
  query: string
  kind?: string
  file_pattern?: string
  project_path?: string
  limit?: number
}) => apiClient.get<{ status: string; symbols: CkgSymbol[]; total_found: number }>(
  "/agent/ckg/search",
  { params }
)

export const getCkgStats = (projectPath?: string) =>
  apiClient.get<{ status: string; total_nodes?: number; projects_count?: number; projects?: string[] }>(
    "/agent/ckg/stats",
    { params: projectPath ? { project_path: projectPath } : {} }
  )

export const clearProject = (projectName: string) =>
  apiClient.delete<{ status: string; deleted: number; project: string }>(
    `/agent/ckg/${encodeURIComponent(projectName)}`
  )

export const clearAllProjects = () =>
  apiClient.delete<{ status: string; deleted: number }>("/agent/ckg/")

export const ckgApi = {
  indexProject,
  searchSymbols,
  getCkgStats,
  clearProject,
  clearAllProjects,
}
