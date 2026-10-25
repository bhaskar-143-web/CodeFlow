from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from .tracer import trace_code
except ImportError:
    from tracer import trace_code

app = FastAPI(title="CodeFlow Python Trace API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip().rstrip("/") for origin in os.getenv("CODEFLOW_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class TraceRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20_000)
    inputs: list[str] = Field(default_factory=list, max_length=40)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codeflow-python-tracer"}


@app.post("/api/trace")
def trace_program(request: TraceRequest) -> dict:
    """Trace the supported Python subset with the restricted AST interpreter."""
    return trace_code(request.code, request.inputs)
