# bal-sbx Implementation Roadmap

This roadmap turns [`docs/bal_sandboxing_strategy.md`](../docs/bal_sandboxing_strategy.md) into self-contained implementation steps. Each step is a **vertical slice**: by the end of it, something is runnable and tested.

Scope of this roadmap: **Phase 1 (core sandbox) + Phase 2 (maintenance commands) + Phase 3 (shared host tools / unified config)** from the strategy doc. Phase 4 (network policies, stronger isolation) is out of scope.

## How to use this roadmap

Implement steps **in order**. Each `step_NN.md` file is self-contained — it states the goal, the exact files to create or modify, the public surface introduced, acceptance criteria, and any gotchas. A future session should be able to implement one step without re-reading the others, only this `plan.md` for orientation.

After every step:

1. `pytest` must pass.
2. The new public surface must work end-to-end through the public API (or CLI) introduced so far.
3. Any new exceptions/types must be exported from `bal_sbx/__init__.py`.

## Step status convention

A step's status is encoded in its filename prefix, so a directory listing or the index table below always reflects the truth — no separate tracker.

- `done_step_NN.md` — completed and verified.
- `in_progress_step_NN.md` — currently being worked on (at most one at a time).
- `open_step_NN.md`, `to_do_step_NN.md`, or no prefix (`step_NN.md`) — pending.

When a step transitions, both the filename and its link in the step index below are updated.

## Architectural decisions

Anchor decisions made during planning. Each step assumes these and references them by ID.

- **A1 — Capability composition, not platform monoliths.** Four providers (`UserProvisioner`, `AclManager`, `HomeLayout`, `PrivilegeBroker`) each with `linux` and `macos` implementations, bundled into a `SystemOps` value object.
- **A2 — `AgentLauncher` Protocol, not a fake `UnsafeSandbox`.** `SandboxedLauncher` wraps a `Sandbox`; `DirectLauncher` is plain `os.execvp` for `--unsafe`. `Sandbox` itself never has a no-op implementation.
- **A3 — Dual exec API.** `exec_replace(cmd, env) -> NoReturn` for production use and `run(cmd, env) -> int` for CLI/tests.
- **A4 — No Registry ABC (YAGNI).** A single `JsonFileRegistry`; tests use `tmp_path`. Introduce an ABC only when a second implementation is real.
- **A5 — Centralized `PathLayout`.** One module owns "where things live"; everything else accepts a `PathLayout`.
- **A6 — Errors and capabilities are public contract.** `core/errors.py` defines the exception taxonomy; `SandboxManager.capabilities()` returns a probe struct.
- **A7 — Env policy as data.** Denylist lives in `Settings`, not in code.
- **A8 — Vertical-slice steps.** Each step ends with something runnable; no "all of `system/` first, then all of `backends/`" horizontal slicing.

## Module layout (target end-state)

```
bal_sbx/
  __init__.py            api.py            __main__.py
  core/      identity.py  metadata.py  paths.py  status.py  errors.py
             shared_tools.py  config.py
  registry/  json_file.py
  system/    ops.py  home.py  privilege.py
             users/  base.py  linux.py  macos.py
             acl/    base.py  linux.py  macos.py
  backends/  base.py  user.py  factory.py
  exec/      launcher.py  environment.py
  config/    settings.py
  discovery/ tools.py
  cli/       main.py  output.py
             commands/  sandbox.py  exec.py  tools.py
tests/
  unit/      core/ registry/ system/ backends/ exec/ config/ cli/ discovery/
  conftest.py
```

## Step index

### Phase 1 — Core Sandbox

| # | Title | Goal |
|---|---|---|
| [01](done_step_01.md) | Project skeleton & tooling | `pip install -e .` and `pytest` work on an empty package. |
| [02](done_step_02.md) | Core domain: identity, paths, errors | Deterministic IDs, `PathLayout`, exception hierarchy, status enum, metadata dataclass. |
| [03](done_step_03.md) | JSON registry | `JsonFileRegistry` with atomic writes and corruption recovery. |
| [04](done_step_04.md) | System layer ABCs + fakes | Provider interfaces and the in-memory fakes used by every later test. |
| [05](done_step_05.md) | Platform implementations | Real Linux and macOS providers (`useradd`/`dscl`, `setfacl`/`chmod +a`). |
| [06](done_step_06.md) | `UserSandbox` backend | Full create → status → repair → destroy lifecycle. |
| [07](done_step_07.md) | Exec layer & launchers | `AgentLauncher` Protocol, `SandboxedLauncher`, `DirectLauncher`. |
| [08](done_step_08.md) | Public facade `SandboxManager` | The API `bal` will import. |
| [09](done_step_09.md) | CLI scaffold & `exec` | `bal-sbx exec -- <cmd>` and `bal-sbx capabilities`. |

**Phase 1 exit criteria:** `bal-sbx exec --workspace ./demo -- id -un` prints the sandbox username on Linux and macOS; `--unsafe` prints the host username; unit suite green.

### Phase 2 — Maintenance

| # | Title | Goal |
|---|---|---|
| [10](done_step_10.md) | `sandbox list` / `create` / `cd` | Inspection and explicit-creation commands. |
| [11](done_step_11.md) | `repair`, `cleanup`, stale detection | Every stale variant from the strategy doc is detected and recoverable. |
| [12](done_step_12.md) | Settings, workspace config, `env` command | Global + per-workspace configuration with documented precedence. |

**Phase 2 exit criteria:** `bal-sbx sandbox list` shows accurate per-sandbox status; `repair` and `cleanup` produce idempotent results; `sandbox env KEY VALUE` persists across sessions; settings precedence is CLI > workspace > global > defaults.

### Phase 3 — Shared host tools

| # | Title | Goal |
|---|---|---|
| [13](done_step_13.md) | Shared-tool data model + ACL subset + registry shape | `SharedTool`/`SandboxConfig`; ACLs accept a `read/write/execute` subset; registry gains `global` section + per-sandbox `config`; legacy shape auto-migrated on read. |
| [14](done_step_14.md) | Lifecycle + launcher integration; remove `WorkspaceConfig` | `SandboxManager` resolves global ⊕ per-sandbox config; `UserSandbox` reconciles shared-tool ACLs on `create`/`repair` and revokes on `destroy`; `build_sandbox_env` learns `extra_path_entries`/`extra_env`; `WorkspaceConfig` deleted; `env` CLI subcommands write the registry. |
| [15](done_step_15.md) | CLI `tools` + discovery | `bal-sbx tools discover/list/add/remove` with `--global|--sandbox|--workspace`; `tools remove` revokes ACLs before deleting config. |

**Phase 3 exit criteria:** A sandbox configured with `global.shared_tools.brew` can run `bal-sbx run -- brew --version` successfully on macOS; `bal-sbx tools discover --apply --global` populates the registry; `bal-sbx tools remove brew --global` revokes ACLs across all active sandboxes before deleting the config entry; per-sandbox dependencies (pip --user, npm) still install into the sandbox HOME, never the host.

## After the roadmap

Once Phase 3 is done, `bal` can adopt the library by replacing its `os.execvp(agent, ...)` call sites with:

```python
from bal_sbx import SandboxManager, SandboxMode
launcher = SandboxManager().launcher(workspace, mode=mode)
launcher.exec_replace([agent, *args], env_overrides=env)
```

Wiring that into `bal` is **not** part of this roadmap; `bal` is read-only for this project.
