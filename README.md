# CodeFlow

A first visual preview of CodeFlow: a cinematic, step-by-step replay of a built-in Python loop sample.

## Current preview mode

This version uses fixed, hand-authored sample events. It does **not** execute the text in the editor, and it does not need Docker or the Python backend to show the replay. If you edit the code, restore the original sample before playing the preview.

## Run the web preview

Requirements: Node.js 18 or newer.

```powershell
npm install
npm run dev
```

Open the local URL printed by Vite (usually http://localhost:5173).

## Next runtime milestone

The FastAPI backend and isolated Python runner are being kept for the later live-execution milestone. That milestone needs a working isolation environment (Docker with WSL 2, or another sandbox). Do not enable direct host execution of arbitrary submitted Python code.
