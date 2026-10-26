from __future__ import annotations

import ast
import math
import operator
from typing import Any

MAX_SOURCE_NODES = 5_000
MAX_EVENTS = 600
MAX_STEPS = 200
MAX_LOOP_ITEMS = 40
MAX_FUNCTION_DEPTH = 8
MAX_COLLECTION_ITEMS = 40
MAX_STRING_LENGTH = 500
MAX_OUTPUT_LENGTH = 8_000
MAX_INTEGER = 10**12


class TraceProblem(Exception):
    pass


class _PythonRaised(Exception):
    def __init__(self, name: str, message: str) -> None:
        self.name = name
        self.message = message
        super().__init__(message)


class _ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


_MISSING = object()


class _SafeInstance:
    def __init__(self, class_name: str, methods: dict[str, ast.FunctionDef]) -> None:
        self.class_name = class_name
        self.methods = methods
        self.attributes: dict[str, Any] = {}


class _SafeModule:
    def __init__(self, name: str) -> None:
        self.name = name


class _VirtualFile:
    def __init__(self, name: str, mode: str, files: dict[str, str]) -> None:
        self.name = name
        self.mode = mode
        self.files = files
        self.closed = False


class SafePythonTracer:
    """Interpret a small Python teaching subset without eval() or exec()."""

    def __init__(self, inputs: list[str] | None = None) -> None:
        self.values: dict[str, Any] = {}
        self.input_values = inputs or []
        self.input_index = 0
        self.events: list[dict[str, Any]] = []
        self.output = ""
        self.steps = 0
        self.functions: dict[str, ast.FunctionDef] = {}
        self.classes: dict[str, dict[str, ast.FunctionDef]] = {}
        self.call_stack: list[str] = []
        self.loop_depth = 0
        self.virtual_files: dict[str, str] = {}
        self.async_functions: set[str] = set()
        self.generator_functions: set[str] = set()
        self.generator_capture: list[Any] | None = None

    def safe_value(self, value: Any, seen: set[int] | None = None) -> Any:
        if seen is None:
            seen = set()
        if value is None or isinstance(value, (bool, str)):
            if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
                raise TraceProblem(f"Text values are limited to {MAX_STRING_LENGTH} characters.")
            return value
        if isinstance(value, int):
            if abs(value) > MAX_INTEGER:
                raise TraceProblem("Numbers are limited to values between -1 trillion and 1 trillion.")
            return value
        if isinstance(value, float):
            if not math.isfinite(value) or abs(value) > MAX_INTEGER:
                raise TraceProblem("This number is too large to visualize.")
            return value
        if isinstance(value, _SafeModule):
            return {"module": value.name}
        if isinstance(value, _VirtualFile):
            return {"file": value.name, "mode": value.mode, "closed": value.closed}
        if isinstance(value, _SafeInstance):
            identity = id(value)
            if identity in seen:
                raise TraceProblem("An object cannot contain itself as an attribute.")
            seen.add(identity)
            try:
                return {"__class__": value.class_name, **{name: self.safe_value(item, seen) for name, item in value.attributes.items()}}
            finally:
                seen.remove(identity)
        if isinstance(value, set):
            if len(value) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            return [self.safe_value(item, seen) for item in self.sorted_set_values(value)]
        if isinstance(value, (list, tuple, dict)):
            if len(value) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            identity = id(value)
            if identity in seen:
                raise TraceProblem("A collection cannot contain itself.")
            seen.add(identity)
            try:
                if isinstance(value, dict):
                    if any(not isinstance(key, str) for key in value):
                        raise TraceProblem("Dictionary keys must be text.")
                    return {key: self.safe_value(item, seen) for key, item in value.items()}
                return [self.safe_value(item, seen) for item in value]
            finally:
                seen.remove(identity)
        raise TraceProblem("This value type is not supported in the visualizer.")

    def snapshot(self) -> dict[str, Any]:
        return {name: self.safe_value(value) for name, value in self.values.items()}

    def emit(
        self,
        kind: str,
        node: ast.AST,
        narration: str,
        changes: list[dict[str, Any]] | None = None,
        focus: dict[str, Any] | None = None,
    ) -> None:
        if len(self.events) >= MAX_EVENTS:
            raise TraceProblem(f"Trace is limited to {MAX_EVENTS} events.")
        event: dict[str, Any] = {
            "type": kind,
            "line": getattr(node, "lineno", None),
            "function": self.call_stack[-1] if self.call_stack else "<module>",
            "callStack": list(self.call_stack),
            "changes": changes or [],
            "state": self.snapshot(),
            "valueTypes": {name: "object" if isinstance(value, _SafeInstance) else "set" if isinstance(value, set) else "tuple" if isinstance(value, tuple) else "list" if isinstance(value, list) else "dictionary" if isinstance(value, dict) else type(value).__name__ for name, value in self.values.items()},
            "output": self.output,
            "narration": narration,
        }
        if focus is not None:
            event["focus"] = focus
        self.events.append(event)

    def change(self, name: str, before: Any, after: Any) -> dict[str, Any]:
        item: dict[str, Any] = {"name": name, "after": self.safe_value(after)}
        if before is not _MISSING:
            item["before"] = self.safe_value(before)
        return item

    def tick(self) -> None:
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise TraceProblem(f"Execution is limited to {MAX_STEPS} steps.")

    def run_block(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self.tick()
            self.run_statement(statement)

    def run_statement(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Import):
            allowed = {"math", "statistics", "asyncio"}
            for alias in node.names:
                if alias.name not in allowed or alias.asname:
                    raise TraceProblem("Only import math, import statistics, and import asyncio are available in the safe visualizer.")
                self.values[alias.name] = _SafeModule(alias.name)
                self.emit("module", node, f"Imported the safe {alias.name} module.", [self.change(alias.name, _MISSING, self.values[alias.name])])
            return

        if isinstance(node, ast.ImportFrom):
            raise TraceProblem("Use import math or import statistics, then access a function with dot notation.")

        if isinstance(node, ast.With):
            if len(node.items) != 1 or node.items[0].optional_vars is None or not isinstance(node.items[0].optional_vars, ast.Name):
                raise TraceProblem("Use one file at a time with 'with open(...) as file:'.")
            context = node.items[0].context_expr
            if not isinstance(context, ast.Call) or not isinstance(context.func, ast.Name) or context.func.id != "open" or not 1 <= len(context.args) <= 2 or context.keywords:
                raise TraceProblem("Use open('name.txt', 'r' or 'w') inside a with block.")
            filename = self.evaluate(context.args[0])
            mode = self.evaluate(context.args[1]) if len(context.args) == 2 else "r"
            if not isinstance(filename, str) or not filename or len(filename) > 80 or any(char in filename for char in "/\\:") or filename in {".", ".."}:
                raise TraceProblem("Virtual file names must be simple names such as 'notes.txt'.")
            if mode not in {"r", "w", "a"}:
                raise TraceProblem("Virtual files support only 'r', 'w', or 'a' mode.")
            if mode == "r" and filename not in self.virtual_files:
                raise _PythonRaised("FileNotFoundError", f"No virtual file named {filename!r}")
            if mode == "w":
                self.virtual_files[filename] = ""
            self.virtual_files.setdefault(filename, "")
            file_name = node.items[0].optional_vars.id
            handle = _VirtualFile(filename, mode, self.virtual_files)
            before = self.values.get(file_name, _MISSING)
            self.values[file_name] = handle
            self.emit("file", node, f"Opened in-memory file {filename!r} for {mode == 'r' and 'reading' or 'writing'}.", [self.change(file_name, before, handle)])
            try:
                self.run_block(node.body)
            finally:
                handle.closed = True
                self.values.pop(file_name, None)
                self.emit("file", node, f"Closed in-memory file {filename!r}.")
            return

        if isinstance(node, ast.ClassDef):
            if node.name in self.classes or node.name in self.functions:
                raise TraceProblem(f"{node.name} is already defined.")
            if self.call_stack:
                raise TraceProblem("Define lesson classes at the top level.")
            if node.decorator_list or node.bases or node.keywords:
                raise TraceProblem("Classes do not support inheritance, decorators, or class options yet.")
            methods: dict[str, ast.FunctionDef] = {}
            for statement in node.body:
                if isinstance(statement, ast.Pass):
                    continue
                if not isinstance(statement, ast.FunctionDef):
                    raise TraceProblem("A lesson class can contain methods and pass only.")
                if statement.name in methods:
                    raise TraceProblem(f"The class already has a {statement.name} method.")
                if statement.decorator_list or statement.args.defaults or statement.args.kw_defaults or statement.args.kwonlyargs or statement.args.vararg or statement.args.kwarg or statement.args.posonlyargs:
                    raise TraceProblem("Class methods need simple positional parameters without decorators or defaults.")
                if statement.returns or any(argument.annotation for argument in statement.args.args):
                    raise TraceProblem("Class method type annotations are not supported yet.")
                if not statement.args.args or len(statement.args.args) > 9:
                    raise TraceProblem("Class methods need self and can use up to 8 additional parameters.")
                methods[statement.name] = statement
            self.classes[node.name] = methods
            self.emit("class_def", node, f"Defined the {node.name} class.")
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in self.functions or node.name in self.classes:
                raise TraceProblem(f"{node.name} is already defined.")
            if self.call_stack:
                raise TraceProblem("Define lesson functions at the top level.")
            if node.decorator_list:
                if len(node.decorator_list) != 1 or not isinstance(node.decorator_list[0], ast.Name):
                    raise TraceProblem("The visualizer supports one simple identity decorator per function.")
                decorator = self.functions.get(node.decorator_list[0].id)
                if decorator is None or len(decorator.args.args) != 1 or len(decorator.body) != 1 or not isinstance(decorator.body[0], ast.Return) or not isinstance(decorator.body[0].value, ast.Name) or decorator.body[0].value.id != decorator.args.args[0].arg:
                    raise TraceProblem("For this lesson, define a one-parameter identity decorator that returns its function.")
                self.emit("decorator", node, f"Applied @{node.decorator_list[0].id}; the decorator returns the original function.")
            if node.args.defaults or node.args.kw_defaults or node.args.kwonlyargs or node.args.vararg or node.args.kwarg or node.args.posonlyargs:
                raise TraceProblem("Use a simple function with named parameters and no default values.")
            if node.returns or any(argument.annotation for argument in node.args.args):
                raise TraceProblem("Function type annotations are not supported yet.")
            if len(node.args.args) > 8:
                raise TraceProblem("Functions can use up to 8 parameters.")
            self.functions[node.name] = node
            if isinstance(node, ast.AsyncFunctionDef):
                self.async_functions.add(node.name)
            if any(isinstance(part, ast.Yield) for part in ast.walk(node)):
                self.generator_functions.add(node.name)
            self.emit("function_def", node, f"Defined the {node.name} function.")
            return

        if isinstance(node, ast.Try):
            if node.handlers and any(handler.type is None for handler in node.handlers[:-1]):
                raise TraceProblem("Put a general except block after specific exception handlers.")
            matched = False
            try:
                try:
                    self.run_block(node.body)
                except _PythonRaised as error:
                    handler_match = None
                    for handler in node.handlers:
                        names = self.exception_handler_names(handler.type)
                        if names is None or error.name in names or "Exception" in names:
                            handler_match = handler
                            break
                    if handler_match is None:
                        raise
                    matched = True
                    self.emit("exception", handler_match, f"Caught {error.name}: {error.message}.")
                    if handler_match.name:
                        self.values[handler_match.name] = error.message
                    try:
                        self.run_block(handler_match.body)
                    finally:
                        if handler_match.name:
                            self.values.pop(handler_match.name, None)
                if not matched:
                    self.run_block(node.orelse)
            finally:
                self.run_block(node.finalbody)
            return

        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Yield):
            if self.generator_capture is None:
                raise TraceProblem("Use yield inside a generator function.")
            value = self.evaluate(node.value.value) if node.value.value else None
            self.generator_capture.append(value)
            self.emit("generator_yield", node, f"Generator yielded {self.describe(value)}.")
            return

        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Await):
            self.evaluate(node.value)
            return

        if isinstance(node, ast.Return):
            if not self.call_stack:
                raise TraceProblem("Use return inside a function.")
            value = self.safe_value(self.evaluate(node.value)) if node.value else None
            self.emit("return", node, f"Returned {self.describe(value)}.")
            raise _ReturnSignal(value)

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                raise TraceProblem("Assign one value at a time.")
            target = node.targets[0]
            if isinstance(target, (ast.Tuple, ast.List)) and all(isinstance(item, ast.Name) for item in target.elts):
                values = self.evaluate(node.value)
                if not isinstance(values, (tuple, list)) or len(values) != len(target.elts):
                    raise TraceProblem("Unpack a tuple or list into the same number of variable names.")
                changes = []
                for name_node, after in zip(target.elts, values):
                    before = self.values.get(name_node.id, _MISSING)
                    self.values[name_node.id] = after
                    changes.append(self.change(name_node.id, before, after))
                self.emit("assignment", node, "Unpacked each item into its matching variable.", changes)
                return
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                object_name = target.value.id
                instance = self.values.get(object_name)
                if not isinstance(instance, _SafeInstance) or target.attr.startswith("__"):
                    raise TraceProblem("Set an attribute on a created object, such as student.score = 10.")
                before = self.safe_value(instance)
                after = self.safe_value(self.evaluate(node.value))
                instance.attributes[target.attr] = after
                self.emit("assignment", node, f"Updated {object_name}.{target.attr}.", [self.change(object_name, before, instance)])
                return
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                name = target.value.id
                collection = self.values.get(name)
                key = self.evaluate(target.slice)
                if not isinstance(collection, dict):
                    raise TraceProblem("Change a dictionary value using its text key, like scores['Maya'] = 10.")
                if not isinstance(key, str):
                    raise TraceProblem("Dictionary keys must be text.")
                before = self.safe_value(collection)
                collection[key] = self.safe_value(self.evaluate(node.value))
                after = self.safe_value(collection)
                focus = {"collection": name, "index": list(collection).index(key)}
                self.emit("assignment", node, f"Updated {name}[{key!r}].", [self.change(name, before, after)], focus)
                return
            if not isinstance(target, ast.Name):
                raise TraceProblem("Use a variable name or a text key in a dictionary assignment.")
            name = target.id
            before = self.values.get(name, _MISSING)
            after = self.evaluate(node.value)
            focus = None
            focus_node = node.value if isinstance(node.value, ast.Subscript) else None
            if isinstance(focus_node, ast.Subscript) and not isinstance(focus_node.slice, ast.Slice) and isinstance(focus_node.value, ast.Name):
                collection_name = focus_node.value.id
                collection = self.values.get(collection_name)
                index = self.evaluate(focus_node.slice)
                if isinstance(collection, (list, tuple, str)) and isinstance(index, int) and not isinstance(index, bool):
                    normalized_index = index if index >= 0 else len(collection) + index
                    if 0 <= normalized_index < len(collection):
                        focus = {"collection": collection_name, "index": normalized_index}
                elif isinstance(collection, dict) and isinstance(index, str) and index in collection:
                    focus = {"collection": collection_name, "index": list(collection).index(index)}
            self.values[name] = after
            kind = "setup" if before is _MISSING else "assignment"
            self.emit(kind, node, f"Set {name} to {self.describe(after)}.", [self.change(name, before, after)], focus)
            return

        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise TraceProblem("Update a variable by name, such as total += num.")
            name = node.target.id
            if name not in self.values:
                raise TraceProblem(f"'{name}' must be created before it can be updated.")
            before = self.values[name]
            after = self.apply_operator(node.op, before, self.evaluate(node.value))
            self.values[name] = after
            self.emit("assignment", node, f"Updated {name} to {self.describe(after)}.", [self.change(name, before, after)])
            return

        if isinstance(node, ast.If):
            decision = self.truthy(self.evaluate(node.test))
            if decision:
                narration = "Condition is true; the if branch runs."
                branch = node.body
            elif node.orelse:
                narration = "Condition is false; the else branch runs."
                branch = node.orelse
            else:
                narration = "Condition is false; there is no else branch."
                branch = []
            self.emit("branch", node, narration)
            self.run_block(branch)
            return
        if isinstance(node, ast.While):
            if node.orelse:
                raise TraceProblem("A while-loop else block is not supported yet.")
            iteration = 0
            ended_by_break = False
            self.loop_depth += 1
            try:
                while self.truthy(self.evaluate(node.test)):
                    if iteration >= MAX_LOOP_ITEMS:
                        raise TraceProblem(f"While loops are limited to {MAX_LOOP_ITEMS} turns.")
                    iteration += 1
                    self.emit("branch", node, f"Condition is true; while loop turn {iteration} runs.")
                    try:
                        self.run_block(node.body)
                    except _ContinueSignal:
                        continue
                    except _BreakSignal:
                        ended_by_break = True
                        break
            finally:
                self.loop_depth -= 1
            if not ended_by_break:
                self.emit("branch", node, "Condition is false; the while loop stops.")
            self.emit("loop_end", node, "The while loop has finished.")
            return
        if isinstance(node, ast.For):
            if isinstance(node.target, ast.Name):
                target_names = [node.target.id]
            elif isinstance(node.target, ast.Tuple) and all(isinstance(item, ast.Name) for item in node.target.elts):
                target_names = [item.id for item in node.target.elts]
            else:
                raise TraceProblem("For loops can use a variable or simple names such as 'for index, item in pairs:'.")
            if node.orelse:
                raise TraceProblem("A for-loop else block is not supported yet.")
            source_name = node.iter.id if isinstance(node.iter, ast.Name) else None
            if isinstance(node.iter, ast.Call) and node.iter.args and isinstance(node.iter.args[0], ast.Name):
                source_name = node.iter.args[0].id
            items = self.evaluate(node.iter)
            if not isinstance(items, (list, tuple, range, dict, set, str)):
                raise TraceProblem("A for loop can go through a list, tuple, dictionary, set, text, or range(...).")
            if len(items) > MAX_LOOP_ITEMS:
                raise TraceProblem(f"Loops are limited to {MAX_LOOP_ITEMS} items.")
            loop_items = self.sorted_set_values(items) if isinstance(items, set) else list(items) if isinstance(items, (dict, str, range)) else items
            self.loop_depth += 1
            try:
                for index, item in enumerate(loop_items):
                    values_to_assign = list(item) if isinstance(node.target, ast.Tuple) and isinstance(item, (tuple, list)) else [item]
                    if len(values_to_assign) != len(target_names):
                        raise TraceProblem("Each loop item must match the number of loop variables.")
                    changes = []
                    for name, after in zip(target_names, values_to_assign):
                        before = self.values.get(name, _MISSING)
                        self.values[name] = after
                        changes.append(self.change(name, before, after))
                    focus = {"collection": source_name, "index": index} if source_name else None
                    assigned = ", ".join(target_names)
                    self.emit("iteration", node, f"Loop selects {self.describe(item)} for {assigned}.", changes, focus)
                    try:
                        self.run_block(node.body)
                    except _ContinueSignal:
                        continue
                    except _BreakSignal:
                        break
            finally:
                self.loop_depth -= 1
            self.emit("loop_end", node, "The loop has finished.")
            return

        if isinstance(node, ast.Break):
            if self.loop_depth == 0:
                raise TraceProblem("Use break inside a loop.")
            self.emit("loop_control", node, "break stops this loop early.")
            raise _BreakSignal()

        if isinstance(node, ast.Continue):
            if self.loop_depth == 0:
                raise TraceProblem("Use continue inside a loop.")
            self.emit("loop_control", node, "continue skips the rest of this turn and starts the next one.")
            raise _ContinueSignal()

        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            self.run_call(node.value, node)
            return

        if isinstance(node, ast.Pass):
            return

        names = {
            "If": "if statements",
            "While": "while loops",
            "FunctionDef": "function definitions",
            "AsyncFunctionDef": "async functions",
            "ClassDef": "class definitions",
            "Import": "imports",
            "ImportFrom": "imports",
            "Try": "try/except blocks",
            "With": "with blocks",
            "ListComp": "list comprehensions",
        }
        label = names.get(type(node).__name__, type(node).__name__)
        raise TraceProblem(f"{label} are not supported yet.")

    @staticmethod
    def exception_handler_names(node: ast.expr | None) -> set[str] | None:
        if node is None:
            return None
        allowed = {"ZeroDivisionError", "ValueError", "TypeError", "IndexError", "KeyError", "Exception"}
        nodes = node.elts if isinstance(node, ast.Tuple) else [node]
        names: set[str] = set()
        for item in nodes:
            if not isinstance(item, ast.Name) or item.id not in allowed:
                raise TraceProblem("Catch ZeroDivisionError, ValueError, TypeError, IndexError, KeyError, or Exception.")
            names.add(item.id)
        return names

    def run_call(self, node: ast.Call, statement: ast.stmt) -> None:
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            module = self.values.get(node.func.value.id)
            if isinstance(module, _SafeModule):
                value = self.evaluate(node)
                if module.name != "asyncio":
                    self.emit("module", statement, f"Used {module.name}.{node.func.attr}() from the safe module.")
                return
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            receiver = self.values.get(node.func.value.id)
            if isinstance(receiver, _VirtualFile) and node.func.attr == "write":
                if receiver.closed or receiver.mode not in {"w", "a"} or len(node.args) != 1 or node.keywords:
                    raise TraceProblem("write() needs one text value on an open file in 'w' or 'a' mode.")
                value = self.evaluate(node.args[0])
                if not isinstance(value, str):
                    raise TraceProblem("Virtual files can write text only.")
                if len(receiver.files[receiver.name]) + len(value) > MAX_STRING_LENGTH:
                    raise TraceProblem("Virtual files are limited to 500 characters.")
                if receiver.mode == "a":
                    receiver.files[receiver.name] += value
                else:
                    receiver.files[receiver.name] = value
                self.emit("file", statement, f"Wrote {len(value)} characters to {receiver.name!r}.")
                return
            if isinstance(receiver, _SafeInstance):
                self.call_method(receiver, node.func.attr, node)
                return
        if isinstance(node.func, ast.Name) and node.func.id in self.classes:
            self.instantiate_class(node)
            return
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"add", "discard", "remove"}:
            if isinstance(node.func.value, ast.Name) and isinstance(self.values.get(node.func.value.id), list):
                self.run_list_method(node, statement)
            else:
                self.run_set_method(node, statement)
            return
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"append", "insert", "pop"}:
            self.run_list_method(node, statement)
            return
        if isinstance(node.func, ast.Name) and node.func.id in self.functions:
            self.call_function(node)
            return
        if not isinstance(node.func, ast.Name) or node.func.id != "print":
            raise TraceProblem("Only print(...) calls are supported.")
        values = [self.evaluate(argument) for argument in node.args]
        sep = " "
        end = "\n"
        for keyword in node.keywords:
            if keyword.arg not in {"sep", "end"}:
                raise TraceProblem("print() only supports the sep and end options.")
            setting = self.evaluate(keyword.value)
            if not isinstance(setting, str):
                raise TraceProblem("print() sep and end values must be text.")
            if keyword.arg == "sep":
                sep = setting
            else:
                end = setting
        text = sep.join(self.describe(value) if isinstance(value, set) else str(value) for value in values) + end
        if len(self.output) + len(text) > MAX_OUTPUT_LENGTH:
            raise TraceProblem(f"Program output is limited to {MAX_OUTPUT_LENGTH} characters.")
        self.output += text
        preview = text.rstrip("\n")
        self.emit("output", statement, f"Printed {preview!r}.")

    def run_list_method(self, node: ast.Call, statement: ast.stmt) -> None:
        if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
            raise TraceProblem("Use append(), insert(), remove(), or pop() on a named list.")
        name = node.func.value.id
        values = self.values.get(name)
        if not isinstance(values, list):
            raise TraceProblem("append(), insert(), remove(), and pop() can only be used with a list.")
        operation = node.func.attr
        if node.keywords:
            raise TraceProblem(f"{operation}() does not use named options here.")
        expected = {"append": (1,), "remove": (1,), "insert": (2,), "pop": (0, 1)}.get(operation)
        if expected is None or len(node.args) not in expected:
            raise TraceProblem({"append": "append() needs one value.", "remove": "remove() needs one value.", "insert": "insert() needs an index and a value.", "pop": "pop() accepts an optional index."}.get(operation, "This list tool is not supported."))

        before = self.safe_value(values)
        if operation == "append":
            item = self.safe_value(self.evaluate(node.args[0]))
            if len(values) >= MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            values.append(item)
            index = len(values) - 1
            action = f"Added {self.describe(item)} to the end of {name}."
        elif operation == "insert":
            raw_index = self.evaluate(node.args[0])
            if not isinstance(raw_index, int) or isinstance(raw_index, bool):
                raise TraceProblem("insert() needs a whole-number index.")
            item = self.safe_value(self.evaluate(node.args[1]))
            if len(values) >= MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            index = max(0, min(raw_index if raw_index >= 0 else len(values) + raw_index, len(values)))
            values.insert(index, item)
            action = f"Inserted {self.describe(item)} into {name} at position {index + 1}."
        elif operation == "remove":
            item = self.safe_value(self.evaluate(node.args[0]))
            try:
                index = values.index(item)
            except ValueError as exc:
                raise TraceProblem(f"{self.describe(item)} is not in {name}.") from exc
            values.pop(index)
            index = min(index, len(values) - 1)
            action = f"Removed {self.describe(item)} from {name}."
        else:
            raw_index = self.evaluate(node.args[0]) if node.args else -1
            if not isinstance(raw_index, int) or isinstance(raw_index, bool):
                raise TraceProblem("pop() needs a whole-number index.")
            if not values:
                raise TraceProblem(f"Cannot pop from an empty list, {name}.")
            index = raw_index if raw_index >= 0 else len(values) + raw_index
            if not 0 <= index < len(values):
                raise TraceProblem(f"pop() index is out of range for {name}.")
            item = values.pop(index)
            removed_position = index + 1
            index = min(index, len(values) - 1)
            action = f"Removed {self.describe(item)} from {name} at position {removed_position}."

        after = self.safe_value(values)
        focus = {"collection": name, "index": index} if index >= 0 else None
        self.emit("assignment", statement, action, [self.change(name, before, after)], focus)

    def run_set_method(self, node: ast.Call, statement: ast.stmt) -> None:
        if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
            raise TraceProblem("Use add(), discard(), or remove() on a named set.")
        name = node.func.value.id
        value = self.values.get(name)
        if not isinstance(value, set):
            raise TraceProblem("add(), discard(), and remove() can only be used with a set.")
        if node.keywords or len(node.args) != 1:
            raise TraceProblem(f"{node.func.attr}() needs one value.")
        item = self.evaluate(node.args[0])
        if not isinstance(item, (str, int, float, bool)):
            raise TraceProblem("Sets can contain text, numbers, or True/False values.")
        before = self.safe_value(value)
        try:
            if node.func.attr == "add":
                value.add(item)
            elif node.func.attr == "discard":
                value.discard(item)
            else:
                value.remove(item)
        except KeyError as exc:
            raise TraceProblem(f"{item!r} is not in the set.") from exc
        after = self.safe_value(value)
        focus = {"collection": name, "index": self.sorted_set_values(value).index(item)} if item in value else None
        self.emit("assignment", statement, f"Updated the {name} set.", [self.change(name, before, after)], focus)

    def instantiate_class(self, node: ast.Call) -> _SafeInstance:
        if not isinstance(node.func, ast.Name):
            raise TraceProblem("Create a class instance using its class name.")
        if node.keywords:
            raise TraceProblem("Create class instances using positional values.")
        class_name = node.func.id
        instance = _SafeInstance(class_name, self.classes[class_name])
        initializer = instance.methods.get("__init__")
        if initializer:
            result = self.call_method(instance, "__init__", node)
            if result is not None:
                raise TraceProblem("__init__() should set attributes and not return a value.")
        elif node.args:
            raise TraceProblem(f"{class_name}() does not take any values.")
        return instance

    def call_method(self, instance: _SafeInstance, method_name: str, node: ast.Call) -> Any:
        method = instance.methods.get(method_name)
        if method is None:
            raise TraceProblem(f"{instance.class_name} has no supported {method_name}() method.")
        if node.keywords:
            raise TraceProblem("Call class methods using positional values.")
        parameters = [argument.arg for argument in method.args.args]
        arguments = [self.evaluate(argument) for argument in node.args]
        if len(arguments) != len(parameters) - 1:
            raise TraceProblem(f"{instance.class_name}.{method_name}() needs {len(parameters) - 1} value(s).")
        if len(self.call_stack) >= MAX_FUNCTION_DEPTH:
            raise TraceProblem(f"Function calls are limited to {MAX_FUNCTION_DEPTH} levels.")
        qualified_name = f"{instance.class_name}.{method_name}"
        self.emit("call", node, f"Calling {qualified_name}().")
        self.events[-1]["callStack"] = [*self.call_stack, qualified_name]
        saved_values = self.values
        self.values = {**saved_values, parameters[0]: instance, **dict(zip(parameters[1:], arguments))}
        self.call_stack.append(qualified_name)
        parent_loop_depth = self.loop_depth
        self.loop_depth = 0
        result = None
        try:
            self.run_block(method.body)
        except _ReturnSignal as returned:
            result = self.safe_value(returned.value)
        else:
            self.emit("return", method, f"{qualified_name} finished without returning a value.")
        finally:
            self.call_stack.pop()
            self.values = saved_values
            self.loop_depth = parent_loop_depth
        return result

    def call_function(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise TraceProblem("Call a function by its name.")
        function = self.functions[node.func.id]
        if node.func.id in self.generator_functions:
            saved_capture = self.generator_capture
            self.generator_capture = []
            try:
                parameters = [argument.arg for argument in function.args.args]
                if node.keywords:
                    raise TraceProblem("Call lesson functions using positional values.")
                arguments = [self.evaluate(argument) for argument in node.args]
                if len(arguments) != len(parameters):
                    raise TraceProblem(f"{function.name}() needs {len(parameters)} value(s).")
                self.emit("call", node, f"Starting generator {function.name}().")
                saved_values = self.values
                self.values = {**saved_values, **dict(zip(parameters, arguments))}
                self.call_stack.append(function.name)
                try:
                    self.run_block(function.body)
                except _ReturnSignal:
                    pass
                finally:
                    self.call_stack.pop()
                    self.values = saved_values
                return list(self.generator_capture)
            finally:
                self.generator_capture = saved_capture
        if isinstance(function, ast.AsyncFunctionDef) and not any(name.startswith("async:") for name in self.call_stack):
            raise TraceProblem("Call async lesson functions through asyncio.run(...).")
        parameters = [argument.arg for argument in function.args.args]
        if node.keywords:
            raise TraceProblem("Call lesson functions using positional values.")
        arguments = [self.evaluate(argument) for argument in node.args]
        if len(arguments) != len(parameters):
            raise TraceProblem(f"{function.name}() needs {len(parameters)} value(s).")
        if len(self.call_stack) >= MAX_FUNCTION_DEPTH:
            raise TraceProblem(f"Function calls are limited to {MAX_FUNCTION_DEPTH} levels.")

        self.emit("call", node, f"Calling {function.name}().")
        self.events[-1]["callStack"] = [*self.call_stack, function.name]
        saved_values = self.values
        self.values = {**saved_values, **dict(zip(parameters, arguments))}
        self.call_stack.append(("async:" if isinstance(function, ast.AsyncFunctionDef) else "") + function.name)
        parent_loop_depth = self.loop_depth
        self.loop_depth = 0
        result = None
        try:
            self.run_block(function.body)
        except _ReturnSignal as returned:
            result = self.safe_value(returned.value)
        else:
            self.emit("return", function, f"{function.name} finished without returning a value.")
        finally:
            self.call_stack.pop()
            self.values = saved_values
            self.loop_depth = parent_loop_depth
        return result

    def evaluate(self, node: ast.expr) -> Any:
        if isinstance(node, ast.JoinedStr):
            pieces: list[str] = []
            for value_node in node.values:
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    pieces.append(value_node.value)
                elif isinstance(value_node, ast.FormattedValue):
                    if value_node.format_spec is not None:
                        raise TraceProblem("F-string format specifiers are not supported yet.")
                    value = self.evaluate(value_node.value)
                    if value_node.conversion == ord("r"):
                        text = repr(value)
                    elif value_node.conversion == ord("a"):
                        text = ascii(value)
                    elif value_node.conversion in {-1, ord("s")}:
                        text = self.describe(value) if isinstance(value, (set, range)) else str(value)
                    else:
                        raise TraceProblem("This f-string conversion is not supported.")
                    pieces.append(text)
                else:
                    raise TraceProblem("This f-string expression is not supported.")
            return self.safe_value("".join(pieces))

        if isinstance(node, ast.Constant):
            if node.value is None or isinstance(node.value, (bool, int, float, str)):
                return self.safe_value(node.value)
            raise TraceProblem("Only text, numbers, True, False, and None can be used as values.")

        if isinstance(node, ast.Await):
            if not any(name.startswith("async:") for name in self.call_stack):
                raise TraceProblem("Use await inside an async function.")
            value = self.evaluate(node.value)
            self.emit("await", node, "The async function resumes after its awaited step (simulated without a real delay).")
            return value

        if isinstance(node, ast.Attribute):
            owner = self.evaluate(node.value)
            if isinstance(owner, _SafeModule):
                if owner.name == "math" and node.attr in {"pi", "e"}:
                    return self.safe_value(math.pi if node.attr == "pi" else math.e)
                allowed = {
                    "math": {"pi", "e", "sqrt", "floor", "ceil"},
                    "statistics": {"mean", "median"},
                    "asyncio": {"run", "sleep"},
                }
                if node.attr in allowed.get(owner.name, set()):
                    return ("module_attribute", owner.name, node.attr)
                raise TraceProblem(f"{owner.name}.{node.attr} is not available in the safe visualizer.")
            if isinstance(owner, _SafeInstance) and node.attr in owner.attributes:
                return owner.attributes[node.attr]
            if isinstance(owner, _SafeInstance):
                raise TraceProblem(f"{owner.class_name} has no {node.attr} attribute yet.")
            raise TraceProblem("Read an attribute from a created object.")

        if isinstance(node, ast.Name):
            if node.id not in self.values:
                raise TraceProblem(f"'{node.id}' has not been assigned a value yet.")
            return self.values[node.id]

        if isinstance(node, ast.ListComp):
            if len(node.generators) != 1 or node.generators[0].is_async:
                raise TraceProblem("Use one simple for-loop inside a list comprehension.")
            generator = node.generators[0]
            if not isinstance(generator.target, ast.Name):
                raise TraceProblem("List comprehensions must use one variable name.")
            items = self.evaluate(generator.iter)
            if not isinstance(items, (list, tuple, range, dict, set, str)):
                raise TraceProblem("A list comprehension needs a list, tuple, set, text, or range.")
            if len(items) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Comprehensions are limited to {MAX_COLLECTION_ITEMS} items.")
            loop_items = self.sorted_set_values(items) if isinstance(items, set) else list(items) if isinstance(items, (dict, str, range)) else items
            name = generator.target.id
            previous = self.values.get(name, _MISSING)
            result = []
            try:
                for item in loop_items:
                    self.values[name] = item
                    if all(self.truthy(self.evaluate(condition)) for condition in generator.ifs):
                        result.append(self.safe_value(self.evaluate(node.elt)))
            finally:
                if previous is _MISSING:
                    self.values.pop(name, None)
                else:
                    self.values[name] = previous
            return self.safe_value(result)

        if isinstance(node, ast.List):
            if len(node.elts) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            return [self.evaluate(item) for item in node.elts]

        if isinstance(node, ast.Tuple):
            if len(node.elts) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            return tuple(self.evaluate(item) for item in node.elts)

        if isinstance(node, ast.Dict):
            if len(node.keys) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            result: dict[str, Any] = {}
            for key_node, value_node in zip(node.keys, node.values):
                if key_node is None:
                    raise TraceProblem("Dictionary unpacking is not supported yet.")
                key = self.evaluate(key_node)
                if not isinstance(key, str):
                    raise TraceProblem("Dictionary keys must be text.")
                result[key] = self.evaluate(value_node)
            return self.safe_value(result)

        if isinstance(node, ast.Set):
            if len(node.elts) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
            items = [self.evaluate(item) for item in node.elts]
            if any(not isinstance(item, (str, int, float, bool)) for item in items):
                raise TraceProblem("Sets can contain text, numbers, or True/False values.")
            try:
                return set(items)
            except TypeError as exc:
                raise TraceProblem("Set values must be simple text, numbers, or True/False values.") from exc

        if isinstance(node, ast.Subscript):
            collection = self.evaluate(node.value)
            if isinstance(node.slice, ast.Slice):
                if not isinstance(collection, (list, tuple, str)):
                    raise TraceProblem("Slices work with lists, tuples, and text.")
                parts = [self.evaluate(part) if part is not None else None for part in (node.slice.lower, node.slice.upper, node.slice.step)]
                if any(part is not None and (not isinstance(part, int) or isinstance(part, bool)) for part in parts):
                    raise TraceProblem("Slice positions and steps must be whole numbers.")
                if parts[2] == 0:
                    raise TraceProblem("A slice step cannot be zero.")
                return self.safe_value(collection[slice(*parts)])
            index = self.evaluate(node.slice)
            if isinstance(collection, dict):
                if not isinstance(index, str):
                    raise TraceProblem("Dictionary keys must be text.")
                if index not in collection:
                    raise _PythonRaised("KeyError", repr(index))
                return self.safe_value(collection[index])
            if not isinstance(collection, (list, tuple, str)):
                raise TraceProblem("Choose an item from a list, tuple, dictionary, or text value.")
            if not isinstance(index, int) or isinstance(index, bool):
                raise TraceProblem("List positions must be whole numbers.")
            try:
                return self.safe_value(collection[index])
            except IndexError as exc:
                raise _PythonRaised("IndexError", "list index out of range") from exc
        if isinstance(node, ast.BinOp):
            return self.apply_operator(node.op, self.evaluate(node.left), self.evaluate(node.right))

        if isinstance(node, ast.Compare):
            return self.evaluate_comparison(node)

        if isinstance(node, ast.BoolOp):
            if not node.values:
                return False
            value = self.evaluate(node.values[0])
            for operand in node.values[1:]:
                if isinstance(node.op, ast.And) and not self.truthy(value):
                    return value
                if isinstance(node.op, ast.Or) and self.truthy(value):
                    return value
                value = self.evaluate(operand)
            return value

        if isinstance(node, ast.UnaryOp):
            value = self.evaluate(node.operand)
            if isinstance(node.op, ast.Not):
                return not self.truthy(value)
            if isinstance(node.op, (ast.UAdd, ast.USub)):
                if not self.is_number(value):
                    raise TraceProblem("Plus and minus signs can only be used with numbers.")
                return self.safe_value(+value if isinstance(node.op, ast.UAdd) else -value)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "set":
            if node.keywords or len(node.args) > 1:
                raise TraceProblem("Use set() or set(one_collection).")
            if not node.args:
                return set()
            value = self.evaluate(node.args[0])
            if not isinstance(value, (str, list, tuple, set)):
                raise TraceProblem("set(...) needs text, a list, a tuple, or another set.")
            items = list(value)
            if any(not isinstance(item, (str, int, float, bool)) for item in items):
                raise TraceProblem("Sets can contain text, numbers, or True/False values.")
            try:
                return set(items)
            except TypeError as exc:
                raise TraceProblem("Set values must be simple text, numbers, or True/False values.") from exc

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"enumerate", "zip"}:
            name = node.func.id
            if node.keywords:
                raise TraceProblem(f"{name}() does not use named options in this lesson subset.")
            arguments = [self.evaluate(argument) for argument in node.args]
            if name == "enumerate":
                if not 1 <= len(arguments) <= 2:
                    raise TraceProblem("Use enumerate(collection) or enumerate(collection, start).")
                source = arguments[0]
                start = arguments[1] if len(arguments) == 2 else 0
                if not isinstance(source, (list, tuple, range, dict, set, str)) or len(source) > MAX_LOOP_ITEMS:
                    raise TraceProblem("enumerate() needs a collection with up to 40 items.")
                if not isinstance(start, int) or isinstance(start, bool):
                    raise TraceProblem("enumerate() start must be a whole number.")
                values = self.sorted_set_values(source) if isinstance(source, set) else list(source)
                return [(start + index, item) for index, item in enumerate(values)]
            if len(arguments) < 2:
                raise TraceProblem("zip() needs at least two collections.")
            sources = []
            for source in arguments:
                if not isinstance(source, (list, tuple, range, dict, set, str)):
                    raise TraceProblem("zip() works with lists, tuples, sets, dictionaries, text, and ranges.")
                values = self.sorted_set_values(source) if isinstance(source, set) else list(source)
                sources.append(values)
            return list(zip(*sources))

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
            if node.keywords or not 1 <= len(node.args) <= 3:
                raise TraceProblem("Use range(start, stop, step) with one to three number values.")
            args = [self.evaluate(argument) for argument in node.args]
            if any(not isinstance(value, int) or isinstance(value, bool) for value in args):
                raise TraceProblem("range(...) values must be whole numbers.")
            try:
                values = range(*args)
            except ValueError as exc:
                raise TraceProblem(str(exc)) from exc
            if len(values) > MAX_LOOP_ITEMS:
                raise TraceProblem(f"range(...) is limited to {MAX_LOOP_ITEMS} values.")
            return values

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.classes:
            return self.instantiate_class(node)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            raise TraceProblem("Use open() inside a 'with' block so the virtual file is closed safely.")

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            receiver = self.evaluate(node.func.value)
            if isinstance(receiver, _SafeModule) and receiver.name == "asyncio":
                if node.keywords:
                    raise TraceProblem("asyncio lesson helpers use positional arguments only.")
                if node.func.attr == "run" and len(node.args) == 1 and isinstance(node.args[0], ast.Call) and isinstance(node.args[0].func, ast.Name):
                    function_name = node.args[0].func.id
                    function = self.functions.get(function_name)
                    if function_name not in self.async_functions or function is None:
                        raise TraceProblem("asyncio.run() needs one async lesson function call.")
                    arguments = [self.evaluate(argument) for argument in node.args[0].args]
                    synthetic_call = ast.Call(func=ast.Name(id=function_name, ctx=ast.Load()), args=[ast.Constant(value=value) for value in arguments], keywords=[])
                    self.call_stack.append("async:" + function_name)
                    try:
                        result = self.call_function(synthetic_call)
                    finally:
                        self.call_stack.pop()
                    self.emit("await", node, f"asyncio.run() finished {function_name}() in the visual teaching model.")
                    return result
                if node.func.attr == "sleep" and len(node.args) == 1:
                    delay = self.evaluate(node.args[0])
                    if not self.is_number(delay) or delay < 0:
                        raise TraceProblem("asyncio.sleep() needs one non-negative number.")
                    return None
                raise TraceProblem("The safe asyncio module supports only run() and simulated sleep().")
            if isinstance(receiver, _VirtualFile):
                if receiver.closed or node.keywords or node.args:
                    raise TraceProblem("Use read() with no options on an open virtual file.")
                if node.func.attr == "read" and receiver.mode == "r":
                    value = receiver.files.get(receiver.name, "")
                    self.emit("file", node, f"Read {len(value)} characters from {receiver.name!r}.")
                    return self.safe_value(value)
                raise TraceProblem("Open a virtual file in 'r' mode before using read().")
            if isinstance(receiver, _SafeModule):
                if node.keywords:
                    raise TraceProblem("Safe module functions use positional arguments only.")
                arguments = [self.evaluate(argument) for argument in node.args]
                module, name = receiver.name, node.func.attr
                if module == "math" and name in {"sqrt", "floor", "ceil"} and len(arguments) == 1 and self.is_number(arguments[0]):
                    value = arguments[0]
                    if name == "sqrt":
                        if value < 0:
                            raise _PythonRaised("ValueError", "math domain error")
                        return self.safe_value(math.sqrt(value))
                    return self.safe_value(math.floor(value) if name == "floor" else math.ceil(value))
                if module == "statistics" and name in {"mean", "median"} and len(arguments) == 1:
                    values = arguments[0]
                    if not isinstance(values, (list, tuple)) or not values or any(not self.is_number(item) for item in values):
                        raise TraceProblem(f"statistics.{name}() needs a non-empty list or tuple of numbers.")
                    result = sum(values) / len(values) if name == "mean" else sorted(values)[(len(values) - 1) // 2] if len(values) % 2 else (sorted(values)[len(values) // 2 - 1] + sorted(values)[len(values) // 2]) / 2
                    return self.safe_value(result)
                raise TraceProblem(f"{module}.{name}() is not available in the safe visualizer.")
            if isinstance(receiver, _SafeInstance):
                return self.call_method(receiver, node.func.attr, node)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.functions:
            return self.call_function(node)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"int", "float", "str", "bool"}:
            name = node.func.id
            if node.keywords or len(node.args) != 1:
                raise TraceProblem(f"{name}() needs one value in this lesson subset.")
            value = self.evaluate(node.args[0])
            try:
                if name == "int":
                    if isinstance(value, bool):
                        result = int(value)
                    elif isinstance(value, (str, int, float)):
                        result = int(value)
                    else:
                        raise TraceProblem("int() converts text or a number to a whole number.")
                elif name == "float":
                    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                        raise TraceProblem("float() converts number text or a number to a decimal number.")
                    result = float(value)
                elif name == "str":
                    result = self.describe(value) if isinstance(value, (set, range)) else str(value)
                else:
                    result = self.truthy(value)
            except (ValueError, OverflowError) as exc:
                raise _PythonRaised("ValueError", f"invalid value {value!r}") from exc
            return self.safe_value(result)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input":
            if node.keywords or len(node.args) > 1:
                raise TraceProblem('Use input() or input("prompt") with one prompt.')
            prompt = self.evaluate(node.args[0]) if node.args else ""
            if not isinstance(prompt, str):
                raise TraceProblem("The input() prompt must be text.")
            if self.input_index >= len(self.input_values):
                raise TraceProblem("Add a value in Program input for each input() call, one value per line.")
            value = self.input_values[self.input_index]
            self.input_index += 1
            if len(value) > MAX_STRING_LENGTH:
                raise TraceProblem(f"Input values are limited to {MAX_STRING_LENGTH} characters.")
            self.emit("input", node, f"Received {value!r} for {prompt or 'input()'}.")
            return value

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len":
            if node.keywords or len(node.args) != 1:
                raise TraceProblem("Use len(...) with one text or collection value.")
            value = self.evaluate(node.args[0])
            if not isinstance(value, (str, list, tuple, dict, set)):
                raise TraceProblem("len(...) works with text and collections.")
            return self.safe_value(len(value))

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"sum", "min", "max", "abs", "round", "sorted"}:
            name = node.func.id
            if node.keywords:
                raise TraceProblem(f"{name}() does not use named options in this lesson subset.")
            arguments = [self.evaluate(argument) for argument in node.args]
            if name == "abs":
                if len(arguments) != 1 or not self.is_number(arguments[0]):
                    raise TraceProblem("abs() needs one number.")
                return self.safe_value(abs(arguments[0]))
            if name == "round":
                if not 1 <= len(arguments) <= 2 or not self.is_number(arguments[0]):
                    raise TraceProblem("Use round(number) or round(number, decimal_places).")
                places = arguments[1] if len(arguments) == 2 else 0
                if not isinstance(places, int) or isinstance(places, bool) or abs(places) > 12:
                    raise TraceProblem("round() decimal places must be a whole number from -12 to 12.")
                return self.safe_value(round(arguments[0], places))
            if name == "sum":
                if not 1 <= len(arguments) <= 2:
                    raise TraceProblem("Use sum(collection) or sum(collection, start_value).")
                source = arguments[0]
                if not isinstance(source, (list, tuple, set, range)) or len(source) > MAX_COLLECTION_ITEMS:
                    raise TraceProblem("sum() needs a collection with up to 40 numbers.")
                start = arguments[1] if len(arguments) == 2 else 0
                if not self.is_number(start) or any(not self.is_number(item) for item in source):
                    raise TraceProblem("sum() works with numbers only.")
                return self.safe_value(sum(source, start))
            if len(arguments) != 1:
                raise TraceProblem(f"{name}() needs one collection.")
            source = arguments[0]
            if not isinstance(source, (list, tuple, set, range, str)) or len(source) > MAX_COLLECTION_ITEMS:
                raise TraceProblem(f"{name}() needs text or a collection with up to 40 items.")
            items = list(source)
            if name == "sorted":
                if any(not isinstance(item, (str, int, float)) or isinstance(item, bool) for item in items):
                    raise TraceProblem("sorted() supports collections of numbers or text.")
                try:
                    return self.safe_value(sorted(items))
                except TypeError as exc:
                    raise TraceProblem("Sort values of the same kind together.") from exc
            if not items:
                raise TraceProblem(f"{name}() needs a collection with at least one item.")
            if any(not isinstance(item, (str, int, float)) or isinstance(item, bool) for item in items):
                raise TraceProblem(f"{name}() supports numbers or text values.")
            try:
                result = min(items) if name == "min" else max(items)
            except TypeError as exc:
                raise TraceProblem("Compare values of the same kind together.") from exc
            return self.safe_value(result)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            value = self.evaluate(node.func.value)
            if node.keywords:
                raise TraceProblem(f"{method}() does not use named options in this lesson subset.")
            arguments = [self.evaluate(argument) for argument in node.args]
            if isinstance(value, dict) and method in {"get", "keys", "values", "items"}:
                if method == "get":
                    if not 1 <= len(arguments) <= 2 or not isinstance(arguments[0], str):
                        raise TraceProblem("get() needs a text key and an optional default value.")
                    return self.safe_value(value.get(arguments[0], arguments[1] if len(arguments) == 2 else None))
                if arguments:
                    raise TraceProblem(f"{method}() does not need values inside its parentheses.")
                if method == "keys":
                    result = list(value.keys())
                elif method == "values":
                    result = list(value.values())
                else:
                    result = list(value.items())
                return self.safe_value(result)
            if isinstance(value, (list, tuple, str)) and method in {"count", "index"}:
                if len(arguments) != 1:
                    raise TraceProblem(f"{method}() needs one value to search for.")
                try:
                    result = value.count(arguments[0]) if method == "count" else value.index(arguments[0])
                except ValueError as exc:
                    raise _PythonRaised("ValueError", f"{arguments[0]!r} was not found") from exc
                return self.safe_value(result)
            if method not in {"upper", "lower", "strip", "replace"}:
                raise TraceProblem("Supported text tools are upper(), lower(), strip(), and replace().")
            if not isinstance(value, str):
                raise TraceProblem("Text tools can only be used with text values.")
            if method == "replace":
                if len(arguments) != 2 or not all(isinstance(argument, str) for argument in arguments):
                    raise TraceProblem("Use replace(old_text, new_text) with two text values.")
                return self.safe_value(value.replace(arguments[0], arguments[1]))
            if arguments:
                raise TraceProblem(f"{method}() does not need any values inside its parentheses.")
            return self.safe_value(getattr(value, method)())

        raise TraceProblem(f"{type(node).__name__} expressions are not supported yet.")

    @staticmethod
    def is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def apply_operator(self, operation: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(operation, ast.Add):
            if self.is_number(left) and self.is_number(right):
                result = left + right
            elif isinstance(left, str) and isinstance(right, str):
                result = left + right
            elif isinstance(left, list) and isinstance(right, list):
                if len(left) + len(right) > MAX_COLLECTION_ITEMS:
                    raise TraceProblem(f"Collections are limited to {MAX_COLLECTION_ITEMS} items.")
                result = left + right
            else:
                raise _PythonRaised("TypeError", "unsupported operand types for +")
        elif isinstance(operation, ast.Sub):
            self.require_numbers(left, right, "-")
            result = left - right
        elif isinstance(operation, ast.Mult):
            self.require_numbers(left, right, "*")
            result = left * right
        elif isinstance(operation, ast.Div):
            self.require_numbers(left, right, "/")
            if right == 0:
                raise _PythonRaised("ZeroDivisionError", "division by zero")
            result = left / right
        elif isinstance(operation, ast.FloorDiv):
            self.require_numbers(left, right, "//")
            if right == 0:
                raise _PythonRaised("ZeroDivisionError", "integer division or modulo by zero")
            result = left // right
        elif isinstance(operation, ast.Mod):
            self.require_numbers(left, right, "%")
            if right == 0:
                raise _PythonRaised("ZeroDivisionError", "integer modulo by zero")
            result = left % right
        elif isinstance(operation, ast.BitAnd):
            if not isinstance(left, set) or not isinstance(right, set):
                raise TraceProblem("Use & to find the intersection of two sets.")
            result = left & right
        elif isinstance(operation, ast.Pow):
            self.require_numbers(left, right, "**")
            if abs(right) > 12:
                raise TraceProblem("For a clear visual trace, exponents are limited to -12 through 12.")
            result = left ** right
            if isinstance(result, complex):
                raise TraceProblem("Complex number results are not supported in this visualizer.")
        else:
            raise TraceProblem("That math operation is not supported yet.")
        return self.safe_value(result)

    @staticmethod
    def truthy(value: Any) -> bool:
        if value is None or isinstance(value, (bool, int, float, str, list, tuple, range)):
            return bool(value)
        raise TraceProblem("This value cannot be used as a condition.")

    def evaluate_comparison(self, node: ast.Compare) -> bool:
        left = self.evaluate(node.left)
        for operation, comparator in zip(node.ops, node.comparators):
            right = self.evaluate(comparator)
            if isinstance(operation, ast.Eq):
                matches = left == right
            elif isinstance(operation, ast.NotEq):
                matches = left != right
            elif isinstance(operation, ast.Lt):
                self.require_orderable(left, right)
                matches = left < right
            elif isinstance(operation, ast.LtE):
                self.require_orderable(left, right)
                matches = left <= right
            elif isinstance(operation, ast.Gt):
                self.require_orderable(left, right)
                matches = left > right
            elif isinstance(operation, ast.GtE):
                self.require_orderable(left, right)
                matches = left >= right
            elif isinstance(operation, ast.In):
                self.require_container(right)
                if isinstance(right, str) and not isinstance(left, str):
                    raise TraceProblem("Text membership checks need text on both sides.")
                matches = left in right
            elif isinstance(operation, ast.NotIn):
                self.require_container(right)
                if isinstance(right, str) and not isinstance(left, str):
                    raise TraceProblem("Text membership checks need text on both sides.")
                matches = left not in right
            else:
                raise TraceProblem("That comparison is not supported yet.")
            if not matches:
                return False
            left = right
        return True

    @staticmethod
    def require_container(value: Any) -> None:
        if not isinstance(value, (str, list, tuple, dict, set, range)):
            raise TraceProblem("The right side of 'in' must be text or a collection.")

    def require_orderable(self, left: Any, right: Any) -> None:
        numeric = self.is_number(left) and self.is_number(right)
        text = isinstance(left, str) and isinstance(right, str)
        if not numeric and not text:
            raise TraceProblem("Compare numbers with numbers or text with text.")
    def require_numbers(self, left: Any, right: Any, symbol: str) -> None:
        if not self.is_number(left) or not self.is_number(right):
            raise _PythonRaised("TypeError", f"{symbol} can only be used with numbers")

    @staticmethod
    def sorted_set_values(value: set[Any]) -> list[Any]:
        def sort_key(item: Any) -> tuple[str, Any]:
            if isinstance(item, bool):
                return ("bool", int(item))
            if isinstance(item, (int, float)):
                return ("number", item)
            return (type(item).__name__, str(item))

        return sorted(value, key=sort_key)

    @staticmethod
    def describe(value: Any) -> str:
        if isinstance(value, range):
            return f"range({value.start}, {value.stop}, {value.step})"
        if isinstance(value, set):
            return "{" + ", ".join(repr(item) for item in SafePythonTracer.sorted_set_values(value)) + "}"
        if isinstance(value, _SafeInstance):
            return f"<{value.class_name} object>"
        return repr(value)


def trace_code(source: str, inputs: list[str] | None = None) -> dict[str, Any]:
    if not source.strip():
        return {"events": [], "output": "", "error": "Enter some Python code first."}
    tracer: SafePythonTracer | None = None
    try:
        tree = ast.parse(source, filename="<codeflow>", mode="exec")
        if sum(1 for _ in ast.walk(tree)) > MAX_SOURCE_NODES:
            return {"events": [], "output": "", "error": f"Code is limited to {MAX_SOURCE_NODES} syntax nodes."}
        if inputs is not None and (len(inputs) > MAX_LOOP_ITEMS or any(not isinstance(value, str) for value in inputs)):
            raise TraceProblem(f"Provide up to {MAX_LOOP_ITEMS} text input values.")
        tracer = SafePythonTracer(inputs)
        tracer.run_block(tree.body)
        return {"events": tracer.events, "output": tracer.output, "error": None}
    except SyntaxError as exc:
        line = f"Line {exc.lineno}: " if exc.lineno else ""
        message = exc.msg or "Invalid Python syntax."
        return {"events": [], "output": "", "error": line + message}
    except _PythonRaised as exc:
        message = f"{exc.name}: {exc.message}"
        return {"events": tracer.events if tracer else [], "output": tracer.output if tracer else "", "error": message}
    except (TraceProblem, ArithmeticError, ValueError, RecursionError, MemoryError) as exc:
        message = str(exc) or "This code could not be traced."
        return {"events": tracer.events if tracer else [], "output": tracer.output if tracer else "", "error": message}

