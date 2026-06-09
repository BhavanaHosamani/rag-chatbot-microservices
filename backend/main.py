import os
import shutil
import httpx

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag.loader import load_documents
from rag.splitter import split_documents
from rag.embeddings import get_embeddings
from rag.vector_store import create_vector_store
from rag.tools import set_vector_store, search_pdf
from rag.agent import create_agent
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

# =========================
# OpenRouter Configuration
# ==================
import os

api_key = os.getenv("OPENROUTER_API_KEY")
os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

http_client = httpx.Client(
    timeout=120.0
)

# =========================
# FastAPI App
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_executor = create_agent()

# =========================
# Direct LLM for PDF Q&A
# =========================

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0.7,
    api_key=os.environ["OPENAI_API_KEY"],
    base_url="https://openrouter.ai/api/v1"
)

# =========================
# Request Model
# =========================

class QueryRequest(BaseModel):
    question: str
    chat_history: list = []

# =========================
# Upload PDF Endpoint
# =========================

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):

    os.makedirs("storage/documents", exist_ok=True)

    file_path = f"storage/documents/{file.filename}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    documents = load_documents("storage/documents")
    chunks = split_documents(documents)
    embeddings = get_embeddings()
    vector_store = create_vector_store(chunks, embeddings)
    set_vector_store(vector_store)

    return {
        "message": f"{file.filename} uploaded and processed successfully!"
    }

# =========================
# Ask Question Endpoint
# =========================

@app.post("/ask")
async def ask_question(request: QueryRequest):

    question = request.question

    # Check if PDF context is available
    context = search_pdf(question)
    
    if context and context != "No PDF uploaded yet. Please upload and process a PDF first.":
        # Use direct LLM with PDF context — no agent needed
        messages = [
            SystemMessage(content="""You are a highly knowledgeable AI assistant. 
You will be given context extracted from a PDF document and a question.
Your job is to answer the question in detail using the context provided.

Rules:
- Give thorough, detailed, well-structured answers
- Use bullet points or numbered lists where appropriate  
- Minimum 5-8 sentences
- Include specific details, numbers, facts from the context
- If the context covers multiple aspects, cover all of them
- Never give vague or one-line answers
- If something is not in the context, say so clearly"""),
            HumanMessage(content=f"""Context from PDF:
{context}

Question: {question}

Please provide a detailed and thorough answer based on the context above.""")
        ]

        response = llm.invoke(messages)

        return {
            "answer": response.content,
            "mode": "pdf",
            "steps": [],
            "sources": []
        }

    else:
        # No PDF — use agent for general questions
        result = agent_executor.invoke({
            "input": question
        })

        steps = result.get("intermediate_steps", [])
        formatted_steps = []

        if steps:
            for step in steps:
                if isinstance(step, tuple):
                    action, observation = step
                    formatted_steps.append({
                        "agent": str(action.tool) if hasattr(action, 'tool') else "",
                        "input": str(action.tool_input) if hasattr(action, 'tool_input') else "",
                        "output": str(observation)
                    })
                elif isinstance(step, dict):
                    formatted_steps.append({
                        "agent": step.get("agent", ""),
                        "input": step.get("input", ""),
                        "output": step.get("output", "")
                    })

        return {
            "answer": result["output"],
            "mode": "agent",
            "steps": formatted_steps,
            "sources": []
        }

# =========================
# Run Server
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )