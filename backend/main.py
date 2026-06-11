import os
import shutil
import httpx
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from rag.loader import load_documents
from rag.splitter import split_documents
from rag.embeddings import get_embeddings
from rag.vector_store import create_vector_store
from rag.tools import set_vector_store, search_pdf, get_pdf_list, delete_pdf_store
from rag.agent import create_agent
from rag.supabase_storage import (
    upload_pdf_to_supabase,
    download_pdf_from_supabase,
    delete_pdf_from_supabase,
    list_pdfs_from_supabase,
)

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain_community.document_loaders import PyPDFLoader

# =========================
# OpenRouter Configuration
# =========================

os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

http_client = httpx.Client(timeout=120.0)

# =========================
# FastAPI App
# =========================

app = FastAPI(title="RAG Chatbot API", version="3.0.0")


@app.get("/")
async def home():
    return {"message": "RAG Chatbot API is running!", "status": "success"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Agent & LLM Init
# =========================

agent_executor = create_agent()

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# =========================
# Restore PDFs on startup
# =========================

@app.on_event("startup")
async def restore_pdfs_on_startup():
    """
    On every Render restart, re-download all PDFs from Supabase
    and rebuild their vector stores in memory.
    """
    print("🔄 Restoring PDFs from Supabase Storage...")
    pdf_names = list_pdfs_from_supabase()

    embeddings = get_embeddings()

    for pdf_name in pdf_names:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp_path = tmp.name

            download_pdf_from_supabase(pdf_name, tmp_path)

            loader = PyPDFLoader(tmp_path)
            documents = loader.load()
            chunks = split_documents(documents)
            vector_store = create_vector_store(chunks, embeddings)
            set_vector_store(pdf_name, vector_store)

            os.unlink(tmp_path)
            print(f"  ✅ Restored: {pdf_name}")
        except Exception as e:
            print(f"  ❌ Failed to restore {pdf_name}: {e}")

    print(f"✅ Restored {len(pdf_names)} PDF(s) from Supabase.")

# =========================
# Request Models
# =========================

class QueryRequest(BaseModel):
    question: str
    chat_history: list = []
    pdf_name: Optional[str] = None


# =========================
# Upload PDF Endpoint
# =========================

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload PDF → save to Supabase Storage → build vector store in memory."""

    # Read file bytes
    file_bytes = await file.read()

    # 1. Upload to Supabase Storage
    upload_pdf_to_supabase(file.filename, file_bytes)

    # 2. Save to a temp file for processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    # 3. Build vector store
    loader = PyPDFLoader(tmp_path)
    documents = loader.load()
    chunks = split_documents(documents)
    embeddings = get_embeddings()
    vector_store = create_vector_store(chunks, embeddings)
    set_vector_store(file.filename, vector_store)

    # 4. Clean up temp file
    os.unlink(tmp_path)

    return {
        "message": f"{file.filename} uploaded and processed successfully!",
        "pdf_name": file.filename,
        "chunks": len(chunks),
        "storage": "supabase"
    }


# =========================
# List PDFs Endpoint
# =========================

@app.get("/pdfs")
async def list_pdfs():
    """Return all PDFs stored in Supabase."""
    pdfs = list_pdfs_from_supabase()
    return {"pdfs": pdfs}


# =========================
# Delete PDF Endpoint
# =========================

@app.delete("/pdfs/{pdf_name}")
async def delete_pdf(pdf_name: str):
    """Delete PDF from Supabase Storage + remove its vector store from memory."""

    # Remove from Supabase
    deleted = delete_pdf_from_supabase(pdf_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"{pdf_name} not found in storage.")

    # Remove from in-memory vector stores
    delete_pdf_store(pdf_name)

    return {"message": f"{pdf_name} deleted successfully."}


# =========================
# Ask Question Endpoint
# =========================

@app.post("/ask")
async def ask_question(request: QueryRequest):
    question = request.question
    pdf_name = request.pdf_name

    context = search_pdf(question, pdf_name=pdf_name)

    no_pdf_messages = [
        "No PDF uploaded yet. Please upload and process a PDF first.",
        "Selected PDF not found. Please re-upload.",
    ]

    if context and context not in no_pdf_messages:
        messages = [
            SystemMessage(content="""
You are a highly knowledgeable AI assistant.

You will be given context extracted from a PDF document and a question.

Answer only using the provided context.

Rules:
- Give detailed answers
- Use bullet points when appropriate
- Minimum 5-8 sentences
- Include important facts and details
- Be clear and structured
- If information is missing, say so
"""),
            HumanMessage(content=f"""
Context from PDF:

{context}

Question:

{question}

Provide a detailed answer.
""")
        ]

        response = llm.invoke(messages)
        return {
            "answer": response.content,
            "mode": "pdf",
            "steps": [],
            "sources": []
        }

    else:
        result = agent_executor.invoke({"input": question})

        steps = result.get("intermediate_steps", [])
        formatted_steps = []
        for step in steps:
            if isinstance(step, tuple):
                action, observation = step
                formatted_steps.append({
                    "agent": str(action.tool) if hasattr(action, "tool") else "",
                    "input": str(action.tool_input) if hasattr(action, "tool_input") else "",
                    "output": str(observation)
                })

        return {
            "answer": result["output"],
            "mode": "agent",
            "steps": formatted_steps,
            "sources": []
        }


# =========================
# Run Locally
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)