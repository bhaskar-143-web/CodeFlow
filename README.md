# CodeFlow

CodeFlow turns supported Python statements into a visual, step-by-step trace.

## Run locally

Requirements: Node.js 18 or newer and Python 3.10 or newer.

In the first VS Code terminal, prepare the backend environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

In a second VS Code terminal, install the web dependencies:

```powershell
npm install
```

## Google login setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create an OAuth client ID for a **Web application** and add `http://localhost` and `http://localhost:5173` as authorized JavaScript origins. Add the deployed frontend origin there when hosting. See Google's [Sign in with Google setup](https://developers.google.com/identity/gsi/web/guides/overview).
2. The ignored local `.env` file contains the client ID and a random session secret. Start the backend with:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --reload --env-file .env
   ```
3. The ignored `.env.local` file already provides the same client ID to Vite. Restart Vite:

   ```powershell
   npm run dev
   ```

The API verifies Google's ID token using Google's official verifier before creating a signed, one-year session cookie. Google recommends backend validation; see [its backend authentication guide](https://developers.google.com/identity/sign-in/web/backend-auth). The login remains active across reloads and browser restarts; **Log out** clears the session and returns to the Google account chooser. Signing out also clears the saved editor workspace on this device. Never commit the session secret. For HTTPS hosting, set `CODEFLOW_ENV=production`, `CODEFLOW_COOKIE_SECURE=true`, and a strong `CODEFLOW_SESSION_SECRET`; configure the frontend origin in `CODEFLOW_ALLOWED_ORIGINS`. If the frontend and API use different sites, also set `CODEFLOW_COOKIE_SAMESITE=none`.
## Hosting configuration

For a hosted frontend, set `VITE_API_BASE_URL` to the deployed API origin before building (for example, `https://api.example.com`). For the API service, set `CODEFLOW_ALLOWED_ORIGINS` to a comma-separated list of frontend origins. Keep the local defaults for development. The browser sends traces to this API; submitted programs are interpreted by the restricted tracer.

## Supported Python subset

The visual tracer currently supports:

- Variable assignments and augmented assignments such as `total += num`
- Numbers, text, booleans, and `None`; `input()` with one supplied value per line and conversions using `int()`, `float()`, `str()`, and `bool()`
- Text joining, basic f-strings, indexing and slicing, `len(...)`, membership checks, and the `upper()`, `lower()`, `strip()`, and `replace()` tools
- Simple top-level functions with positional parameters, calls, `return`, and bounded recursion with a visible call stack; simple classes with `__init__`, attributes, and methods
- Lists with indexing, slicing, `count()`, `index()`, `append()`, `insert()`, `remove()`, and `pop()`, tuples, sets, dictionaries with text keys, `get()`, `keys()`, `values()`, `items()`, collection indexing, and `range(...)` with one to three arguments
- `for` loops over lists, tuples, dictionaries, sets, text, and ranges; `enumerate()`, `zip()`, tuple unpacking, and one-generator filtered list comprehensions; `while` loops (up to 40 turns), plus `break` and `continue`
- `try/except/else/finally` for common runtime errors (`ZeroDivisionError`, `ValueError`, `TypeError`, `IndexError`, and `KeyError`)
- Comparisons and Boolean logic: equality, chained ranges, membership, plus `and`, `or`, and `not`.
- `if/else` branches with comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`) and boolean logic (`and`, `or`, `not`)
- Numeric arithmetic: `+`, `-`, `*`, `/`, `//`, `%`, and `**`; helpers `sum()`, `min()`, `max()`, `abs()`, `round()`, and `sorted()`
- Set creation, membership, `add()`, `discard()`, and iteration
- `print(...)`, including `sep` and `end` options
- A safe subset of `math` and `statistics`, including `sqrt`, `floor`, `ceil`, `mean`, and `median`
- In-memory text files with `with open(...)`, `read()`, and `write()`; no device files are opened
- One simple identity decorator, bounded generator lessons, and sequential `async`/`await` visual examples
- Set intersection with `&`

The tracer uses an AST interpreter and never calls `exec` or `eval` on submitted code. Advanced lessons remain intentionally bounded: `math` and `statistics` expose a small allowlist; `asyncio` models one sequential coroutine without real waits or concurrency; decorators are limited to one simple identity decorator; generators show a bounded, pre-collected sequence of yielded values (full lazy suspension is not modeled); and file operations run against in-memory files only. Imports outside the allowlist, real filesystem or network access, inheritance, and manually raised exceptions are not interpreted. Unsupported syntax is reported in the app.

Limits: 20,000 source characters, 200 interpreted statements, 40 collection or loop items, 600 trace events, and 8,000 output characters.

## Deploy to Render

The root `render.yaml` defines a free Python API service and a free Vite static site. Create both from the GitHub repository using the Blueprint flow. Set `GOOGLE_CLIENT_ID` for the API and `VITE_GOOGLE_CLIENT_ID` for the web service to the same Web OAuth client ID. After the first deploy, add `https://codeflow-bhaskar-web.onrender.com` as an authorized JavaScript origin in Google Cloud Console; this sign-in flow does not use a redirect URI. The Blueprint generates a session secret and enables secure cross-site cookies.

The API may spin down when idle on Render's free plan. CodeFlow remains a restricted teaching tracer, not a full Python runtime.
