import os
from supabase import create_client, Client

# =========================
# Supabase Client
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET_NAME = "pdfs"

def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set as environment variables."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# =========================
# Upload PDF
# =========================

def upload_pdf_to_supabase(filename: str, file_bytes: bytes) -> bool:
    """Upload raw PDF bytes to Supabase Storage bucket."""
    try:
        client = get_client()
        # upsert=True so re-uploading same filename overwrites cleanly
        client.storage.from_(BUCKET_NAME).upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"}
        )
        print(f"✅ Uploaded {filename} to Supabase Storage.")
        return True
    except Exception as e:
        print(f"❌ Failed to upload {filename} to Supabase: {e}")
        raise


# =========================
# Download PDF
# =========================

def download_pdf_from_supabase(filename: str, dest_path: str) -> bool:
    """Download a PDF from Supabase Storage and save to dest_path."""
    try:
        client = get_client()
        response = client.storage.from_(BUCKET_NAME).download(filename)
        with open(dest_path, "wb") as f:
            f.write(response)
        print(f"✅ Downloaded {filename} from Supabase Storage.")
        return True
    except Exception as e:
        print(f"❌ Failed to download {filename}: {e}")
        raise


# =========================
# Delete PDF
# =========================

def delete_pdf_from_supabase(filename: str) -> bool:
    """Delete a PDF from Supabase Storage. Returns True if successful."""
    try:
        client = get_client()
        client.storage.from_(BUCKET_NAME).remove([filename])
        print(f"✅ Deleted {filename} from Supabase Storage.")
        return True
    except Exception as e:
        print(f"❌ Failed to delete {filename}: {e}")
        return False


# =========================
# List PDFs
# =========================

def list_pdfs_from_supabase() -> list:
    """Return list of all PDF filenames in the Supabase bucket."""
    try:
        client = get_client()
        files = client.storage.from_(BUCKET_NAME).list()
        # Each item is a dict with 'name', 'id', 'created_at', etc.
        names = [f["name"] for f in files if f["name"].endswith(".pdf")]
        return names
    except Exception as e:
        print(f"❌ Failed to list PDFs from Supabase: {e}")
        return []