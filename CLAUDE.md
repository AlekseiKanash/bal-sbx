# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`bal-sbx` is UNIX-native sandboxing for AI coding agents. It runs an agent as a dedicated per-workspace UNIX user with an isolated `$HOME` and ACL-scoped access to the workspace only. It is **not** a container — there are no namespaces, no cgroups, no kernel-level isolation. The threat model is **credential isolation**, not hostile-code containment (`README.md:162-176`).

Ships as both a Python library (consumed by the sibling `bal` project) and a `bal-sbx` CLI.

Status: early development. Currently implementing Phase 1 + Phase 2 of `docs/bal_sandboxing_strategy.md` per `dev_roadmap/plan.md` — steps 1-12 are done.

## Development commands

```bash
pip install -e ".[dev]"     # install with pytest + ruff
pytest                       # full unit suite
pytest tests/unit/cli/test_sandbox_env.py::test_name   # single test
ruff check .                 # lint (line-length 120, target py311)
```

The package entry point is `bal-sbx = "bal_sbx.cli.main:main"`. `python -m bal_sbx` also works.

`setuptools-scm` generates `bal_sbx/_version.py` from git tags; it is gitignored.

## Architecture

### The big picture

`SandboxManager` (`bal_sbx/api.py`) is **the only public class** — everything under `bal_sbx` other than what `__init__.py` re-exports is implementation detail. Production callers do:

```python
launcher = SandboxManager().launcher(workspace, mode=SandboxMode.SAFE)
launcher.exec_replace([agent, *args], env_overrides=env)
```

The manager composes a `SystemOps` (platform providers), a `JsonFileRegistry` (sandbox metadata), and a `PathLayout` (where things live). Every constructor argument has a production default; tests pass fakes.

### Layered modules

- `core/` — pure data + policy, no I/O. `SandboxIdentity` (deterministic `bal_<blake2s-3>` from `realpath(workspace)`), `PathLayout` (A5 — one module owns paths), `SandboxStatus` enum, `SandboxMetadata`, exception taxonomy in `errors.py`, `staleness.detect_stale`.
- `registry/` — `JsonFileRegistry` with atomic writes + corruption recovery. **No ABC** (A4 — single impl until a second one is real).
- `system/` — four providers (A1 — capability composition, not platform monoliths):
  - `users/` (`UserProvisioner`: linux=`useradd`, macos=`dscl`)
  - `acl/` (`AclManager`: linux=`setfacl`, macos=`chmod +a`)
  - `home.py` (`HomeLayout`)
  - `privilege.py` (`PrivilegeBroker`: `SudoBroker` cached or `SudoPerOpBroker`)
  - `ops.py` bundles them into `SystemOps`; `SystemOps.detect()` is the only place that branches on `sys.platform`.
- `backends/` — `Sandbox` ABC + `UserSandbox` impl + `build_sandbox` factory. **No no-op sandbox** (A2): unsafe is handled by a separate launcher, not a fake backend.
- `exec/` — `AgentLauncher` Protocol (structural, not inheritance). Two impls:
  - `SandboxedLauncher` produces argv `["sudo", "-u", user, "-H", "env", "-i", *KEY=VAL, *cmd]`. The redundant `env -i` after `sudo -H` is intentional — sudoers can leak host env even with `-H`, so we scrub explicitly (`exec/launcher.py:7-15`).
  - `DirectLauncher` is the `--unsafe` path: plain `os.execvp`, prints `MODE: UNSAFE` to stderr.
  - Dual API (A3): `exec_replace(cmd, env) -> NoReturn` for prod, `run(cmd, env) -> int` for CLI/tests.
  - `environment.build_sandbox_env` builds env from scratch — host env is never inherited.
- `config/` — `Settings` (global TOML `~/.bal/sbx.toml`), `WorkspaceConfig` (per-workspace `.bal/config.json`). Precedence: CLI > workspace > global > defaults.
- `cli/` — `main.py` is a pure dispatcher (argv → `COMMANDS[name](args, factory)`). Business logic lives in `cli/commands/*`. Tests inject a `manager_factory` returning a manager built with `FakeSystemOps`.

### Architectural anchors (from `dev_roadmap/plan.md`)

These are the load-bearing decisions — keep them in mind before refactoring:

- **A1** Capability composition: four providers × two platforms, bundled by `SystemOps`. Don't introduce a `LinuxSandbox`/`MacosSandbox` monolith.
- **A2** No no-op `UnsafeSandbox`. Unsafe = `DirectLauncher`, not a fake `Sandbox`.
- **A3** Dual exec API: `exec_replace` and `run`.
- **A4** No `Registry` ABC until a second backend is real.
- **A5** All paths flow through `PathLayout`; no hardcoded `/home/...` outside `paths.py` and `home.py`.
- **A6** `core/errors.py` is public contract; `SandboxManager.capabilities()` is the probe struct.
- **A7** Env denylist lives in `Settings`, not in code.
- **A8** Vertical-slice steps — every roadmap step ends with something runnable.

## Testing conventions

- Unit tests live in `tests/unit/<subpackage>/`. The mirror-the-source layout is intentional.
- `tests/conftest.py` exposes a `fake_system_ops` fixture from `tests/unit/system/fakes.py`. The fakes (`FakeUserProvisioner`, `FakeAclManager`, `FakeHomeLayout`, `NullPrivilegeBroker`) are the standard substitute for the real system layer — **pytest never invokes real `sudo`, `useradd`, or `setfacl`**.
- Tests assert on outcomes (was the user created? does `status()` return OK?), not on which mock method was called.
- CLI tests inject a `manager_factory` into `main(argv, manager_factory=...)` so the full dispatch path is exercised without touching the filesystem.

## Roadmap-driven development

Work is structured as 12 self-contained vertical-slice steps in `dev_roadmap/`. The filename prefix is the source of truth for status:

- `done_step_NN.md` — completed and verified
- `in_progress_step_NN.md` — currently active (at most one)
- `step_NN.md` / `open_step_NN.md` / `to_do_step_NN.md` — pending

When a step transitions, rename the file **and** update the index table in `plan.md`. Each step file is self-contained: it states goal, files to touch, public surface, acceptance criteria. A future session should be able to do a step by reading only `plan.md` + that one step file.

After every step: `pytest` must pass, the new surface must work end-to-end via the public API/CLI, and any new exceptions/types must be exported from `bal_sbx/__init__.py`.

There is a `roadmap.next-step` skill and an MCP server (`.mcp.json`) for navigating the roadmap programmatically.

## Style rules (from `README.md:231-238` and the sibling `bal` project's `coding_guide.md`)

- PEP 8, line length 120, functions roughly 20–30 lines.
- OOP with SOLID; no global state; no single-caller wrappers.
- Prefer the standard library. New dependencies require explicit justification.
- Tests assert on outcomes, not on mock-call accounting.

## Things to know before editing

- Sibling project `../bal` is **read-only** from this repo. The library is designed for `bal` to adopt but does not import or modify it.
- `sys.platform` branching belongs in `SystemOps.detect()` and `PathLayout.default()` only. Backends, launchers, and the CLI are platform-agnostic.
- The sandbox identity is `bal_` + `blake2s(realpath(workspace), digest_size=3).hexdigest()` — short, stable, deterministic. Don't change the hashing without thinking about migration of existing registries.
- `SandboxedLauncher._argv` shape is load-bearing for security; the `env -i` after `sudo -H` is not redundant despite appearances.
