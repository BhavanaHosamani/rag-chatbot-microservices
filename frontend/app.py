import streamlit as st
import requests

API_URL = "https://rag-chatbot-96sp.onrender.com"

SESSION = requests.Session()

# =========================
# API Helpers
# =========================

def upload_pdf(file):
    try:
        response = SESSION.post(
            f"{API_URL}/upload",
            files={"file": (file.name, file, "application/pdf")},
            timeout=300
        )
        if response.status_code == 200:
            return True, response.json()["message"]
        return False, response.text
    except requests.exceptions.ConnectionError:
        return False, "Backend connection failed."
    except Exception as e:
        return False, str(e)


def fetch_pdf_list():
    try:
        response = SESSION.get(f"{API_URL}/pdfs", timeout=30)
        if response.status_code == 200:
            return response.json().get("pdfs", [])
        return []
    except Exception:
        return []


def delete_pdf(pdf_name: str):
    try:
        response = SESSION.delete(f"{API_URL}/pdfs/{pdf_name}", timeout=30)
        if response.status_code == 200:
            return True, response.json()["message"]
        return False, response.text
    except Exception as e:
        return False, str(e)


def ask_question(question: str, pdf_name: str = None):
    try:
        response = SESSION.post(
            f"{API_URL}/ask",
            json={
                "question": question,
                "chat_history": [],
                "pdf_name": pdf_name
            },
            timeout=120
        )
        if response.status_code == 200:
            data = response.json()
            return (
                data.get("answer", ""),
                data.get("sources", []),
                data.get("mode", "agent"),
                data.get("steps", [])
            )
        return (f"Error: {response.text}", [], "error", [])
    except requests.exceptions.ConnectionError:
        return ("Could not connect to backend.", [], "error", [])

# =========================
# Sidebar
# =========================

def render_sidebar():
    with st.sidebar:
        st.header("📂 PDF Manager")

        # ── Upload ──────────────────────────────
        st.subheader("Upload a PDF")
        uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

        if uploaded_file:
            if st.button("⬆️ Upload & Process"):
                with st.spinner(f"Uploading {uploaded_file.name} to Supabase..."):
                    success, message = upload_pdf(uploaded_file)
                    if success:
                        st.success(message)
                        st.session_state["pdf_list"] = fetch_pdf_list()
                    else:
                        st.error(message)

        st.divider()

        # ── Refresh button ───────────────────────
        if st.button("🔄 Refresh PDF List"):
            st.session_state["pdf_list"] = fetch_pdf_list()

        # ── Manage uploaded PDFs ─────────────────
        st.subheader("Your PDFs")

        if "pdf_list" not in st.session_state:
            st.session_state["pdf_list"] = fetch_pdf_list()

        pdf_list = st.session_state["pdf_list"]

        if not pdf_list:
            st.info("No PDFs uploaded yet.")
            st.session_state["selected_pdf"] = None
        else:
            options = ["🔍 All PDFs"] + pdf_list
            selection = st.radio(
                "Query from:",
                options,
                index=0,
                key="pdf_radio"
            )
            st.session_state["selected_pdf"] = (
                None if selection == "🔍 All PDFs" else selection
            )

            st.divider()

            # Delete buttons
            st.subheader("🗑️ Delete a PDF")
            for pdf_name in pdf_list:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text(pdf_name)
                with col2:
                    if st.button("✕", key=f"del_{pdf_name}"):
                        with st.spinner(f"Deleting {pdf_name}..."):
                            success, msg = delete_pdf(pdf_name)
                            if success:
                                st.success(msg)
                                st.session_state["pdf_list"] = fetch_pdf_list()
                                if st.session_state.get("selected_pdf") == pdf_name:
                                    st.session_state["selected_pdf"] = None
                                st.rerun()
                            else:
                                st.error(msg)

        st.divider()

        # ── Storage badge ────────────────────────
        st.caption("☁️ PDFs stored in Supabase Storage")

        selected = st.session_state.get("selected_pdf")
        if pdf_list:
            if selected:
                st.success(f"📄 Active: {selected}")
            else:
                st.success(f"📚 Querying all {len(pdf_list)} PDF(s)")
        else:
            st.warning("⚡ General Mode (no PDFs)")

# =========================
# Render Messages
# =========================

def render_message(msg):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# =========================
# Handle Chat Input
# =========================

def handle_input(prompt):
    st.session_state["messages"].append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            selected_pdf = st.session_state.get("selected_pdf")
            answer, sources, mode, steps = ask_question(prompt, pdf_name=selected_pdf)
            st.markdown(answer)

            if mode == "pdf":
                label = f"📄 {selected_pdf}" if selected_pdf else "📚 All PDFs"
                st.caption(f"Source: {label} · ☁️ Supabase Storage")
            else:
                st.caption("⚡ General knowledge")

            st.session_state["messages"].append({
                "role": "assistant",
                "content": answer
            })

# =========================
# Main App
# =========================

def main():
    st.set_page_config(page_title="RAG Chatbot", layout="wide")
    st.title("🤖 RAG Chatbot")

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if "selected_pdf" not in st.session_state:
        st.session_state["selected_pdf"] = None

    render_sidebar()

    for msg in st.session_state["messages"]:
        render_message(msg)

    prompt = st.chat_input("Ask anything...")
    if prompt:
        handle_input(prompt)

if __name__ == "__main__":
    main()