"""
Snippets 代码片段管理 API — 对标 VSCode workbench/contrib/snippets
端点: GET/POST /system/snippets | GET/PUT/DELETE /{id} | GET /languages | POST /import | GET /export
"""
from __future__ import annotations
import json, logging, uuid
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/snippets", tags=["Snippets"])

# 内置默认片段
_BUILTIN: list[dict] = [
    {"id":"builtin-vue3-comp","prefix":"vcomp","name":"Vue 3 Component","language":"vue","body":'<script setup lang="ts">\n\n</script>\n\n<template>\n  <div class="$1">$2</div>\n</template>\n\n<style scoped>\n.$1 { $3 }\n</style>',"tags":["vue"]},
    {"id":"builtin-ts-func","prefix":"tfunc","name":"TypeScript Function","language":"typescript","body":"function $1($2): $3 {\n  $4\n}","tags":["typescript"]},
    {"id":"builtin-ts-arrow","prefix":"tarrow","name":"Arrow Function","language":"typescript","body":"const $1 = ($2): $3 => {\n  $4\n}","tags":["typescript"]},
    {"id":"builtin-clog","prefix":"clog","name":"Console Log","language":"javascript","body":'console.log("$1:", $1)',"tags":["debug"]},
    {"id":"builtin-py-func","prefix":"pfunc","name":"Python Function","language":"python","body":'def $1($2):\n    """$3"""\n    $4',"tags":["python"]},
    {"id":"builtin-py-class","prefix":"pclass","name":"Python Class","language":"python","body":"class $1:\n    def __init__(self, $2):\n        $3","tags":["python"]},
    {"id":"builtin-py-async","prefix":"pasync","name":"Async Function","language":"python","body":'async def $1($2):\n    """$3"""\n    $4',"tags":["python","async"]},
    {"id":"builtin-html5","prefix":"html5","name":"HTML5 Boilerplate","language":"html","body":'<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>$1</title>\n</head>\n<body>$2</body>\n</html>',"tags":["html"]},
    {"id":"builtin-react-fc","prefix":"rfc","name":"React FC","language":"typescriptreact","body":'import React from "react"\n\ninterface $1Props { $2 }\n\nexport const $1: React.FC<$1Props> = ({ $3 }) => {\n  return (<div>$4</div>)\n}',"tags":["react"]},
    {"id":"builtin-react-useeffect","prefix":"rue","name":"useEffect","language":"typescriptreact","body":"useEffect(() => {\n  $1\n  return () => { $2 }\n}, [$3])","tags":["react"]},
    {"id":"builtin-if","prefix":"if","name":"If Statement","language":None,"body":"if ($1) {\n  $2\n}","tags":["universal"]},
    {"id":"builtin-for","prefix":"for","name":"For Loop","language":"javascript","body":"for (let $1 = 0; $1 < $2; $1++) {\n  $3\n}","tags":["universal","loop"]},
    {"id":"builtin-try","prefix":"try","name":"Try-Catch","language":None,"body":"try {\n  $1\n} catch ($2) {\n  $3\n}","tags":["universal"]},
    {"id":"builtin-fastapi-route","prefix":"froute","name":"FastAPI Route","language":"python","body":"@router.$1(\"/$2\")\nasync def $3($4):\n    $5\n    return $6","tags":["python","fastapi"]},
    {"id":"builtin-dockerfile","prefix":"docker","name":"Dockerfile","language":"dockerfile","body":"FROM $1\n\nWORKDIR /app\n\nCOPY . .\n\nRUN $2\n\nCMD [\"$3\"]","tags":["docker","devops"]},
]

_store: dict[str, dict] = {}
_inited = False

def _init():
    global _inited
    if _inited: return
    for s in _BUILTIN: _store[s["id"]] = dict(s)
    _inited = True

class SnippetCreate(BaseModel):
    prefix: str = Field(..., min_length=1, max_length=256)
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    body: str = Field(..., min_length=1, max_length=65536)
    language: str | None = None
    tags: list[str] = []

class SnippetUpdate(BaseModel):
    prefix: str | None = None
    name: str | None = None
    description: str | None = None
    body: str | None = None
    language: str | None = None
    tags: list[str] | None = None

class SnippetResp(BaseModel):
    id: str; prefix: str; name: str; description: str; body: str
    language: str | None; tags: list[str] = []; is_builtin: bool = False

def _resp(s: dict) -> SnippetResp:
    return SnippetResp(id=s["id"],prefix=s.get("prefix",""),name=s.get("name",""),
        description=s.get("description",""),body=s.get("body",""),
        language=s.get("language"),tags=s.get("tags",[]),
        is_builtin=str(s["id"]).startswith("builtin-"))

def _check(id: str) -> dict:
    _init()
    if id not in _store: raise HTTPException(404, f"Snippet not found: {id}")
    return _store[id]

@router.get("", response_model=list[SnippetResp])
async def list_snippets(language: str|None=None, tag: str|None=None, search: str|None=None):
    _init(); r = list(_store.values())
    if language: r = [s for s in r if s.get("language") in (language, None)]
    if tag: r = [s for s in r if tag in (s.get("tags") or [])]
    if search: r = [s for s in r if search.lower() in s["name"].lower() or search.lower() in s["prefix"].lower()]
    return [_resp(s) for s in r]

@router.get("/languages")
async def list_languages():
    _init()
    langs = sorted(set(s.get("language") for s in _store.values() if s.get("language")))
    return {"languages": langs, "count": len(langs)}

@router.get("/for-language/{lang}", response_model=list[SnippetResp])
async def snippets_for_language(lang: str):
    """Monaco 补全 Provider 专用：获取某语言的片段"""
    _init()
    r = [s for s in _store.values() if s.get("language") in (lang, None)]
    return [_resp(s) for s in r]

@router.post("", response_model=SnippetResp)
async def create_snippet(req: SnippetCreate):
    _init()
    sid = str(uuid.uuid4())[:12]
    s = {"id": sid, "prefix": req.prefix, "name": req.name,
         "description": req.description, "body": req.body,
         "language": req.language, "tags": req.tags}
    _store[sid] = s
    return _resp(s)

@router.get("/{sid}", response_model=SnippetResp)
async def get_snippet(sid: str): return _resp(_check(sid))

@router.put("/{sid}", response_model=SnippetResp)
async def update_snippet(sid: str, req: SnippetUpdate):
    s = _check(sid)
    for k in ("prefix","name","description","body","language","tags"):
        if getattr(req, k) is not None: s[k] = getattr(req, k)
    return _resp(s)

@router.delete("/{sid}")
async def delete_snippet(sid: str):
    s = _check(sid)
    if str(s["id"]).startswith("builtin-"): raise HTTPException(403, "Cannot delete builtin snippet")
    del _store[sid]
    return {"status": "deleted", "id": sid}

@router.post("/import")
async def import_snippets(data: list[SnippetCreate]):
    _init(); imported = 0
    for item in data:
        sid = str(uuid.uuid4())[:12]
        _store[sid] = {"id":sid,"prefix":item.prefix,"name":item.name,
                       "description":item.description,"body":item.body,
                       "language":item.language,"tags":item.tags}; imported += 1
    return {"imported": imported}

@router.get("/export")
async def export_snippets(language: str|None=None):
    _init()
    r = [s for s in _store.values() if not str(s["id"]).startswith("builtin-")]
    if language: r = [s for s in r if s.get("language") == language]
    return Response(content=json.dumps(r, ensure_ascii=False, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=snippets-export.json"})
