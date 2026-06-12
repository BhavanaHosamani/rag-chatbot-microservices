import os
import httpx
import tempfile
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# =========================
# Config
# =========================

os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
PDF_SERVICE_URL  = os.getenv("PDF_SERVICE_URL",  "http://localhost:8002")

app = FastAPI(title="RAG Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# In-memory vector stores
# { "user_id/filename.pdf": <Chroma> }
# =========================

pdf_stores: dict = {}

# =========================
# Helpers
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


def get_embeddings():
    return OpenAIEmbeddings(
        model="openai/text-embedding-ada-002",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )


def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    return splitter.split_documents(documents)


# =========================
# Models
# =========================

class IndexRequest(BaseModel):
    pdf_name: str  # filename only — service fetches bytes from pdf-service

class SearchRequest(BaseModel):
    query: str
    pdf_name: Optional[str] = None  # None = search all user's PDFs

# =========================
# Endpoints
# =========================

@app.get("/")
async def home():
    return {"service": "rag-service", "status": "running"}


@app.post("/index")
async def index_pdf(
    req: IndexRequest,
    authorization: Optional[str] = Header(None)
):
    """Download PDF from pdf-service, build vector store, store in memory."""
    user = verify_token(authorization)
    user_id = user["user_id"]
    store_key = f"{user_id}/{req.pdf_name}"

    # Fetch PDF bytes from pdf-service
    try:
        res = httpx.get(
            f"{PDF_SERVICE_URL}/download/{req.pdf_name}",
            headers={"Authorization": authorization},
            timeout=60
        )
        if res.status_code != 200:
            raise HTTPException(status_code=404, detail="PDF not found in pdf-service.")
        pdf_bytes = res.content
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="PDF service unavailable.")

    # Write to temp file and load
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    loader = PyPDFLoader(tmp_path)
    documents = loader.load()
    chunks = split_documents(documents)
    os.unlink(tmp_path)

    # Build vector store
    embeddings = get_embeddings()
    vector_store = Chroma.from_documents(chunks, embeddings)
    pdf_stores[store_key] = vector_store

    return {
        "message": f"{req.pdf_name} indexed successfully.",
        "store_key": store_key,
        "chunks": len(chunks)
    }


@app.post("/search")
async def search(
    req: SearchRequest,
    authorization: Optional[str] = Header(None)
):
    """Search across one or all of a user's indexed PDFs."""
    user = verify_token(authorization)
    user_id = user["user_id"]

    if req.pdf_name:
        store_key = f"{user_id}/{req.pdf_name}"
        targets = {store_key: pdf_stores[store_key]} if store_key in pdf_stores else {}
    else:
        targets = {k: v for k, v in pdf_stores.items() if k.startswith(f"{user_id}/")}

    if not targets:
        return {"context": None, "found": False}

    all_results = []
    for key, store in targets.items():
        docs = store.similarity_search(req.query, k=6)
        if docs:
            if len(targets) > 1:
                pdf_label = key.split("/", 1)[-1]
                all_results.append(f"── From: {pdf_label} ──")
            for i, doc in enumerate(docs):
                all_results.append(f"[Section {i+1}]:\n{doc.page_content}")

    if not all_results:
        return {"context": None, "found": False}

    return {"context": "\n\n".join(all_results), "found": True}


@app.delete("/index/{pdf_name}")
async def delete_index(
    pdf_name: str,
    authorization: Optional[str] = Header(None)
):
    """Remove a PDF's vector store from memory."""
    user = verify_token(authorization)
    store_key = f"{user['user_id']}/{pdf_name}"
    pdf_stores.pop(store_key, None)
    return {"message": f"Index for {pdf_name} removed."}


@app.get("/indexed")
async def list_indexed(authorization: Optional[str] = Header(None)):
    """List all PDFs currently indexed for this user."""
    user = verify_token(authorization)
    user_id = user["user_id"]
    keys = [k.split("/", 1)[-1] for k in pdf_stores if k.startswith(f"{user_id}/")]
    return {"indexed": keys}


# =========================
# Run Locally
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)