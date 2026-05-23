# Step 09 — CLI scaffold & `exec` command

## Goal

Wire up the `bal-sbx` CLI entry point. Implement the orchestrator (argparse subparser dispatch) and the first two user-facing commands: `bal-sbx exec` and `bal-sbx capabilities`. After this step, the Phase 1 exit criteria can be checked end-to-end.

## Files created

- `bal_sbx/cli/__init__.py`
- `bal_sbx/cli/main.py`
- `bal_sbx/cli/output.py`
- `bal_sbx/cli/commands/__init__.py`
- `bal_sbx/cli/commands/exec_cmd.py`        # filename avoids shadowing builtin `exec`
- `bal_sbx/cli/commands/capabilities.py`
- `tests/unit/cli/__init__.py`
- `tests/unit/cli/test_main.py`
- `tests/unit/cli/test_exec_cmd.py`
- `tests/unit/cli/test_capabilities.py`

## Public surface introduced

```bash
bal-sbx capabilities
bal-sbx exec [--workspace PATH] [--unsafe] -- <cmd> [args...]
```

```python
# bal_sbx/cli/main.py
def main(argv: Sequence[str] | None = None) -> int: ...

# bal_sbx/cli/output.py
def emit(message: str, *, level: str = "info") -> None: ...
def emit_capabilities(caps: Capabilities) -> None: ...
def emit_unsafe_banner() -> None: ...
```

## Acceptance criteria

### Code
- `main(argv)` is a pure dispatcher per `bal`'s `orchestrators route — they don't reason` rule:
  ```python
  parser = build_parser()
  args = parser.parse_args(argv)
  return COMMANDS[args.command](args)
  ```
  All business logic lives in the command modules.
- `build_parser()` registers subparsers for `exec`, `capabilities`, and a placeholder `sandbox` group that step 10/11/12 will extend (use `add_subparsers(required=True)`).
- Workspace inference (`resolve_workspace(args.workspace)`):
  - If `--workspace` provided → canonicalize via `os.path.realpath` and return.
  - Otherwise: walk from cwd upward looking for a `.bal/` directory; fall back to cwd.
  - Lives in a single helper (probably `bal_sbx/cli/workspace.py`) and is reused by every later command.
- `exec_cmd`:
  - Argparse uses `argparse.REMAINDER` for the command + args after `--`.
  - Builds a `SandboxManager()`, picks mode based on `--unsafe`.
  - For `--unsafe`: `manager.unsafe(workspace).exec_replace(cmd)`. Mode is also surfaced visually via `emit_unsafe_banner()` to stderr.
  - For sandboxed: `manager.launcher(workspace, SandboxMode.SAFE).exec_replace(cmd)`.
  - `exec_replace` never returns; the function therefore also never returns, and there is no `return 0` after it.
- `capabilities`:
  - Prints platform, sudo availability, ACL support, and `unsupported_reason` if any.
  - Returns 0.
- `cli/output.py` is the only place that calls `print` or writes to stdout/stderr — keeps command modules pure for testing.

### Tests
- `main([])` exits non-zero with a usage message (argparse default).
- `main(["capabilities"])` runs the command and returns 0; capture output and assert keys present.
- `main(["exec", "--", "echo", "hi"])` with a patched `SandboxManager` (injected via dependency override or by patching `bal_sbx.api.SandboxManager`) calls `exec_replace` on a `SandboxedLauncher`.
- `main(["exec", "--unsafe", "--", "echo", "hi"])` calls `exec_replace` on a `DirectLauncher` and emits the unsafe banner to stderr.
- `main(["exec", "--workspace", "/tmp/foo", "--", "true"])` resolves workspace to `/tmp/foo`.
- Workspace inference: in a `tmp_path` directory tree with a `.bal/` marker at the top, calling from a subdirectory returns the top.

## Notes / gotchas

- Use `argparse` from stdlib. The `coding_guide.md` forbids hand-rolled arg parsing.
- `os.execvp` does not return; structure `exec_cmd` so the static type checker does not require a `return` after it. Use `typing.NoReturn` on the helper that calls `exec_replace`.
- Dependency injection for tests: `main()` can accept an optional `manager_factory` parameter defaulting to `SandboxManager`. Tests pass in a factory that returns a manager constructed with `FakeSystemOps`.
- See plan.md A8 — after this step Phase 1 ships.
