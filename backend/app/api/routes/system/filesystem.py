"""
文件系统 CRUD API — 对标 VSCode platform/files
端点: GET /list|/read|/info  POST /write|/mkdir|/move|/copy|/delete
安全: 禁止路径遍历攻击，限制在PROJECT_ROOT内
"""
from __future__ import annotations
import os, shutil, logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/filesystem", tags=["FileSystem"])
_ROOT = os.path.normpath(os.environ.get("PROJECT_ROOT", os.getcwd()))
_EXCLUDES = {".git","node_modules","__pycache__",".venv","venv","dist","build",".DS_Store"}

def _resolve(rel: str) -> str:
    abs_p = os.path.normpath(os.path.join(_ROOT, rel or "."))
    if not abs_p.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Path traversal not allowed")
    return abs_p

class FileEntry(BaseModel):
    name: str; path: str; type: str; size_bytes: int = 0
    modified_at: float = 0; extension: str = ""; is_hidden: bool = False

class WriteReq(BaseModel):
    path: str; content: str = Field(..., max_length=10*1024*1024)
    encoding: str = "utf-8"

class MoveReq(BaseModel): source: str; destination: str
class CopyReq(BaseModel): source: str; destination: str; overwrite: bool = False
class DeleteReq(BaseModel): path: str; recursive: bool = False
class MkdirReq(BaseModel): path: str; parents: bool = True

def _entry(p: Path) -> FileEntry:
    s = p.stat() if p.exists() else None
    return FileEntry(name=p.name, path=str(p.relative_to(_ROOT)).replace("\\","/"),
        type="directory" if p.is_dir() else "file",
        size_bytes=s.st_size if s and not p.is_dir() else 0,
        modified_at=s.st_mtime if s else 0, extension=p.suffix[1:] if p.suffix else "",
        is_hidden=p.name.startswith("."))

@router.get("/list", response_model=list[FileEntry])
async def ls(path: str = Query("."), show_hidden: bool = False):
    ap = _resolve(path)
    if not os.path.isdir(ap): raise HTTPException(400, "Not a directory")
    es = []
    for e in os.scandir(ap):
        if e.name in _EXCLUDES: continue
        if e.name.startswith(".") and not show_hidden: continue
        es.append(_entry(Path(e.path)))
    es.sort(key=lambda x: (0 if x.type=="directory" else 1, x.name.lower()))
    return es

@router.get("/read")
async def read(path: str = Query(...), encoding: str = "utf-8"):
    ap = _resolve(path)
    if not os.path.isfile(ap): raise HTTPException(404, "File not found")
    try:
        with open(ap,"r",encoding=encoding,errors="replace") as f:
            return {"content":f.read(),"path":path,"encoding":encoding}
    except UnicodeDecodeError:
        import base64
        with open(ap,"rb") as f:
            return {"content":base64.b64encode(f.read()).decode(),"encoding":"base64","path":path,"is_binary":True}

@router.post("/write")
async def write(req: WriteReq):
    ap = _resolve(req.path)
    os.makedirs(os.path.dirname(ap) or ".", exist_ok=True)
    with open(ap,"w",encoding=req.encoding,errors="replace") as f: f.write(req.content)
    return {"status":"written","path":req.path,"bytes":len(req.content.encode(req.encoding))}

@router.post("/mkdir")
async def mkdir(req: MkdirReq):
    ap = _resolve(req.path)
    os.makedirs(ap, exist_ok=req.parents)
    return {"status":"created","path":req.path}

@router.post("/move")
async def move(req: MoveReq):
    a,b = _resolve(req.source), _resolve(req.destination)
    if not os.path.exists(a): raise HTTPException(404,"Source not found")
    os.makedirs(os.path.dirname(b) or ".", exist_ok=True)
    shutil.move(a,b)
    return {"status":"moved","source":req.source,"destination":req.destination}

@router.post("/copy")
async def copy(req: CopyReq):
    a,b = _resolve(req.source), _resolve(req.destination)
    if not os.path.exists(a): raise HTTPException(404,"Source not found")
    if os.path.exists(b) and not req.overwrite: raise HTTPException(409,"Destination exists")
    os.makedirs(os.path.dirname(b) or ".", exist_ok=True)
    (shutil.copytree(a,b) if os.path.isdir(a) else shutil.copy2(a,b))
    return {"status":"copied","source":req.source,"destination":req.destination}

@router.post("/delete")
async def delete(req: DeleteReq):
    ap = _resolve(req.path)
    if not os.path.exists(ap): raise HTTPException(404,"Path not found")
    if os.path.normpath(ap) == os.path.normpath(_ROOT): raise HTTPException(403,"Cannot delete project root")
    if req.recursive and os.path.isdir(ap): shutil.rmtree(ap)
    elif os.path.isdir(ap): os.rmdir(ap)
    else: os.unlink(ap)
    return {"status":"deleted","path":req.path}

@router.get("/info")
async def info(path: str = Query(...)):
    ap = _resolve(path)
    if not os.path.exists(ap): raise HTTPException(404,"Path not found")
    s = os.stat(ap); p = Path(ap)
    return {"name":p.name,"path":path,"type":"directory" if p.is_dir() else "file",
        "size_bytes":s.st_size,"modified_at":s.st_mtime,"created_at":s.st_ctime,
        "extension":p.suffix[1:] if p.suffix else "","is_hidden":p.name.startswith("."),
        "is_readable":os.access(ap,os.R_OK),"is_writable":os.access(ap,os.W_OK)}
