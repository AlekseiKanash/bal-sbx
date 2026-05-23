# Step 12 — Settings, workspace config, `env` command

## Goal

Introduce configuration with explicit precedence (CLI > workspace > global > defaults) and the `bal-sbx sandbox env KEY [VALUE]` command for managing persistent per-workspace environment variables. Wire workspace env into the launcher so agents receive it on exec.

## Files created / modified

- `bal_sbx/config/__init__.py`
- `bal_sbx/config/settings.py`            # global settings: ~/.bal/sbx.toml
- `bal_sbx/config/workspace.py`           # per-workspace: <workspace>/.bal/config.json
- `bal_sbx/cli/commands/sandbox.py`       # implement `cmd_env`
- `bal_sbx/exec/launcher.py`              # apply workspace env at launch time
- `bal_sbx/api.py`                        # SandboxManager accepts Settings
- `tests/unit/config/__init__.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/config/test_workspace.py`
- `tests/unit/cli/test_sandbox_env.py`
- `tests/unit/exec/test_workspace_env_applied.py`

## Public surface introduced

```bash
bal-sbx sandbox env                  # list all keys for current workspace
bal-sbx sandbox env KEY              # get value (or empty + exit 1 if unset)
bal-sbx sandbox env KEY VALUE        # set value
bal-sbx sandbox env --unset KEY      # remove value
```

```python
# bal_sbx/config/settings.py
@dataclass(frozen=True)
class Settings:
    privilege_mode: str = "cached"          # "cached" | "per_operation"
    env_denylist: tuple[str, ...] = DEFAULT_DENYLIST
    registry_path: str | None = None        # None = PathLayout default

    @classmethod
    def load(cls, path: str | None = None) -> "Settings": ...

# bal_sbx/config/workspace.py
class WorkspaceConfig:
    def __init__(self, workspace: str, layout: PathLayout): ...
    def env(self) -> dict[str, str]: ...
    def set_env(self, key: str, value: str) -> None: ...
    def unset_env(self, key: str) -> None: ...

# bal_sbx/api.py
class SandboxManager:
    def __init__(self, ..., settings: Settings | None = None): ...
```

## Acceptance criteria

### Code
- `Settings.load`:
  - Reads `path` (default: `~/.bal/sbx.toml`).
  - Missing file → returns defaults.
  - Uses `tomllib` (stdlib, Python 3.11+). No third-party TOML.
  - Unknown keys raise `RegistryCorrupt(f"unknown setting: {key}")` (reusing the existing error type — or define a fresh `ConfigInvalid` if the semantic differs enough; if so, add to the exception hierarchy and export).
- `WorkspaceConfig`:
  - File: `<workspace>/.bal/config.json`. Created on first write.
  - `env()` returns a fresh dict each call (no shared references).
  - `set_env` / `unset_env` rewrite atomically (same temp+rename pattern as the registry).
  - Reading a missing file returns an empty config.
- `SandboxManager.__init__(settings=...)`:
  - When `settings` is `None`, calls `Settings.load()`.
  - Uses `settings.privilege_mode` to pick the `PrivilegeBroker` if `system_ops` is not provided.
  - Uses `settings.env_denylist` when constructing launchers.
- `SandboxedLauncher` now accepts the workspace config:
  - `launcher = manager.launcher(workspace)` resolves the `WorkspaceConfig` from the workspace path.
  - At exec time, env precedence (in `build_sandbox_env`): defaults < workspace env < `env_overrides`.
- `cmd_env`:
  - No args → list keys/values.
  - One arg → get; missing key prints empty and exits 1.
  - Two args → set.
  - `--unset KEY` → remove.

### Tests
- `Settings.load` from a tmp TOML file with each field set; defaults when file missing.
- `Settings.load` raises on unknown keys.
- `WorkspaceConfig` round-trip: `set_env`, then a fresh instance returns the value.
- `WorkspaceConfig` atomic write: patch `os.replace` to raise → file untouched.
- `SandboxManager` constructed with a `Settings(privilege_mode="per_operation")` selects `SudoPerOpBroker` when auto-detecting.
- `SandboxedLauncher` exec: workspace env appears in the constructed argv; CLI overrides win over workspace, which wins over defaults (the three-tier precedence test is the centerpiece).
- `cmd_env` covers list / get / set / unset paths.

## Notes / gotchas

- `tomllib` is read-only in stdlib. For writing settings programmatically (if ever needed), choose `tomli-w` only if a real requirement appears — for now `Settings` is read-only at runtime.
- `WorkspaceConfig` writes JSON, not TOML — matches the workspace-config example in the strategy doc and keeps the dependency surface small.
- Precedence rule (CLI > workspace > global > defaults) is asserted in **one** integration-style test that exercises all four layers — do not let it drift across modules.
- See plan.md A7 — env policy is data.
