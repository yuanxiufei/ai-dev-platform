"""
OpenAPI Server Discovery — 自动发现 OpenAPI 端点并注册为工具 (借鉴 Open WebUI OpenAPI)

解析 OpenAPI 3.x Spec，将每个 operation 转换为可调用的 Tool。
自动 schema 映射：OpenAPI Schema → Tool Parameter Schema。
"""

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin

import httpx


@dataclass
class OpenAPITool:
    """由 OpenAPI 操作转换而来的工具"""
    id: str
    name: str
    description: str = ""
    method: str = "GET"
    path: str = "/"
    server_url: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    request_body_schema: Optional[dict] = None
    # 来源信息
    source_spec_id: str = ""
    source_server_name: str = ""
    tags: list[str] = field(default_factory=list)
    # 调用配置
    timeout: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)

    def to_tool_schema(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for pname, pschema in self.parameters.items():
            prop = {
                "type": pschema.get("type", "string"),
                "description": pschema.get("description", ""),
            }
            if "enum" in pschema:
                prop["enum"] = pschema["enum"]
            if "default" in pschema:
                prop["default"] = pschema["default"]
            properties[pname] = prop
            if pschema.get("required", False):
                required.append(pname)

        tool = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
        return tool

    async def call(self, arguments: dict[str, Any] = None) -> dict:
        """调用远程 API"""
        url = urljoin(self.server_url, self.path)

        # 替换路径参数
        if arguments:
            for key, val in arguments.items():
                if f"{{{key}}}" in url:
                    url = url.replace(f"{{{key}}}", str(val))

        headers = {**self.headers}
        params = {}
        body = None

        if self.method.upper() in ("GET", "DELETE"):
            # 非路径参数作为 query string
            if arguments:
                params = {
                    k: v for k, v in arguments.items()
                    if f"{{{k}}}" not in self.path
                }
        else:
            # POST/PUT/PATCH → JSON body
            if self.request_body_schema:
                body = arguments or {}
            elif arguments:
                body = arguments

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(
                method=self.method.upper(),
                url=url,
                params=params or None,
                json=body,
                headers=headers,
            )

        try:
            result = resp.json()
        except json.JSONDecodeError:
            result = {"status_code": resp.status_code, "text": resp.text[:2000]}

        return {
            "status": resp.status_code,
            "headers": dict(resp.headers),
            "data": result,
        }


@dataclass
class OpenAPIServer:
    id: str
    name: str
    url: str = ""
    description: str = ""
    tools: list[OpenAPITool] = field(default_factory=list)
    spec_url: str = ""  # OpenAPI spec JSON URL
    headers: dict[str, str] = field(default_factory=dict)
    is_active: bool = True
    last_synced_at: str = ""
    tool_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "tools": [t.to_tool_schema() for t in self.tools],
            "spec_url": self.spec_url,
            "is_active": self.is_active,
            "last_synced_at": self.last_synced_at,
            "tool_count": self.tool_count,
        }


