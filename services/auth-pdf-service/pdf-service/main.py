import os
import httpx
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase import create_client

# =========================
# Config
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET_NAME = "pdfs"

# URL of auth-service to verify tokens
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="PDF Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Helpers
# =========================

def storage_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def user_path(user_id: str, filename: str) -> str:
    return f"{user_id}/{filename}"

def verify_token(authorization: str) -> dict:
    """Call auth-service to verify JWT and get user info."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header.")
    try:
        res = httpx.get(
            f"{AUTH_SERVICE_URL}/verify",
            headers={"Authorization": authorization},
            timeout=10
        )
        if res.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        return res.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable.")

def register_pdf(user_id: str, pdf_name: str):
    client = storage_client()
    client.table("user_pdfs").insert({"user_id": user_id, "pdf_name": pdf_name}).execute()

def remove_pdf_record(user_id: str, pdf_name: str):
    client = storage_client()
    client.table("user_pdfs").delete().eq("user_id", user_id).eq("pdf_name", pdf_name).execute()

def get_user_pdfs(user_id: str) -> list:
    client = storage_client()
    res = client.table("user_pdfs").select("pdf_name").eq("user_id", user_id).execute()
    return [r["pdf_name"] for r in res.data]

# =========================
# Endpoints
# =========================

@app.get("/")
async def home():
    return {"service": "pdf-service", "status": "running"}


@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    user = verify_token(authorization)
    user_id = user["user_id"]

    file_bytes = await file.read()
    path = user_path(user_id, file.filename)

    # Upload to Supabase Storage
    client = storage_client()
    client.storage.from_(BUCKET_NAME).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"}
    )

    # Register in DB
    register_pdf(user_id, file.filename)

    return {
        "message": f"{file.filename} uploaded successfully!",
        "pdf_name": file.filename,
        "user_id": user_id
    }


@app.get("/pdfs")
async def list_pdfs(authorization: Optional[str] = Header(None)):
    user = verify_token(authorization)
    pdfs = get_user_pdfs(user["user_id"])
    return {"pdfs": pdfs}


@app.delete("/pdfs/{pdf_name}")
async def delete_pdf(
    pdf_name: str,
    authorization: Optional[str] = Header(None)
):
    user = verify_token(authorization)
    user_id = user["user_id"]
    path = user_path(user_id, pdf_name)

    client = storage_client()
    client.storage.from_(BUCKET_NAME).remove([path])
    remove_pdf_record(user_id, pdf_name)

    return {"message": f"{pdf_name} deleted successfully."}


@app.get("/download/{pdf_name}")
async def download_pdf(
    pdf_name: str,
    authorization: Optional[str] = Header(None)
):
    """Used by rag-service to fetch PDF bytes for processing."""
    user = verify_token(authorization)
    user_id = user["user_id"]
    path = user_path(user_id, pdf_name)

    client = storage_client()
    file_bytes = client.storage.from_(BUCKET_NAME).download(path)

    from fastapi.responses import Response
    return Response(content=file_bytes, media_type="application/pdf")


# =========================
# Run Locally
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)