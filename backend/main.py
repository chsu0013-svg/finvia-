"""Finvia API + static frontend, served from a single container.

Only the ``frontend/`` folder is exposed as static files. Source code, the
Dockerfile and uploaded documents are never served.
"""
import os
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from analysis import analyse_upload, build_demo_dashboard, build_tax_report, new_state

VERSION = "1.2.0"
BASE = Path(__file__).resolve().parent
FRONTEND = Path(os.getenv("FRONTEND_DIR", BASE.parent / "frontend"))
UPLOADS = Path(os.getenv("UPLOAD_DIR", BASE.parent / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXT = {".csv", ".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg"}

# Same-origin by default (frontend and API share one server). Only set
# ALLOWED_ORIGINS if the frontend is hosted on a different domain.
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()] or ["*"]

# ---------- Per-visitor workspace (in memory) ----------
# Each browser gets its own workspace via an HttpOnly cookie, so one visitor's
# uploaded statement is never shown to another. Capped so memory cannot grow
# without bound. Replace with a database before handling real SME data.
SESSION_COOKIE = "finvia_sid"
SESSION_MAX = 500
_sessions: "OrderedDict[str, dict]" = OrderedDict()


def workspace(request: Request, response: Response) -> dict:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid or sid not in _sessions:
        sid = uuid.uuid4().hex
        _sessions[sid] = new_state()
        while len(_sessions) > SESSION_MAX:
            _sessions.popitem(last=False)
        response.set_cookie(
            SESSION_COOKIE,
            sid,
            max_age=60 * 60 * 24 * 7,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    else:
        _sessions.move_to_end(sid)
    return _sessions[sid]


# ---------- Security headers ----------
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", CSP)
        path = request.url.path
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif path in ("/", "/index.html", "/service-worker.js", "/manifest.webmanifest"):
            # Always revalidate the shell so a new deploy shows up immediately.
            response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Finvia API", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeaders)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- Health ----------
@app.get("/health")
def health():
    return {"status": "ok", "service": "finvia", "version": VERSION}


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "finvia-api", "version": VERSION}


# ---------- API ----------
@app.get("/api/dashboard")
def dashboard(state: dict = Depends(workspace)):
    return build_demo_dashboard(state)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), state: dict = Depends(workspace)):
    if not file.filename:
        raise HTTPException(400, "Missing filename.")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Unsupported file type.")

    target = UPLOADS / f"{uuid.uuid4().hex}{ext}"
    written = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"File is too large. Maximum is {MAX_UPLOAD_MB} MB.")
                out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise

    result = analyse_upload(target, file.filename, state)
    return {"message": result["message"], "dashboard": result["dashboard"]}


@app.get("/api/tax-report")
def tax_report(state: dict = Depends(workspace)):
    return build_tax_report(state)


class Referral(BaseModel):
    consent: bool


@app.post("/api/referral")
def referral(payload: Referral):
    if not payload.consent:
        raise HTTPException(400, "Consent is required.")
    return {
        "status": "submitted",
        "message": "Your referral request has been recorded. A participating bank will make the final financing decision. Finvia does not approve loans.",
    }


# ---------- Frontend (must be mounted last) ----------
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
