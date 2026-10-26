from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from starlette.middleware.sessions import SessionMiddleware

try:
    from .tracer import trace_code
except ImportError:
    from tracer import trace_code

app = FastAPI(title="CodeFlow Python Trace API", version="0.2.0")
session_secret = os.getenv("CODEFLOW_SESSION_SECRET", "").strip()
if not session_secret and (os.getenv("CODEFLOW_ENV") == "production" or os.getenv("CODEFLOW_COOKIE_SECURE", "false").lower() == "true"):
    raise RuntimeError("Set CODEFLOW_SESSION_SECRET to a long random value in production.")
session_secret = session_secret or "codeflow-local-session-secret-change-before-deploy"
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    session_cookie="codeflow_session",
    max_age=60 * 60 * 24 * 365,
    same_site=os.getenv("CODEFLOW_COOKIE_SAMESITE", "lax"),
    https_only=os.getenv("CODEFLOW_COOKIE_SECURE", "false").lower() == "true",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip().rstrip("/") for origin in os.getenv("CODEFLOW_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)


class TraceRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20_000)
    inputs: list[str] = Field(default_factory=list, max_length=40)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codeflow-python-tracer"}


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=5_000)


@app.post("/api/auth/google")
def login_with_google(payload: GoogleLoginRequest, request: Request) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google login is not configured on the server yet.")
    try:
        claims = id_token.verify_oauth2_token(payload.credential, GoogleRequest(), client_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Google could not verify this sign-in. Please try again.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Google sign-in could not be reached. Please try again.") from exc
    subject = claims.get("sub")
    email = claims.get("email")
    if not subject or not email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google did not return a verified account.")
    user = {
        "id": subject,
        "email": email,
        "name": claims.get("name") or email,
        "picture": claims.get("picture"),
    }
    request.session["user"] = user
    return {"user": user}


@app.get("/api/auth/session")
def current_session(request: Request) -> dict:
    return {"user": request.session.get("user")}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "signed_out"}


@app.post("/api/trace")
def trace_program(trace_request: TraceRequest, request: Request) -> dict:
    """Trace code only for a signed-in learner."""
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Sign in to run a trace.")
    return trace_code(trace_request.code, trace_request.inputs)
