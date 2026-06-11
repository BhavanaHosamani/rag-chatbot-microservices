from langchain_core.tools import Tool
from typing import Optional

# =========================
# Multi-PDF Vector Store
# =========================

# Stores one vector store per PDF: { "filename.pdf": <VectorStore> }
pdf_stores: dict = {}


def set_vector_store(pdf_name: str, store):
    """Register a vector store for a specific PDF."""
    global pdf_stores
    pdf_stores[pdf_name] = store


def get_pdf_list() -> list:
    """Return list of all uploaded PDF names."""
    return list(pdf_stores.keys())


def delete_pdf_store(pdf_name: str) -> bool:
    """Remove a PDF's vector store. Returns True if found and deleted."""
    global pdf_stores
    if pdf_name in pdf_stores:
        del pdf_stores[pdf_name]
        return True
    return False


def search_pdf(query: str, pdf_name: Optional[str] = None) -> str:
    """
    Search across a specific PDF or all PDFs.
    - pdf_name=None  → search all uploaded PDFs and combine results
    - pdf_name="x"   → search only that PDF's vector store
    """
    global pdf_stores

    if not pdf_stores:
        return "No PDF uploaded yet. Please upload and process a PDF first."

    if pdf_name and pdf_name not in pdf_stores:
        return "Selected PDF not found. Please re-upload."

    targets = {pdf_name: pdf_stores[pdf_name]} if pdf_name else pdf_stores

    all_results = []
    for name, store in targets.items():
        docs = store.similarity_search(query, k=6)
        if docs:
            if len(targets) > 1:
                all_results.append(f"── From: {name} ──")
            for i, doc in enumerate(docs):
                all_results.append(f"[Section {i+1}]:\n{doc.page_content}")

    if not all_results:
        return "No relevant content found in the PDF."

    return "\n\n".join(all_results)


# =========================
# LangChain Tool
# =========================

def _tool_search(query: str) -> str:
    """Wrapper used by the LangChain agent (searches all PDFs)."""
    return search_pdf(query)


pdf_tool = Tool(
    name="PDF_Agent",
    func=_tool_search,
    description="""Use this tool whenever the user asks ANY question about the uploaded PDF document(s).
    This tool searches through the PDF content and returns relevant sections.
    Always use this tool for questions about: methodology, aims, objectives, introduction,
    conclusion, results, implementation, literature, hardware, software, or any topic from the document.
    Input should be the user's question or relevant keywords."""
)