class OpenAPIDiscovery:
    """OpenAPI 自动发现引擎"""

    def __init__(self, storage_path: str = "data/openapi_servers.json"):
        self.storage_path = storage_path
        self._servers: dict[str, OpenAPIServer] = {}
        self._load()

    def _load(self) -> None:
        import os as _os
        _os.makedirs(_os.path.dirname(self.storage_path), exist_ok=True)
        if _os.path.isfile(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    svr = self._dict_to_server(item)
                    self._servers[svr.id] = svr
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        data = [s.to_dict() for s in self._servers.values()]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _dict_to_server(self, d: dict) -> OpenAPIServer:
        tools: list[OpenAPITool] = []
        for td in d.get("tools", []):
            # 从 tool_schema 重建（简化存储）
            tools.append(OpenAPITool(
                id=td.get("id", str(uuid.uuid4())[:8]),
                name=td.get("function", {}).get("name", td.get("name", "")),
                description=td.get("function", {}).get("description", td.get("description", "")),
            ))
        return OpenAPIServer(
            id=d.get("id", str(uuid.uuid4())[:8]),
            name=d.get("name", ""),
            url=d.get("url", ""),
            description=d.get("description", ""),
            spec_url=d.get("spec_url", ""),
            tools=tools,
            headers=d.get("headers", {}),
            is_active=d.get("is_active", True),
            last_synced_at=d.get("last_synced_at", ""),
            tool_count=d.get("tool_count", 0),
        )

    # ── 解析 OpenAPI Spec ──

    @staticmethod
    def _parse_parameters(params_list: list[dict]) -> dict[str, Any]:
        """解析 OpenAPI parameters → 扁平 schema"""
        result: dict[str, Any] = {}
        for param in params_list:
            name = param.get("name", "")
            schema = param.get("schema", {})
            result[name] = {
                "type": schema.get("type", "string"),
                "description": param.get("description", ""),
                "required": param.get("required", False),
                "in": param.get("in", "query"),
                "default": schema.get("default"),
            }
            if "enum" in schema:
                result[name]["enum"] = schema["enum"]
        return result

    @staticmethod
    def _schema_to_params(schema: dict) -> dict[str, Any]:
        """OpenAPI JSON Schema → 扁平 properties"""
        if not schema:
            return {}
        props = schema.get("properties", {})
        required = schema.get("required", [])
        result: dict[str, Any] = {}
        for name, prop in props.items():
            result[name] = {
                "type": prop.get("type", "string"),
                "description": prop.get("description", ""),
                "required": name in required,
            }
            if "enum" in prop:
                result[name]["enum"] = prop["enum"]
        return result

    @staticmethod
    def _sanitize_name(path: str, method: str) -> str:
        """将 OpenAPI path + method 转换为合法的工具名称"""
        # /users/{id} + GET → get_user_by_id
        clean = re.sub(r"[{}]", "", path)
        clean = clean.strip("/").replace("/", "_")
        parts = [p for p in clean.split("_") if p]
        # 去重
        seen: set[str] = set()
        unique: list[str] = []
        for p in parts:
            if p.lower() not in seen:
                unique.append(p.lower())
                seen.add(p.lower())
        name = f"{method.lower()}_{'_'.join(unique)}"
        return name[:64]  # 限制长度

    async def discover(self, spec_url: str, server_name: str = "",
                       headers: dict[str, str] = None) -> Optional[OpenAPIServer]:
        """从 OpenAPI spec URL 发现所有端点"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(spec_url, headers=headers or {})
                resp.raise_for_status()
                spec = resp.json()
        except Exception:
            return None

        # 获取服务器基础 URL
        servers = spec.get("servers", [{}])
        base_url = servers[0].get("url", spec_url.rsplit("/", 1)[0])

        info = spec.get("info", {})
        title = server_name or info.get("title", "Unknown API")
        server_id = str(uuid.uuid4())[:8]

        tools: list[OpenAPITool] = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method in ("get", "post", "put", "patch", "delete"):
                operation = path_item.get(method)
                if not operation:
                    continue

                tool_id = str(uuid.uuid4())[:8]
                op_id = operation.get("operationId", "")
                tool_name = op_id or self._sanitize_name(path, method)

                # 收集参数
                parameters = self._parse_parameters(operation.get("parameters", []))

                # 请求体
                request_body_schema = None
                rb = operation.get("requestBody", {})
                if rb and "application/json" in (rb.get("content") or {}):
                    request_body_schema = rb["content"]["application/json"].get("schema")

                    # 将 request body properties 也加入参数
                    body_params = self._schema_to_params(request_body_schema or {})
                    parameters.update(body_params)

                tool = OpenAPITool(
                    id=tool_id,
                    name=tool_name,
                    description=operation.get("summary", operation.get("description", "")),
                    method=method.upper(),
                    path=path,
                    server_url=base_url,
                    parameters=parameters,
                    request_body_schema=request_body_schema,
                    source_spec_id=server_id,
                    source_server_name=title,
                    tags=operation.get("tags", []),
                    headers=headers or {},
                )
                tools.append(tool)

        server = OpenAPIServer(
            id=server_id,
            name=title,
            url=base_url,
            description=info.get("description", ""),
            tools=tools,
            spec_url=spec_url,
            headers=headers or {},
            last_synced_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            tool_count=len(tools),
        )
        self._servers[server_id] = server
        self._save()
        return server

    # ── CRUD ──

    def list_servers(self) -> list[dict]:
        return [s.to_dict() for s in self._servers.values()]

    def get_server(self, server_id: str) -> Optional[OpenAPIServer]:
        return self._servers.get(server_id)

    def delete_server(self, server_id: str) -> bool:
        if server_id in self._servers:
            del self._servers[server_id]
            self._save()
            return True
        return False

    def list_all_tools(self, server_id: Optional[str] = None) -> list[OpenAPITool]:
        """列出所有工具（全局或按服务器）"""
        if server_id:
            svr = self._servers.get(server_id)
            return svr.tools if svr else []
        tools: list[OpenAPITool] = []
        for svr in self._servers.values():
            tools.extend(svr.tools)
        return tools

    def get_tool_schemas(self, server_id: Optional[str] = None) -> list[dict]:
        return [t.to_tool_schema() for t in self.list_all_tools(server_id)]

    @property
    def server_count(self) -> int:
        return len(self._servers)

    @property
    def total_tool_count(self) -> int:
        return sum(s.tool_count for s in self._servers.values())


# 全局单例
_discovery: Optional[OpenAPIDiscovery] = None


def get_openapi_discovery() -> OpenAPIDiscovery:
    global _discovery
    if _discovery is None:
        _discovery = OpenAPIDiscovery()
    return _discovery


def init_openapi_discovery(storage_path: str = "data/openapi_servers.json") -> OpenAPIDiscovery:
    global _discovery
    _discovery = OpenAPIDiscovery(storage_path=storage_path)
    return _discovery
