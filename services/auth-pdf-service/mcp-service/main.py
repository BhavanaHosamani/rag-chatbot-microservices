import os
import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any

from tools.web_search import web_search
from tools.file_system import read_file, write_file, list_files
from tools.supabase_db import query_user_pdfs, get_pdf_count

# =========================
# Config
# =========================

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="MCP Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Auth Helper
# =========================

def verify_token(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header.")
    try:
        res = httpx.get(
            f"{AUTH_SERVICE_URL}/verify",
            headers={"Authorization": authorization},
            timeout=10
        )
        if res.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid token.")
        return res.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable.")

# =========================
# Request Models
# =========================

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class DBQueryRequest(BaseModel):
    user_id: Optional[str] = None  # if None, uses token's user_id

class MCPToolRequest(BaseModel):
    tool: str          # "web_search" | "read_file" | "write_file" | "list_files" | "db_query"
    params: dict = {}

# =========================
# Endpoints
# =========================

@app.get("/")
async def home():
    return {
        "service": "mcp-service",
        "status": "running",
        "tools": ["web_search", "read_file", "write_file", "list_files", "db_query"]
    }


@app.get("/tools")
async def list_tools():
    """List all available MCP tools."""
    return {
        "tools": [
            {
                "name": "web_search",
                "description": "Search the web using DuckDuckGo",
                "params": {"query": "string", "max_results": "int (default 5)"}
            },
            {
                "name": "read_file",
                "description": "Read contents of a file",
                "params": {"path": "string"}
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "params": {"path": "string", "content": "string"}
            },
            {
                "name": "list_files",
                "description": "List files in a directory",
                "params": {"path": "string (optional, default '/')"}
            },
            {
                "name": "db_query",
                "description": "Query user's PDF records from Supabase",
                "params": {}
            }
        ]
    }


@app.post("/tools/call")
async def call_tool(
    req: MCPToolRequest,
    authorization: Optional[str] = Header(None)
):
    """Universal tool caller — routes to the right tool."""
    user = verify_token(authorization)
    user_id = user["user_id"]

    tool = req.tool
    params = req.params

    if tool == "web_search":
        query = params.get("query", "")
        max_results = params.get("max_results", 5)
        if not query:
            raise HTTPException(status_code=400, detail="query is required for web_search")
        result = await web_search(query, max_results)
        return {"tool": tool, "result": result}

    elif tool == "read_file":
        path = params.get("path", "")
        if not path:
            raise HTTPException(status_code=400, detail="path is required for read_file")
        result = read_file(path)
        return {"tool": tool, "result": result}

    elif tool == "write_file":
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            raise HTTPException(status_code=400, detail="path is required for write_file")
        result = write_file(path, content)
        return {"tool": tool, "result": result}

    elif tool == "list_files":
        path = params.get("path", "/tmp")
        result = list_files(path)
        return {"tool": tool, "result": result}

    elif tool == "db_query":
        result = query_user_pdfs(user_id)
        return {"tool": tool, "result": result}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}. Available: web_search, read_file, write_file, list_files, db_query")


# =========================
# Individual Tool Endpoints
# =========================

@app.post("/tools/web-search")
async def tool_web_search(
    req: WebSearchRequest,
    authorization: Optional[str] = Header(None)
):
    verify_token(authorization)
    result = await web_search(req.query, req.max_results)
    return {"results": result}


@app.post("/tools/read-file")
async def tool_read_file(
    req: FileReadRequest,
    authorization: Optional[str] = Header(None)
):
    verify_token(authorization)
    result = read_file(req.path)
    return {"content": result}


@app.post("/tools/write-file")
async def tool_write_file(
    req: FileWriteRequest,
    authorization: Optional[str] = Header(None)
):
    verify_token(authorization)
    result = write_file(req.path, req.content)
    return {"message": result}


@app.get("/tools/db-query")
async def tool_db_query(
    authorization: Optional[str] = Header(None)
):
    user = verify_token(authorization)
    result = query_user_pdfs(user["user_id"])
    return {"pdfs": result}


# =========================
# Run Locally
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)