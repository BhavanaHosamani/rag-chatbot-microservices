from langchain_core.tools import Tool

vector_store = None

def set_vector_store(store):
    global vector_store
    vector_store = store

def search_pdf(query):

    global vector_store

    if vector_store is None:
        return "No PDF uploaded yet. Please upload and process a PDF first."

    docs = vector_store.similarity_search(query, k=8)

    if not docs:
        return "No relevant content found in the PDF."

    results = []
    for i, doc in enumerate(docs):
        results.append(f"[Section {i+1}]:\n{doc.page_content}")

    return "\n\n".join(results)

pdf_tool = Tool(
    name="PDF_Agent",
    func=search_pdf,
    description="""Use this tool whenever the user asks ANY question about the uploaded PDF document.
    This tool searches through the PDF content and returns relevant sections.
    Always use this tool for questions about: methodology, aims, objectives, introduction, 
    conclusion, results, implementation, literature, hardware, software, or any topic from the document.
    Input should be the user's question or relevant keywords."""
)