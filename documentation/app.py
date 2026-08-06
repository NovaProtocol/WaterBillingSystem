import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env('SECRET_KEY', 'DEPLOYMENT_TYPE')

SITE_DIR = Path(__file__).resolve().parent / "site"

app = FastAPI(title="Cotta Water Billing Docs")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def index():
    return FileResponse(SITE_DIR / "index.html")


@app.get("/{path:path}")
async def serve_docs(path: str):
    if not path:
        return FileResponse(SITE_DIR / "index.html")
    parts = path.rstrip("/")
    candidates = [
        SITE_DIR / parts,
        SITE_DIR / parts / "index.html",
        SITE_DIR / (parts + ".html"),
    ]
    for c in candidates:
        if c.is_file():
            return FileResponse(c)
    return JSONResponse({"error": "Not found"}, status_code=404)
