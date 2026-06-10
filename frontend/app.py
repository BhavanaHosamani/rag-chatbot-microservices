import streamlit as st
import requests

API_URL = st.secrets.get(
    "API_URL",
    "https://rag-chatbot-96sp.onrender.com"
)

SESSION = requests.Session()

# =========================
# Upload PDF
# =========================

def upload_pdf(file):

    try:

        response = SESSION.post(
            f"{API_URL}/upload",
            files={
                "file": (
                    file.name,
                    file,
                    "application/pdf"
                )
            },
            timeout=300
        )

        if response.status_code == 200:
            return True, response.json()["message"]

        return False, response.text

    except requests.exceptions.ConnectionError:
        return False, "Backend connection failed."

    except Exception as e:
        return False, str(e)

# =========================
# Ask Question
# =========================

def ask_question(question):

    try:

        response = SESSION.post(
            f"{API_URL}/ask",
            json={
                "question": question,
                "chat_history": []
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

        return (
            f"Error: {response.text}",
            [],
            "error",
            []
        )

    except requests.exceptions.ConnectionError:

        return (
            "Could not connect to backend.",
            [],
            "error",
            []
        )

# =========================
# Sidebar
# =========================

def render_sidebar():

    with st.sidebar:

        st.header("Upload Document")

        uploaded_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"]
        )

        if uploaded_file:

            if st.button("Process PDF"):

                with st.spinner("Processing PDF..."):

                    success, message = upload_pdf(uploaded_file)

                    if success:
                        st.success(message)
                        st.session_state["pdf_ready"] = True
                    else:
                        st.error(message)

        if st.session_state.get("pdf_ready"):
            st.success("PDF Ready")
        else:
            st.warning("General Mode")

# =========================
# Render Messages
# =========================

def render_message(msg):

    with st.chat_message(msg["role"]):

        st.markdown(msg["content"])

# =========================
# Handle Chat
# =========================

def handle_input(prompt):

    st.session_state["messages"].append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        with st.spinner("Thinking..."):

            answer, sources, mode, steps = ask_question(prompt)

            st.markdown(answer)

            st.session_state["messages"].append({
                "role": "assistant",
                "content": answer
            })

# =========================
# Main App
# =========================

def main():

    st.set_page_config(
        page_title="RAG Chatbot",
        layout="wide"
    )

    st.title("RAG Chatbot")

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if "pdf_ready" not in st.session_state:
        st.session_state["pdf_ready"] = False

    render_sidebar()

    for msg in st.session_state["messages"]:
        render_message(msg)

    prompt = st.chat_input("Ask anything...")

    if prompt:
        handle_input(prompt)

# =========================
# Run Frontend
# =========================

if __name__ == "__main__":
    main()