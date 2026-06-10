"""
Prompt templates for code generation tasks.

模板变量说明：
  - SCREENSHOT_TO_LAYOUT : 无变量，直接使用。输入：截图图片 → 输出：布局 JSON
  - LAYOUT_TO_CODE        : {framework}, {layout_json} — 布局 JSON → 前端组件代码
  - TEXT_TO_FULLSTACK     : {description}, {framework}, {backend_section} — 需求 → 全栈项目
  - PROJECT_STRUCTURE     : {description}, {stack} — 需求 → 目录结构建议
  - API_GENERATION        : {method}, {path}, {description}, {request_schema}, {response_schema} — 生成 FastAPI 端点

Usage:
    from ai_models.prompts.code_gen import LAYOUT_TO_CODE
    prompt = LAYOUT_TO_CODE.format(
        framework="vue",
        layout_json='{"page": "home", "components": [...]}'
    )
"""

# -- 截图 → 布局 JSON --
# 输入：UI 截图图片（通过 VL 模型的 image 参数传入）
# 输出：严格的 JSON（不包含 markdown 包裹），描述页面结构
SCREENSHOT_TO_LAYOUT = """You are a UI analysis expert. Analyze the provided screenshot and output a structured layout JSON.

Rules:
1. Identify all visible UI elements (buttons, inputs, cards, navbars, etc.)
2. Record position (x, y, width, height), type, text content, and hierarchy
3. Group nested elements under their parent container
4. Output ONLY valid JSON, no explanation

Output format:
{
  "page": "page name",
  "layout": "flex | grid | absolute",
  "components": [
    {
      "type": "button | input | card | navbar | text | image | ...",
      "text": "visible text",
      "position": {"x": 0, "y": 0, "w": 100, "h": 40},
      "style": {"bg": "#hex", "rounded": true, "shadow": "..."},
      "children": [...]
    }
  ]
}

Analyze this screenshot:"""

# -- 布局 JSON → 代码 --
# 变量：{framework} - 目标框架（vue/react/html）
#       {layout_json} - SCREENSHOT_TO_LAYOUT 输出的 JSON 字符串
LAYOUT_TO_CODE = """You are an expert {framework} developer. Convert the following UI layout JSON into production-ready {framework} code.

Requirements:
- Use modern {framework} best practices
- Use Tailwind CSS for styling
- Make it responsive (mobile-first)
- Include proper TypeScript types
- Componentize reusable parts
- Add comments for complex logic

Layout JSON:
{layout_json}

Generate the complete component code:"""

# -- 文本描述 → 全栈项目 --
# 变量：{description} - 自然语言需求描述
#       {framework} - 前端框架
#       {backend_section} - 后端需求（如果 include_backend=True，则包含数据库/API 要求）
TEXT_TO_FULLSTACK = """You are a fullstack architect. Design and generate a complete project based on this description:

{description}

Generate the following files:

--- FRONTEND ---
- {framework} components with TypeScript + Tailwind CSS
- Include state management, API calls, routing

--- BACKEND ---
- FastAPI endpoints with Pydantic models
- SQLModel database models
- Proper error handling
{backend_section}

Description of what to build:"""

# -- 项目结构生成 --
# 变量：{description} - 项目需求
#       {stack} - 技术栈（如 "fastapi+react"）
PROJECT_STRUCTURE = """Based on the following project requirements, generate a recommended project structure:

Requirements: {description}

Output a directory tree with brief descriptions for each file/folder.
Use standard conventions for a {stack} project."""

# -- API 代码生成 --
# 变量：{method} - HTTP 方法（GET/POST/PUT/DELETE）
#       {path} - API 路径
#       {description} - 接口说明
#       {request_schema} - 请求体 JSON Schema（可为空）
#       {response_schema} - 响应体 JSON Schema（可为空）
API_GENERATION = """Generate a FastAPI endpoint based on this specification:

Endpoint: {method} {path}
Description: {description}
Request body: {request_schema}
Response: {response_schema}

Include:
- Pydantic models for request/response
- SQLModel database model if needed
- Service layer function
- Proper HTTP status codes and error handling
- Type hints throughout"""


__all__ = [
    "SCREENSHOT_TO_LAYOUT",
    "LAYOUT_TO_CODE",
    "TEXT_TO_FULLSTACK",
    "PROJECT_STRUCTURE",
    "API_GENERATION",
]
