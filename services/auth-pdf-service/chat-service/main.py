import os
import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.agents import initialize_agent, AgentType
from langchain_core.tools import Tool

# =========================
# Config
# =========================

os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
RAG_SERVICE_URL  = os.getenv("RAG_SERVICE_URL",  "http://localhost:8003")
MCP_SERVICE_URL  = os.getenv("MCP_SERVICE_URL",  "http://localhost:8005")

app = FastAPI(title="Chat Service", version="2.0.0")

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


def fetch_rag_context(query: str, pdf_name: Optional[str], authorization: str) -> Optional[str]:
    """Call rag-service for PDF context."""
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


def call_mcp_tool(tool: str, params: dict, authorization: str) -> str:
    """Call mcp-service with a specific tool."""
    try:
        res = httpx.post(
            f"{MCP_SERVICE_URL}/tools/call",
            json={"tool": tool, "params": params},
            headers={"Authorization": authorization},
            timeout=30
        )
        if res.status_code == 200:
            data = res.json()
            result = data.get("result", "")
            if isinstance(result, list):
                # Format list results nicely
                return "\n".join([
                    f"- {r.get('title', '')}: {r.get('snippet', '')}"
                    for r in result if isinstance(r, dict)
                ])
            return str(result)
        return f"MCP tool error: {res.text}"
    except httpx.RequestError:
        return "MCP service unavailable."


def build_agent_with_mcp(authorization: str):
    """Build LangChain agent with PDF + MCP tools."""

    # Tool 1: PDF Search via rag-service
    def pdf_search(query: str) -> str:
        context = fetch_rag_context(query, None, authorization)
        return context or "No relevant content found in uploaded PDFs."

    # Tool 2: Web Search via mcp-service
    def web_search(query: str) -> str:
        return call_mcp_tool("web_search", {"query": query, "max_results": 5}, authorization)

    # Tool 3: File Read via mcp-service
    def file_read(path: str) -> str:
        return call_mcp_tool("read_file", {"path": path}, authorization)

    # Tool 4: File Write via mcp-service
    def file_write(input_str: str) -> str:
        # Expect format: "path::content"
        if "::" in input_str:
            path, content = input_str.split("::", 1)
            return call_mcp_tool("write_file", {"path": path.strip(), "content": content.strip()}, authorization)
        return "Error: Use format 'filename.txt::content here'"

    # Tool 5: DB Query via mcp-service
    def db_query(_: str) -> str:
        result = call_mcp_tool("db_query", {}, authorization)
        return str(result)

    tools = [
        Tool(
            name="PDF_Search",
            func=pdf_search,
            description="Search uploaded PDF documents for information. Use for questions about uploaded files."
        ),
        Tool(
            name="Web_Search",
            func=web_search,
            description="Search the internet for current information, news, facts. Use when PDF has no answer."
        ),
        Tool(
            name="File_Read",
            func=file_read,
            description="Read a file from storage. Input: filename or path."
        ),
        Tool(
            name="File_Write",
            func=file_write,
            description="Write content to a file. Input format: 'filename.txt::content to write'"
        ),
        Tool(
            name="DB_Query",
            func=db_query,
            description="Query the database to see user's uploaded PDFs and metadata."
        ),
    ]

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="output"
    )

    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        memory=memory,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        agent_kwargs={
            "system_message": """You are a highly knowledgeable AI assistant with access to multiple tools:
1. PDF_Search: Search uploaded PDF documents
2. Web_Search: Search the internet for current information
3. File_Read: Read files from storage
4. File_Write: Write files to storage
5. DB_Query: Query database for user PDF metadata

Always try PDF_Search first for document questions. Use Web_Search for current events or when PDFs don't have the answer. Give detailed, comprehensive answers."""
        }
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
    return {"service": "chat-service", "status": "running", "version": "2.0.0"}


@app.post("/ask")
async def ask(
    req: AskRequest,
    authorization: Optional[str] = Header(None)
):
    user = verify_token(authorization)
    question = req.question
    pdf_name = req.pdf_name

    # First try PDF context
    context = fetch_rag_context(question, pdf_name, authorization)

    if context:
        # Answer directly from PDF
        messages = [
            SystemMessage(content="""You are a highly knowledgeable AI assistant.
Answer only using the provided PDF context.
- Give detailed answers with bullet points
- Minimum 5-8 sentences
- Be clear and structured"""),
            HumanMessage(content=f"Context from PDF:\n\n{context}\n\nQuestion:\n\n{question}")
        ]
        response = llm.invoke(messages)
        return {
            "answer": response.content,
            "mode": "pdf",
            "steps": [],
            "sources": []
        }
    else:
        # Use agent with all MCP tools
        agent = build_agent_with_mcp(authorization)
        result = agent.invoke({"input": question})

        steps = result.get("intermediate_steps", [])
        formatted_steps = []
        for step in steps:
            if isinstance(step, tuple):
                action, observation = step
                formatted_steps.append({
                    "tool": str(action.tool) if hasattr(action, "tool") else "",
                    "input": str(action.tool_input) if hasattr(action, "tool_input") else "",
                    "output": str(observation)[:500]
                })

        return {
            "answer": result["output"],
            "mode": "agent+mcp",
            "steps": formatted_steps,
            "sources": []
        }


# =========================
# Run Locally
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True)