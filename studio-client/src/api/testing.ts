import apiClient from "./client"

// ============================================
// 测试管理 API — 发现 / 执行 / 框架列表
// ============================================

export interface TestCase {
  id: string
  name: string
  file_path: string
  line: number
  status: "idle" | "running" | "passed" | "failed" | "skipped"
  duration_ms: number
  error_message: string
  error_stack: string
  suite_name: string
}

export interface TestSuite {
  id: string
  name: string
  file_path: string
  cases: TestCase[]
  status: "idle" | "running" | "passed" | "failed" | "skipped"
}

export interface TestFile {
  path: string
  name: string
  suites: TestSuite[]
}

export interface DiscoverRequest {
  project_path?: string
  framework?: "auto" | "pytest" | "jest" | "vitest" | "gotest" | "cargotest"
  pattern?: string
}

export interface ExecuteRequest {
  project_path?: string
  framework?: "auto" | "pytest" | "jest" | "vitest" | "gotest" | "cargotest"
  test_ids?: string[]
  file_path?: string
  suite_name?: string
}

export interface TestRunResult {
  total: number
  passed: number
  failed: number
  skipped: number
  duration_ms: number
  results: TestCase[]
}

export const testingApi = {
  /** 发现测试文件 — 返回 TestFile[] 树结构 (对标 VSCode Test Explorer) */
  discover: (req: DiscoverRequest) =>
    apiClient.post("/system/testing/discover", req),

  /** 运行测试 — 对标 VSCode Run Test / Debug Test */
  run: (req: ExecuteRequest) =>
    apiClient.post("/system/testing/run", req),

  /** 列出支持的测试框架 */
  listFrameworks: () =>
    apiClient.get("/system/testing/frameworks"),
}
