#!/usr/bin/env tsx

import { execSync } from "node:child_process"

// 获取后端 OpenAPI 文档并生成前端客户端代码
async function generateClient() {
  const backendUrl = process.env.BACKEND_URL || "http://localhost:18000"
  const openapiPath = `${backendUrl}/api/v1/openapi.json`

  console.log(`Fetching OpenAPI document from ${openapiPath}`)

  try {
    // 使用 openapi-ts 工具生成客户端代码
    execSync(
      `npx @hey-api/openapi-ts --input="${openapiPath}" --output="./src/client"`,
      { stdio: "inherit" },
    )

    console.log("✅ API client generated successfully!")
  } catch (error) {
    console.error("❌ Failed to generate API client:", error)
    process.exit(1)
  }
}

generateClient()
