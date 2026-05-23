# Step 07 — Exec layer & launchers

## Goal

Implement the `AgentLauncher` Protocol and the two concrete launchers: `SandboxedLauncher` (wraps a `Sandbox`) and `DirectLauncher` (the `--unsafe` path). Build the clean-environment construction logic separately and test it exhaustively — this is where credentials would leak.

## Files created

- `bal_sbx/exec/__init__.py`
- `bal_sbx/exec/environment.py`
- `bal_sbx/exec/launcher.py`
- `tests/unit/exec/__init__.py`
- `tests/unit/exec/test_environment.py`
- `tests/unit/exec/test_sandboxed_launcher.py`
- `tests/unit/exec/test_direct_launcher.py`

## Public surface introduced

```python
# bal_sbx/exec/environment.py
DEFAULT_DENYLIST: tuple[str, ...] = (
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "HISTFILE",
)
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"

def build_sandbox_env(
    identity: SandboxIdentity,
    overrides: Mapping[str, str] | None = None,
    denylist: Iterable[str] = DEFAULT_DENYLIST,
    base_path: str = DEFAULT_PATH,
) -> dict[str, str]: ...

# bal_sbx/exec/launcher.py
class AgentLauncher(Protocol):
    def exec_replace(self, cmd: Sequence[str], env_overrides: Mapping[str, str] | None = None) -> NoReturn: ...
    def run(self, cmd: Sequence[str], env_overrides: Mapping[str, str] | None = None) -> int: ...

class SandboxedLauncher:
    def __init__(self, sandbox: Sandbox, system_ops: SystemOps, registry: JsonFileRegistry,
                 denylist: Iterable[str] = DEFAULT_DENYLIST): ...

class DirectLauncher:
    """The --unsafe path. No sandbox, no env scrubbing, no user switch."""
    def __init__(self): ...
```

## Acceptance criteria

### Code
- `build_sandbox_env`:
  - Starts from an **empty** dict (no host env inheritance).
  - Sets `HOME = identity.home`, `USER = identity.user`, `LOGNAME = identity.user`, `PATH = base_path`, `BAL_SANDBOX_ID = identity.id`, `BAL_SANDBOX_WORKSPACE = identity.workspace`.
  - Applies `overrides` last. Overrides may include keys that are also in `denylist` — that is the caller's decision (e.g. workspace config). The denylist applies to host env, which we are not inheriting; it stays in the signature for future host-env-bleed-through scenarios. Document this clearly in the module docstring.
- `SandboxedLauncher.exec_replace(cmd, env_overrides)`:
  1. Verify sandbox status; if not `OK`, raise `SandboxBroken`.
  2. `registry.touch(identity.id)` — stamp `last_used_at` before replacement.
  3. Build env via `build_sandbox_env`.
  4. Construct argv: `["sudo", "-u", identity.user, "-H", "env", "-i", *env_pairs, *cmd]`. `env -i` plus explicit pairs ensures a truly clean environment even after `sudo`. Document why.
  5. `os.execvp("sudo", argv)`.
- `SandboxedLauncher.run(cmd, env_overrides)`:
  - Same setup, but `subprocess.run(...)` returning `returncode`.
  - Does not raise on non-zero exit (let the caller decide).
- `DirectLauncher.exec_replace(cmd, env_overrides)`:
  - Inherits current env.
  - Applies `env_overrides`.
  - Prints `"MODE: UNSAFE"` to stderr (visibility requirement from the strategy doc).
  - `os.execvpe(cmd[0], cmd, env)`.
- `DirectLauncher.run(...)` mirrors `exec_replace` but uses `subprocess.run`.
- `AgentLauncher` is a `typing.Protocol` with `runtime_checkable=False`. The two concrete classes do not inherit from it — duck typing matches the protocol structurally.

### Tests
- `build_sandbox_env`:
  - Returns a dict that contains only the explicit keys (no `PWD`, no `LC_*`, etc.) unless added by overrides.
  - `BAL_SANDBOX_ID` and `BAL_SANDBOX_WORKSPACE` are always set.
  - Overrides override defaults.
  - Denylist behavior — when extending, ensure the denylist is iterable-safe (accepts list, tuple, set).
- `SandboxedLauncher.exec_replace`:
  - Refuses to launch if `sandbox.status() != OK` — asserts `SandboxBroken` raised.
  - Calls `registry.touch` before `os.execvp` (verify call order with a `MagicMock` recording calls).
  - Constructed argv includes `["sudo", "-u", identity.user, "-H", "env", "-i", ...]`.
- `SandboxedLauncher.run`:
  - Returns the subprocess exit code without raising on non-zero.
- `DirectLauncher.exec_replace`:
  - Writes `MODE: UNSAFE` to stderr (capture with `capsys`).
  - Calls `os.execvpe` with the correct argv and env.
- Both launchers conform to `AgentLauncher` structurally (`isinstance` not required; just call the methods through the protocol-typed reference in one test).

## Notes / gotchas

- The `env -i` after `sudo` is critical: without it, `sudo` may inherit a subset of host env even when invoked with `-i`. The double-clean approach (`sudo -i` would also work but rewrites HOME unexpectedly) is the safer choice. Document this.
- `os.execvp` vs `os.execvpe`: `execvp` uses the current env; we want full control, so launchers use `os.execvp("sudo", argv)` after `env -i` has scrubbed everything in argv form.
- See plan.md A2 (separate Sandbox from launcher), A3 (dual exec API), A7 (denylist as data).
