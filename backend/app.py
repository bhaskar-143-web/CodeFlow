from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="CodeFlow Runtime API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class TraceRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20_000)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codeflow-runtime"}


@app.post("/api/trace")
def trace_program(request: TraceRequest) -> dict:
    """Run code only inside the separately built, network-isolated Docker image."""
    container_name = f"codeflow-run-{uuid.uuid4().hex[:12]}"
    command = [
        "docker", "run", "--rm", "-i", "--name", container_name,
        "--network=none", "--memory=128m", "--cpus=0.5", "--pids-limit=64",
        "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=8m",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
        "--env", "PYTHONDONTWRITEBYTECODE=1", "codeflow-sandbox",
    ]
    try:
        completed = subprocess.run(
            command,
            input=request.code,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=7,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Docker was not found. Install and start Docker, then build the sandbox image from backend/sandbox.") from exc
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=3, check=False)
        return {"events": [], "output": "", "error": "Execution stopped: the 5-second time limit was reached.", "timed_out": True}

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "The sandbox container could not start. Build the codeflow-sandbox image first."
        raise HTTPException(status_code=503, detail=detail[-1200:])
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="The sandbox returned an invalid trace response.") from exc
    return result
