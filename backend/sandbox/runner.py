from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback

MAX_EVENTS = 600
MAX_ITEMS = 40


def safe_value(value, depth=0):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value[:500] if isinstance(value, str) else value
    if depth >= 3:
        return f"<{type(value).__name__}>"
    if isinstance(value, (list, tuple)):
        items = [safe_value(item, depth + 1) for item in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            items.append("…")
        return items
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_ITEMS:
                result["…"] = "more items"
                break
            result[str(key)[:80]] = safe_value(item, depth + 1)
        return result
    return f"<{type(value).__name__}>"


def main():
    source = sys.stdin.read(20_001)
    if len(source) > 20_000:
        print(json.dumps({"events": [], "output": "", "error": "Code is limited to 20,000 characters."}))
        return

    output = io.StringIO()
    events = []
    previous_by_frame = {}
    namespace = {"__name__": "__main__"}

    def snapshot(frame):
        return {
            key: safe_value(value)
            for key, value in frame.f_locals.items()
            if not key.startswith("__") and not callable(value)
        }

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != "<codeflow>" or len(events) >= MAX_EVENTS:
            return tracer
        if event not in {"line", "call", "return", "exception"}:
            return tracer

        frame_id = id(frame)
        state = snapshot(frame)
        previous = previous_by_frame.get(frame_id, {})
        changes = []
        for name, value in state.items():
            old = previous.get(name)
            if name not in previous or old != value:
                changes.append({"name": name, "before": old, "after": value})
        previous_by_frame[frame_id] = state

        item = {
            "type": event,
            "line": frame.f_lineno,
            "function": frame.f_code.co_name,
            "changes": changes[:12],
            "state": state,
            "output": output.getvalue(),
        }
        if event == "exception":
            item["error"] = f"{arg[0].__name__}: {arg[1]}"
        events.append(item)
        return tracer

    error = None
    try:
        compiled = compile(source, "<codeflow>", "exec")
        with contextlib.redirect_stdout(output):
            sys.settrace(tracer)
            exec(compiled, namespace, namespace)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        if len(events) < MAX_EVENTS:
            events.append({
                "type": "exception", "line": getattr(exc.__traceback__, "tb_lineno", None),
                "function": "<module>", "changes": [], "state": {}, "output": output.getvalue(), "error": error,
            })
    finally:
        sys.settrace(None)

    print(json.dumps({"events": events, "output": output.getvalue(), "error": error}, ensure_ascii=False))


if __name__ == "__main__":
    main()
