# Step 10 — `sandbox list` / `create` / `cd`

## Goal

Expose the inspection and explicit-creation surface of the sandbox model through the CLI. These commands are direct delegates to `SandboxManager` and `Sandbox` methods that already exist.

## Files created / modified

- `bal_sbx/cli/commands/sandbox.py`      # shared module — list, create, cd, env (env stub for step 12)
- `bal_sbx/cli/output.py`                # extend with table-rendering helpers
- `bal_sbx/cli/main.py`                  # register `sandbox` subparser group
- `tests/unit/cli/test_sandbox_list.py`
- `tests/unit/cli/test_sandbox_create.py`
- `tests/unit/cli/test_sandbox_cd.py`

## Public surface introduced

```bash
bal-sbx sandbox list
bal-sbx sandbox create [--type user] [--workspace PATH]
bal-sbx sandbox cd [--workspace PATH]
```

## Acceptance criteria

### Code
- `sandbox.py` is a single module with one function per subcommand (`cmd_list`, `cmd_create`, `cmd_cd`, plus stubs for `cmd_repair`, `cmd_cleanup`, `cmd_env` that raise `NotImplementedError` until steps 11–12).
- `cmd_list`:
  - Calls `manager.list()`.
  - Renders a fixed-width table via `cli/output.py`:
    ```
    ID         WORKSPACE                  STATUS         LAST USED
    bal_f81d4f /Users/me/work/foo         ok             2026-05-23T13:15:00Z
    bal_a1b2c3 /Users/me/work/bar         broken_symlink 2026-05-22T09:00:00Z
    ```
  - Empty registry → prints "No sandboxes registered." and returns 0.
- `cmd_create`:
  - Resolves workspace (reuses the helper from step 09).
  - Calls `manager.get_or_create(workspace, kind=args.type)`.
  - Prints a one-line success message including ID, user, HOME path.
  - Returns 0.
- `cmd_cd`:
  - Resolves workspace.
  - Asserts the sandbox exists (look up via registry); if not → exit 2 with `SandboxNotFound: run 'bal-sbx sandbox create' first`.
  - Calls `sandbox.enter()` — `os.execvp` replaces the process with an interactive shell.
- Table rendering lives in `cli/output.py` as `emit_sandbox_table(rows)` — accepts a list of (identity, metadata, status) tuples.

### Tests
- `cmd_list` with empty registry prints the "No sandboxes" line.
- `cmd_list` with two entries renders both rows in `last_used_at` desc order.
- `cmd_create` calls `get_or_create` with the correct workspace and kind, returns 0.
- `cmd_create` with unknown kind (`--type docker`) — argparse rejects it (use `choices=["user"]`) or `manager.get_or_create` raises `ValueError`; either way exit is non-zero.
- `cmd_cd` raises a clean error when the sandbox is absent.
- `cmd_cd` calls `sandbox.enter()` (verified by patching `os.execvp`).
- Output formatting: golden test for `emit_sandbox_table` with two known rows.

## Notes / gotchas

- Do **not** import `rich`, `tabulate`, or `prettytable`. Fixed-width text via `str.ljust` is sufficient and matches the rest of the project's stdlib-only stance.
- The `--type` flag accepts only `"user"` until Phase 3 introduces Docker. argparse `choices=["user"]` is the right place to enforce this.
- `sandbox cd` deliberately does not pass `cmd[]` — it always launches a login shell. If users want to run a one-off command, they use `bal-sbx exec`.
