# Step 14 — Lifecycle + launcher integration; remove `WorkspaceConfig`

## Goal

Make shared tools actually work end-to-end:

- `SandboxManager` resolves `global ⊕ per-sandbox` config on every
  `get_or_create` / `launcher` / `destroy`.
- `UserSandbox` accepts a `shared_tool_grants` sequence and reconciles
  per-tool ACLs at `create` / `repair` time, revokes them at `destroy`.
- `build_sandbox_env` accepts `extra_path_entries` and `extra_env` from the
  resolved tools.
- `WorkspaceConfig` is deleted; `bal-sbx sandbox env` writes the registry
  (per-sandbox or `--global`).
- Legacy `<ws>/.bal/config.json` `env` is auto-migrated into the registry
  on first `get_or_create`.

## Files created / modified

- `bal_sbx/core/paths.py`                    # remove `workspace_config_file`
- `bal_sbx/backends/user.py`                 # `ToolGrant`, reconcile loops
- `bal_sbx/backends/factory.py`              # pass `shared_tool_grants` through
- `bal_sbx/exec/environment.py`              # `extra_path_entries`, `extra_env`
- `bal_sbx/exec/launcher.py`                 # drop `workspace_config`; add `workspace_env`/`shared_tool_paths`/`shared_tool_env`
- `bal_sbx/api.py`                           # resolve tooling, migrate legacy, `update_config`
- `bal_sbx/cli/commands/sandbox.py`          # `env` writes registry; `--global` flag
- `bal_sbx/cli/main.py`                      # argparse `--global` on env
- `bal_sbx/config/__init__.py`               # drop `WorkspaceConfig` export
- `bal_sbx/config/workspace.py`              # **deleted**
- `tests/unit/config/test_workspace.py`      # **deleted**
- `tests/unit/exec/test_environment.py`      # extra_path_entries / extra_env precedence
- `tests/unit/exec/test_workspace_env_applied.py`  # migrated to registry-backed env
- `tests/unit/cli/test_sandbox_env.py`       # registry assertions + `--global` cases
- `tests/unit/core/test_paths.py`            # drop reference to deleted field
- `tests/unit/backends/test_user_sandbox_shared_tools.py`  # new
- `tests/unit/test_api_shared_tools.py`      # new

## Public surface introduced

```python
# bal_sbx/backends/user.py
class ToolGrant(NamedTuple):
    path: str
    permissions: frozenset[Permission]

class UserSandbox(Sandbox):
    def __init__(
        self,
        identity: SandboxIdentity,
        system_ops: SystemOps,
        shared_tool_grants: Sequence[ToolGrant] = (),
    ) -> None: ...
```

```python
# bal_sbx/api.py
class SandboxManager:
    def resolve_config(self, workspace_path: str) -> SandboxConfig: ...
    def update_config(
        self,
        workspace_path: str,
        mutate: Callable[[SandboxConfig], SandboxConfig],
    ) -> SandboxConfig: ...
```

```python
# bal_sbx/exec/environment.py
def build_sandbox_env(
    identity,
    overrides=None,
    workspace_env=None,
    denylist=DEFAULT_DENYLIST,
    base_path=DEFAULT_PATH,
    extra_path_entries: Sequence[str] = (),
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]: ...
```

```python
# bal_sbx/exec/launcher.py
class SandboxedLauncher:
    def __init__(
        self,
        sandbox, system_ops, registry,
        denylist=DEFAULT_DENYLIST,
        workspace_env: Mapping[str, str] | None = None,
        shared_tool_paths: Sequence[str] = (),
        shared_tool_env: Mapping[str, str] | None = None,
    ) -> None: ...
```

```bash
bal-sbx sandbox env [--workspace PATH | --global] [KEY [VALUE]] [--unset KEY]
```

## Acceptance criteria

### Code
- `SandboxManager.get_or_create(ws)` ensures a registry entry exists (creating
  a config-only entry from legacy `<ws>/.bal/config.json` env if present),
  resolves merged config, computes ACL grants filtered by host-path
  existence (warns via `warnings.warn` and skips missing paths), and passes
  the grants into `UserSandbox`. Calling it again after adding a tool to
  config re-grants the new path (self-healing).
- `UserSandbox.create` grants any expected (path, perms) whose ACL is not
  already present; skips when the existing ACL is a superset (e.g. full
  rights). Env-only grants (empty `permissions`) skip the ACL call.
- `UserSandbox.destroy` revokes shared-tool ACLs *before* the workspace ACL
  and user/home cleanup, using the currently-resolved grants. Failures are
  collected and re-raised as `SandboxBroken` only after best-effort cleanup
  of every step.
- `UserSandbox.status` returns `DANGLING_ACL` if any expected shared-tool
  ACL is missing; `repair` re-grants and reports `DANGLING_ACL` once (does
  not duplicate per missing path).
- `build_sandbox_env` PATH precedence: `extra_path_entries` prepended to
  `base_path`. Env precedence: defaults < `extra_env` < `workspace_env` <
  `overrides`. Identity keys remain at the defaults level.
- `SandboxedLauncher` takes `workspace_env` / `shared_tool_paths` /
  `shared_tool_env` as constructor args (no more `WorkspaceConfig`
  reference). Argv shape is unchanged.
- `bal-sbx sandbox env` operates on `registry.sandboxes[id].config.env` by
  default; `--global` switches to `registry.global` config. The legacy
  `<ws>/.bal/config.json` is never read or written by the new code path.
- `env` creates a config-only registry entry (no user/home/ACL provisioning).
- Legacy `<ws>/.bal/config.json` `env` is auto-copied into the registry on
  the next `get_or_create`. The old file is left in place — the user can
  delete it.

### Tests
- 12 new `test_environment.py` cases covering extra_path_entries empty/non-empty,
  extra_env vs workspace_env vs overrides precedence.
- 10 new `test_user_sandbox_shared_tools.py` cases covering grant on create,
  revoke on destroy, idempotency, subset preservation, repair, env-only
  tool skip, partial-failure tolerance.
- 8 new `test_api_shared_tools.py` cases covering global config grants,
  workspace overrides global per name, missing-path warning, PATH heuristic
  applied through the manager, destroy revokes, second-create self-heals.
- 6 new `test_sandbox_env.py` cases for `--global` flag and "no per-workspace
  file is created" assertion.
- 4 new `test_workspace_env_applied.py` cases for global env, global-vs-workspace
  override, fresh-launcher pickup, and legacy migration.
- Suite grows from 344 to 368.

## Notes / gotchas

- Tool env applies even when every tool path is missing — the user opted
  into the env set explicitly, and tool env is independent of ACL grants.
  Only the ACL grants and PATH entries depend on path existence.
- `SandboxedLauncher` no longer holds a `WorkspaceConfig` reference, so it
  no longer "reads fresh" on every exec. The launcher captures env at
  construction time; subsequent config changes require `manager.launcher()`
  to be called again. In production this is the natural flow
  (`bal-sbx run` builds one launcher per invocation); only the old "mutate
  after construction" test was relying on the freshness behavior.
- `update_config(ws, mutate)` always writes to the per-sandbox entry —
  creating a config-only entry if the sandbox has never been provisioned.
  Use the registry's `set_global_config` for the global section.
- The CLI command module reaches into `manager._registry.global_config()`
  for the `--global` env operations; a public surface for this lands in
  step 15 (`bal-sbx tools` subcommand wrappers).
- Migration helper `_load_legacy_workspace_env` is intentionally tolerant —
  malformed legacy files are skipped, not raised.
