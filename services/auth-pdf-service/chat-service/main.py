import os
import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory
from langchain.agents import initialize_agent, AgentType
from langchain_core.tools import Tool

# =========================
# Config
# =========================

os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
RAG_SERVICE_URL  = os.getenv("RAG_SERVICE_URL",  "http://localhost:8003")

app = FastAPI(title="Chat Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# LLM
# =========================

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0.7,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

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


def fetch_context(query: str, pdf_name: Optional[str], authorization: str) -> Optional[str]:
    """Call rag-service to get relevant context for a query."""
    try:
        res = httpx.post(
            f"{RAG_SERVICE_URL}/search",
            json={"query": query, "pdf_name": pdf_name},
            headers={"Authorization": authorization},
            timeout=30
        )
        if res.status_code == 200:
            data = res.json()
            if data.get("found"):
                return data["context"]
        return None
    except httpx.RequestError:
        return None


def build_agent(authorization: str):
    """Build a LangChain agent that calls rag-service as a tool."""

    def rag_search(query: str) -> str:
        context = fetch_context(query, None, authorization)
        return context or "No relevant content found in uploaded PDFs."

    pdf_tool = Tool(
        name="PDF_Search",
        func=rag_search,
        description="""Use this tool whenever the user asks about an uploaded PDF document.
        Input should be the user's question or relevant keywords."""
    )

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="output"
    )

    agent = initialize_agent(
        tools=[pdf_tool],
        llm=llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        memory=memory,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )
    return agent


# =========================
# Models
# =========================

class AskRequest(BaseModel):
    question: str
    chat_history: list = []
    pdf_name: Optional[str] = None

# =========================
# Endpoints
# =========================

@app.get("/")
async def home():
    return {"service": "chat-service", "status": "running"}


@app.post("/ask")
async def ask(
    req: AskRequest,
    authorization: Optional[str] = Header(None)
):
    user = verify_token(authorization)
    question = req.question
    pdf_name = req.pdf_name

    # Try to get PDF context from rag-service
    context = fetch_context(question, pdf_name, authorization)

    if context:
        # Answer using PDF context
        messages = [
            SystemMessage(content="""
You are a highly knowledgeable AI assistant.
Answer only using the provided PDF context.
Rules:
- Give detailed answers
- Use bullet points when appropriate
- Minimum 5-8 sentences
- Include important facts and details
- Be clear and structured
- If information is missing, say so
"""),
            HumanMessage(content=f"Context from PDF:\n\n{context}\n\nQuestion:\n\n{question}\n\nProvide a detailed answer.")
        ]
        response = llm.invoke(messages)
        return {
            "answer": response.content,
            "mode": "pdf",
            "steps": [],
            "sources": []
        }

    else:
        # Fall back to general agent
        agent = build_agent(authorization)
        result = agent.invoke({"input": question})

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
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True)