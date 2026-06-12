from fastapi import FastAPI

app = FastAPI(title="Auth PDF Service")

@app.get("/")
def root():
    return {"service": "auth-pdf-service", "status": "running"}