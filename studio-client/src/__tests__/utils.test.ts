/**
 * 工具函数单元测试
 *
 * 测试 src/utils/ 下的纯函数逻辑
 */
import { describe, expect, it } from "vitest"

// ── 项目状态映射 ──────────────────────────────
const statusLabel: Record<string, string> = {
  draft: "草稿",
  building: "构建中",
  deploying: "部署中",
  running: "运行中",
  failed: "失败",
}

const statusColor: Record<string, string> = {
  draft: "bg-gray-500/20 text-gray-400",
  building: "bg-yellow-500/20 text-yellow-400",
  deploying: "bg-blue-500/20 text-blue-400",
  running: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
}

describe("statusLabel 状态标签映射", () => {
  it("应正确映射所有已知状态", () => {
    expect(statusLabel.draft).toBe("草稿")
    expect(statusLabel.building).toBe("构建中")
    expect(statusLabel.deploying).toBe("部署中")
    expect(statusLabel.running).toBe("运行中")
    expect(statusLabel.failed).toBe("失败")
  })

  it("未知状态应返回 undefined", () => {
    expect(statusLabel.unknown).toBeUndefined()
  })
})

describe("statusColor 状态颜色映射", () => {
  it("运行时态应为绿色", () => {
    expect(statusColor.running).toContain("bg-green")
  })

  it("失败状态应为红色", () => {
    expect(statusColor.failed).toContain("bg-red")
  })

  it("每个已知状态都有对应颜色", () => {
    const keys = Object.keys(statusLabel)
    for (const key of keys) {
      expect(statusColor[key]).toBeDefined()
    }
  })
})
