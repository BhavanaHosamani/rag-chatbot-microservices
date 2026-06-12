import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase import create_client

# =========================
# Config
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

app = FastAPI(title="Auth Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Helpers
# =========================

def anon_client():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def service_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# =========================
# Models
# =========================

class AuthRequest(BaseModel):
    email: str
    password: str

# =========================
# Endpoints
# =========================

@app.get("/")
async def home():
    return {"service": "auth-service", "status": "running"}


@app.post("/signup")
async def signup(req: AuthRequest):
    try:
        client = anon_client()
        res = client.auth.sign_up({"email": req.email, "password": req.password})
        if res.user is None:
            raise ValueError("Sign up failed.")
        return {
            "message": "Account created successfully!",
            "user_id": res.user.id,
            "email": res.user.email,
            "access_token": res.session.access_token if res.session else None,
            "refresh_token": res.session.refresh_token if res.session else None,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/login")
async def login(req: AuthRequest):
    try:
        client = anon_client()
        res = client.auth.sign_in_with_password({"email": req.email, "password": req.password})
        if res.user is None:
            raise ValueError("Invalid email or password.")
        return {
            "message": "Login successful!",
            "user_id": res.user.id,
            "email": res.user.email,
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    try:
        client = anon_client()
        client.auth.sign_out()
        return {"message": "Logged out successfully."}
    except Exception:
        return {"message": "Logged out."}


@app.get("/verify")
async def verify(authorization: Optional[str] = Header(None)):
    """Verify JWT token — called by other services to validate users."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header.")
    token = authorization.replace("Bearer ", "").strip()
    try:
        client = anon_client()
        res = client.auth.get_user(token)
        if res.user is None:
            raise ValueError("Invalid token.")
        return {"user_id": res.user.id, "email": res.user.email}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


# =========================
# Run Locally
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)