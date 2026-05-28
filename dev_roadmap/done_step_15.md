# Step 15 — `bal-sbx tools` CLI + host-tool discovery

## Goal

User-facing surface for the shared-tools feature:

- `bal-sbx tools list / add / remove` to manage the registry's
  `global.shared_tools` and `sandboxes[id].config.shared_tools` sections.
- `bal-sbx tools discover` to detect host-installed tools (brew, node,
  python 3.11/3.12/3.13, cargo, go) and print a JSON snippet — or with
  `--apply`, write them straight into the chosen scope.
- `tools remove` revokes ACLs *before* deleting the config entry. Removing
  from `--global` only revokes on sandboxes that don't override the tool by
  name in their per-sandbox config.

## Files created / modified

- `bal_sbx/discovery/__init__.py`                  # new package
- `bal_sbx/discovery/tools.py`                     # detector registry
- `bal_sbx/cli/commands/tools.py`                  # subcommand handlers
- `bal_sbx/cli/main.py`                            # register `tools`
- `tests/unit/discovery/__init__.py`               # new
- `tests/unit/discovery/test_tools.py`             # detector tests
- `tests/unit/cli/test_tools.py`                   # subcommand tests
- `tests/unit/cli/test_main.py`                    # update RESERVED/COMMANDS assertion

## Public surface introduced

```python
# bal_sbx/discovery/tools.py
class Detector(Protocol):
    name: str
    def detect(self) -> SharedTool | None: ...

class BrewDetector: ...
class NodeDetector: ...
class PythonDetector:
    def __init__(self, version: str): ...     # e.g. "3.11"
class CargoDetector: ...
class GoDetector: ...

DEFAULT_DETECTORS: tuple[Detector, ...] = (
    BrewDetector(),
    NodeDetector(),
    PythonDetector("3.11"),
    PythonDetector("3.12"),
    PythonDetector("3.13"),
    CargoDetector(),
    GoDetector(),
)

def discover_tools(
    detectors: tuple[Detector, ...] = DEFAULT_DETECTORS,
) -> dict[str, SharedTool]: ...
```

CLI:

```
bal-sbx tools list      [--workspace PATH | --sandbox ID | --global]
bal-sbx tools add NAME  --path P [--path P ...] --perm read --perm execute
                        [--env KEY=VAL ...]
                        [--workspace PATH | --sandbox ID | --global]
bal-sbx tools remove NAME [--workspace PATH | --sandbox ID | --global]
bal-sbx tools discover  [--apply [--workspace PATH | --sandbox ID | --global]]
```

## Acceptance criteria

### Code
- Detectors carry their own platform check inside `detect()` (A1 — branching
  at the edges, not centralized). `BrewDetector` probes
  `/opt/homebrew/bin/brew` first, then `/usr/local/bin/brew`; emits
  `HOMEBREW_PREFIX` env and the relevant `Cellar`/`opt` sibling paths when
  they exist.
- `PythonDetector(version)` produces tool name `python{version_no_dots}`
  (e.g. `python311`).
- Discovered tools never carry `Permission.WRITE` — the user must compose a
  writable entry manually via `tools add`.
- `tools list` / `add` / `remove` accept `--global`, `--sandbox ID`, or
  `--workspace PATH`; if none of the three are given, the workspace is
  resolved from the cwd (matching `sandbox env`).
- `tools add` calls `SandboxManager.update_config(workspace, ...)`, which
  creates a config-only registry entry if the sandbox was never provisioned
  — symmetric with `sandbox env`.
- `tools remove --global` finds every sandbox whose per-sandbox config does
  *not* override the tool by name, and revokes those sandboxes' ACLs on the
  global tool's paths before deleting the global entry.
- `tools remove --workspace PATH` (or `--sandbox ID`) revokes only that
  sandbox's ACLs for the tool's paths and deletes only its per-sandbox
  entry.
- `tools discover` without `--apply` prints a `{"shared_tools": {...}}`
  JSON snippet the user can copy-paste; with `--apply` writes into the
  chosen scope (defaulting to the cwd workspace).
- `tools list` output renders permissions in canonical order
  (read → write → execute → env), not alphabetical.
- `SharedTool` validation (from step 13) is the single source of truth for
  permission combinations — the CLI surfaces `ConfigInvalid` for e.g.
  `--perm execute` without `--perm read`.

### Tests
- 14 detector cases covering Apple Silicon vs Intel brew prefix, missing
  siblings (Cellar/opt), node/python/go via `shutil.which`, cargo via
  `expanduser`, the aggregator filtering `None` results, and the default-no-write
  invariant.
- 14 CLI cases covering list (empty + global after add), add (global,
  per-sandbox, invalid env, invalid perms), remove (global revoke, global
  skip-when-overridden, per-sandbox revoke, unknown tool), discover (JSON
  snippet, apply to global, apply to workspace, no-tools-message).
- Suite grows from 368 to 396.

## Notes / gotchas

- The CLI module uses `manager._registry` / `manager._system_ops` directly
  for the `--global` operations. A public surface lives in step-13's
  `JsonFileRegistry.global_config()` / `set_global_config()`; the
  command module also calls `manager.update_config(...)` for the
  per-sandbox path. No new public API was needed.
- `tools remove --global` warns (does not fail) on individual ACL revoke
  failures so that one broken sandbox doesn't block cleanup across the
  whole fleet.
- `tools add` uses `argparse` `choices` on `--perm` for early validation,
  but the cross-permission rule ("`execute` requires `read`") is enforced
  by `SharedTool.__post_init__` and propagated as `ConfigInvalid`.
- `discover_tools()` builds its dict by detector return order; later
  detectors overwrite earlier ones if they share a name (none of the
  defaults do).
- The `Detector` Protocol is structural — implementing a custom detector
  is "just" a class with a `name` attribute and a `detect()` method
  returning a `SharedTool` or `None` (A4 — no ABC).
