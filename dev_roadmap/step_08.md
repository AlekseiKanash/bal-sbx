# Step 08 — Public facade `SandboxManager`

## Goal

Wrap everything built so far behind a single class that `bal` will import. Define the public top-level exports and the `__main__` entry that delegates to the CLI.

## Files created / modified

- `bal_sbx/api.py`
- `bal_sbx/__init__.py`     # populate exports
- `bal_sbx/__main__.py`     # delegate to `cli.main` (which arrives in step 09 — placeholder stub here that raises a clear error)
- `tests/unit/test_api.py`
- `tests/unit/test_public_exports.py`

## Public surface introduced

```python
# bal_sbx/__init__.py
from bal_sbx.api import SandboxManager, SandboxMode, Capabilities
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.status import SandboxStatus
from bal_sbx.core import errors

__all__ = [
    "SandboxManager", "SandboxMode", "Capabilities",
    "SandboxIdentity", "SandboxMetadata", "SandboxStatus",
    "errors",
]

# bal_sbx/api.py
class SandboxMode(str, Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"

@dataclass(frozen=True)
class Capabilities:
    platform: str               # "linux" | "darwin" | "unsupported"
    can_sudo: bool
    acl_supported: bool
    unsupported_reason: str | None

class SandboxManager:
    def __init__(self, system_ops: SystemOps | None = None,
                 registry: JsonFileRegistry | None = None,
                 path_layout: PathLayout | None = None,
                 privilege_mode: str = "cached"): ...

    def capabilities(self) -> Capabilities: ...
    def resolve(self, workspace_path: str) -> SandboxIdentity: ...
    def get_or_create(self, workspace_path: str, kind: str = "user") -> Sandbox: ...
    def launcher(self, workspace_path: str, mode: SandboxMode = SandboxMode.SAFE) -> AgentLauncher: ...
    def unsafe(self, workspace_path: str) -> AgentLauncher: ...   # convenience for SandboxMode.UNSAFE
    def list(self) -> list[tuple[SandboxIdentity, SandboxMetadata, SandboxStatus]]: ...
    def destroy(self, workspace_path: str) -> None: ...
```

## Acceptance criteria

### Code
- `SandboxManager.__init__` injects defaults when arguments are `None`:
  - `path_layout = PathLayout.default()`
  - `system_ops = SystemOps.detect(privilege_mode)` (only attempted if not provided; failures raise immediately).
  - `registry = JsonFileRegistry(path_layout.registry_path)`.
- All public methods accept absolute or relative workspace paths and canonicalize internally via `SandboxIdentity.from_workspace`.
- `capabilities()`:
  - `platform = sys.platform`.
  - `can_sudo = system_ops.privilege.is_available()`.
  - `acl_supported = system_ops.acl.is_supported()`.
  - `unsupported_reason = SystemOps.unsupported_reason()`.
- `resolve()` is side-effect-free.
- `get_or_create()`:
  - Builds identity.
  - Constructs sandbox via `build_sandbox(kind, identity, system_ops)`.
  - Calls `sandbox.create()` (idempotent).
  - Updates registry: if entry exists, `touch`; otherwise `put` a fresh `SandboxMetadata`.
  - Returns the sandbox.
- `launcher(workspace, mode)`:
  - `SAFE` → calls `get_or_create` and returns `SandboxedLauncher`.
  - `UNSAFE` → returns `DirectLauncher` (no sandbox created, no registry touch).
- `unsafe(workspace)` is a one-liner: `return self.launcher(workspace, mode=SandboxMode.UNSAFE)`. **No additional logic** — confirms the "no single-caller wrapper" rule by being a true syntactic shorthand.
- `list()` walks the registry and pairs each entry with a fresh status check via `UserSandbox.status()`. Returns sorted by `last_used_at` desc.
- `destroy(workspace)`:
  - If sandbox is not in registry → raise `SandboxNotFound`.
  - Build sandbox, call `destroy()`, remove registry entry.

### Tests
- `Capabilities` round-trip: construct a manager with `FakeSystemOps` and verify each field.
- `resolve()` is deterministic and side-effect-free (registry unchanged after 100 calls).
- `get_or_create()` is idempotent at the manager level: two calls produce one registry entry.
- `launcher(SAFE)` returns a `SandboxedLauncher`; `launcher(UNSAFE)` returns a `DirectLauncher`.
- `list()` returns entries sorted by `last_used_at` desc.
- `destroy()` removes the registry entry and tears down via `FakeSystemOps`.
- Public exports test: `import bal_sbx; for name in bal_sbx.__all__: assert hasattr(bal_sbx, name)`.

## Notes / gotchas

- `SandboxManager` is the **only** public class — the rest of `bal_sbx` is implementation. Document this in the module docstring.
- The constructor's `system_ops`-or-detect logic exists for one reason: tests inject fakes. Production code never passes `system_ops` directly. Document this.
- `__main__.py` should be:
  ```python
  from bal_sbx.cli.main import main
  raise SystemExit(main())
  ```
  This will fail until step 09 lands `cli/main.py`. Acceptable — `pytest` does not import `__main__`.
- See plan.md A2, A6.
