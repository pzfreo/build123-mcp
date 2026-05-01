# Security

## Threat model

build123d-mcp executes AI-generated Python code via `exec()`. The primary threat is **prompt injection**: malicious content in a file or web page that the user asks an AI to analyse causes the AI to call `execute()` with a payload intended to read files, exfiltrate data, run shell commands, or open network connections.

This is a local development tool. It is not designed for multi-tenant or production deployments.

---

## Defences

Three layers are applied to every `execute()` call.

### 1. AST inspection (pre-execution)

Before `exec()` is called, the code is parsed and the AST is walked. The check rejects:

- `import <module>` or `from <module> import ...` where the root module is not in the allowlist
- Direct calls to `eval`, `exec`, `compile`, `open`, `__import__`, `breakpoint`, `input`

**Import allowlist:** `build123d`, `math`, `numpy`, `typing`, `collections`, `itertools`, `functools`, `copy`

This blocks common injection patterns before any code runs:
- Shell access: `import os`, `import subprocess`
- Filesystem: `import pathlib`, `import shutil`, `from os.path import ...`
- Network: `import socket`, `import urllib`, `import requests`, `import http`
- Code injection: `eval(...)`, `exec(...)`
- File I/O: `open(...)`

### 2. Restricted builtins (namespace-level)

The exec namespace's `__builtins__` is replaced with a filtered copy:

- `open`, `eval`, `exec`, `compile`, `breakpoint`, `input` are removed outright
- `__import__` is replaced with an allowlisted wrapper that enforces the same import allowlist at the namespace level

This provides a second layer independent of AST inspection. If the AST check were somehow bypassed (e.g. by a future code path that skips it), the namespace `__import__` restriction still fires at runtime.

### 3. Execution timeout

Each `execute()` call runs in a daemon thread with a configurable wall-clock limit (default: 30 seconds). If the limit is exceeded, `ExecutionTimeout` is raised and the error is returned to the caller.

This prevents denial-of-service via infinite loops or expensive computations.

---

## Known limitations

These are not fixed by the current implementation. They are documented so users can make an informed decision about deployment.

### Python sandbox escapes

Python's object model exposes powerful introspection APIs that can bypass namespace-level restrictions:

```python
# Access OS module via subclass traversal — not blocked
[c for c in ().__class__.__bases__[0].__subclasses__()
 if 'Popen' in c.__name__][0](['id'])

# Access globals of an imported function
list.__class__.__mro__[-1].__subclasses__()
```

These patterns are not blocked. Blocking them reliably requires a proper sandbox (see below).

### Build123d internals

Once `from build123d import *` runs, build123d symbols are in the exec namespace. If any build123d function internally wraps a file or subprocess operation, it could be called from user code without triggering the import check.

### Memory exhaustion

No memory limit is enforced. User code can allocate unbounded memory:

```python
x = [0] * 10**10  # not blocked
```

### Timeout thread continues

The daemon thread running exec'd code continues after a timeout. The namespace may be in a partially modified state. Callers should treat the session as dirty after a timeout and call `reset()` or `restore_snapshot()`.

### Windows

`signal.SIGALRM` is not available on Windows. The timeout uses a thread join, which works cross-platform but cannot forcibly terminate the runaway thread.

---

## Recommendations for higher-security deployments

If you are running this server in an environment where the input is not trusted (e.g. exposing it to external users, or in a shared environment), the namespace-level defences are not sufficient. Consider:

1. **Run in a container** with no network access (`--network none`) and a read-only filesystem mount (except a controlled output directory).
2. **Use seccomp/AppArmor** to restrict syscalls to those needed by build123d (file I/O within a temp dir, no fork, no network).
3. **Use RestrictedPython** as an additional layer before exec, though it requires careful allowlisting to work with build123d.
4. **Run each execute() call in a subprocess** and communicate results over a pipe; the subprocess can be killed hard on timeout.

---

## Reporting security issues

Open an issue at https://github.com/pzfreo/build123d-mcp/issues and label it `security`.
