# CodeFlow

CodeFlow turns supported Python statements into a visual, step-by-step trace.

## Run locally

Requirements: Node.js 18 or newer and Python 3.10 or newer.

In the first VS Code terminal, create the environment, install backend dependencies, and start the trace API:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --reload
```

In a second VS Code terminal, start the web app:

```powershell
npm install
npm run dev
```


Open the local URL printed by Vite (usually http://localhost:5173).

To check the production build, run `npm run build`. This also checks the TypeScript types.

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

Unsupported syntax is reported in the app. Inheritance, decorators, imports, file and network access, and manually raised exceptions are not interpreted yet. The tracer parses Python into an AST and interprets only supported nodes; it does not call `exec` or `eval` on submitted code.

Limits: 20,000 source characters, 200 interpreted statements, 40 collection or loop items, 600 trace events, and 8,000 output characters.

## Later runtime milestone

This restricted tracer is for learning examples, not full Python compatibility. Keep the Docker sandbox in `backend/sandbox` for a later isolated runtime milestone.
