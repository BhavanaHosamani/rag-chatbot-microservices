import os
from typing import List, Dict
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def get_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def query_user_pdfs(user_id: str) -> List[Dict]:
    """Get all PDFs belonging to a user from Supabase."""
    try:
        client = get_client()
        response = (
            client.table("user_pdfs")
            .select("pdf_name, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        return [{"error": str(e)}]


def get_pdf_count(user_id: str) -> Dict:
    """Get total PDF count for a user."""
    try:
        client = get_client()
        response = (
            client.table("user_pdfs")
            .select("pdf_name", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        return {
            "user_id": user_id,
            "total_pdfs": response.count or 0,
            "pdfs": [row["pdf_name"] for row in (response.data or [])]
        }
    except Exception as e:
        return {"error": str(e)}


def search_pdf_records(user_id: str, keyword: str) -> List[Dict]:
    """Search PDFs by name keyword for a user."""
    try:
        client = get_client()
        response = (
            client.table("user_pdfs")
            .select("pdf_name, created_at")
            .eq("user_id", user_id)
            .ilike("pdf_name", f"%{keyword}%")
            .execute()
        )
        return response.data or []
    except Exception as e:
        return [{"error": str(e)}]