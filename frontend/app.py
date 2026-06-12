import streamlit as st
import requests

# =========================
# Service URLs
# Change these to your Render URLs when deployed
# =========================

AUTH_SERVICE_URL = "http://localhost:8001"
PDF_SERVICE_URL  = "http://localhost:8002"
RAG_SERVICE_URL  = "http://localhost:8003"
CHAT_SERVICE_URL = "http://localhost:8004"

SESSION = requests.Session()

# =========================
# Auth Helpers
# =========================

def api_signup(email: str, password: str):
    try:
        r = SESSION.post(f"{AUTH_SERVICE_URL}/signup",
                         json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            return True, r.json()
        return False, r.json().get("detail", r.text)
    except Exception as e:
        return False, str(e)


def api_login(email: str, password: str):
    try:
        r = SESSION.post(f"{AUTH_SERVICE_URL}/login",
                         json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            return True, r.json()
        return False, r.json().get("detail", r.text)
    except Exception as e:
        return False, str(e)


def api_logout():
    try:
        SESSION.post(f"{AUTH_SERVICE_URL}/logout",
                     headers=auth_headers(), timeout=10)
    except Exception:
        pass


def auth_headers():
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}

# =========================
# PDF Helpers
# =========================

def upload_pdf(file):
    try:
        r = SESSION.post(
            f"{PDF_SERVICE_URL}/upload",
            files={"file": (file.name, file, "application/pdf")},
            headers=auth_headers(),
            timeout=300
        )
        if r.status_code == 200:
            # After upload, tell rag-service to index it
            index_pdf(file.name)
            return True, r.json()["message"]
        return False, r.json().get("detail", r.text)
    except Exception as e:
        return False, str(e)


def fetch_pdf_list():
    try:
        r = SESSION.get(f"{PDF_SERVICE_URL}/pdfs",
                        headers=auth_headers(), timeout=30)
        if r.status_code == 200:
            return r.json().get("pdfs", [])
        return []
    except Exception:
        return []


def delete_pdf(pdf_name: str):
    try:
        r = SESSION.delete(f"{PDF_SERVICE_URL}/pdfs/{pdf_name}",
                           headers=auth_headers(), timeout=30)
        if r.status_code == 200:
            # Also remove from rag-service index
            SESSION.delete(f"{RAG_SERVICE_URL}/index/{pdf_name}",
                           headers=auth_headers(), timeout=10)
            return True, r.json()["message"]
        return False, r.json().get("detail", r.text)
    except Exception as e:
        return False, str(e)

# =========================
# RAG Helpers
# =========================

def index_pdf(pdf_name: str):
    """Tell rag-service to index the just-uploaded PDF."""
    try:
        SESSION.post(
            f"{RAG_SERVICE_URL}/index",
            json={"pdf_name": pdf_name},
            headers=auth_headers(),
            timeout=120
        )
    except Exception:
        pass  # Best effort — rag-service will re-index on demand

# =========================
# Chat Helper
# =========================

def ask_question(question: str, pdf_name: str = None):
    try:
        r = SESSION.post(
            f"{CHAT_SERVICE_URL}/ask",
            json={"question": question, "chat_history": [], "pdf_name": pdf_name},
            headers=auth_headers(),
            timeout=120
        )
        if r.status_code == 200:
            data = r.json()
            return (data.get("answer", ""),
                    data.get("sources", []),
                    data.get("mode", "agent"),
                    data.get("steps", []))
        return (f"Error: {r.text}", [], "error", [])
    except requests.exceptions.ConnectionError:
        return ("Could not connect to chat service.", [], "error", [])

# =========================
# Auth Page
# =========================

def render_auth_page():
    st.set_page_config(page_title="RAG Chatbot — Login", layout="centered")
    st.title("🤖 RAG Chatbot")
    st.subheader("Your personal AI PDF assistant")
    st.divider()

    tab_login, tab_signup = st.tabs(["🔐 Login", "📝 Sign Up"])

    with tab_login:
        st.subheader("Welcome back!")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login", use_container_width=True, type="primary"):
            if not email or not password:
                st.error("Please enter email and password.")
            else:
                with st.spinner("Logging in..."):
                    success, data = api_login(email, password)
                    if success:
                        st.session_state["access_token"] = data["access_token"]
                        st.session_state["user_email"]   = data["email"]
                        st.session_state["user_id"]      = data["user_id"]
                        st.session_state["logged_in"]    = True
                        st.session_state["messages"]     = []
                        st.session_state["pdf_list"]     = []
                        st.success("Logged in successfully!")
                        st.rerun()
                    else:
                        st.error(f"Login failed: {data}")

    with tab_signup:
        st.subheader("Create your account")
        new_email    = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password (min 6 chars)", type="password", key="signup_password")
        confirm_pass = st.text_input("Confirm Password", type="password", key="confirm_password")

        if st.button("Create Account", use_container_width=True, type="primary"):
            if not new_email or not new_password:
                st.error("Please fill in all fields.")
            elif new_password != confirm_pass:
                st.error("Passwords do not match.")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with st.spinner("Creating account..."):
                    success, data = api_signup(new_email, new_password)
                    if success:
                        st.success("Account created! Please login.")
                    else:
                        st.error(f"Sign up failed: {data}")

# =========================
# Sidebar
# =========================

def render_sidebar():
    with st.sidebar:
        st.header("📂 PDF Manager")

        # User info + logout
        st.caption(f"👤 {st.session_state.get('user_email', '')}")
        if st.button("🚪 Logout", use_container_width=True):
            api_logout()
            for key in ["logged_in", "access_token", "user_email",
                        "user_id", "messages", "pdf_list", "selected_pdf"]:
                st.session_state.pop(key, None)
            st.rerun()

        st.divider()

        # Upload
        st.subheader("Upload a PDF")
        uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
        if uploaded_file:
            if st.button("⬆️ Upload & Process"):
                with st.spinner(f"Uploading {uploaded_file.name}..."):
                    success, message = upload_pdf(uploaded_file)
                    if success:
                        st.success(message)
                        st.session_state["pdf_list"] = fetch_pdf_list()
                    else:
                        st.error(message)

        st.divider()

        if st.button("🔄 Refresh PDF List"):
            st.session_state["pdf_list"] = fetch_pdf_list()

        st.subheader("Your PDFs")
        if "pdf_list" not in st.session_state:
            st.session_state["pdf_list"] = fetch_pdf_list()

        pdf_list = st.session_state["pdf_list"]

        if not pdf_list:
            st.info("No PDFs uploaded yet.")
            st.session_state["selected_pdf"] = None
        else:
            options   = ["🔍 All PDFs"] + pdf_list
            selection = st.radio("Query from:", options, index=0, key="pdf_radio")
            st.session_state["selected_pdf"] = (
                None if selection == "🔍 All PDFs" else selection
            )

            st.divider()
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
        st.caption("☁️ Supabase Storage  |  🔐 Auth  |  🧩 Microservices")

        selected = st.session_state.get("selected_pdf")
        if pdf_list:
            if selected:
                st.success(f"📄 Active: {selected}")
            else:
                st.success(f"📚 Querying all {len(pdf_list)} PDF(s)")
        else:
            st.warning("⚡ General Mode (no PDFs)")

# =========================
# Chat Page
# =========================

def render_chat_page():
    st.set_page_config(page_title="RAG Chatbot", layout="wide")
    st.title("🤖 RAG Chatbot")

    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "selected_pdf" not in st.session_state:
        st.session_state["selected_pdf"] = None

    render_sidebar()

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask anything...")
    if prompt:
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
                    st.caption(f"Source: {label} · 🧩 rag-service · ☁️ Supabase")
                else:
                    st.caption("⚡ General knowledge · 🧩 chat-service")
                st.session_state["messages"].append({"role": "assistant", "content": answer})

# =========================
# Main
# =========================

def main():
    if not st.session_state.get("logged_in"):
        render_auth_page()
    else:
        render_chat_page()

if __name__ == "__main__":
    main()