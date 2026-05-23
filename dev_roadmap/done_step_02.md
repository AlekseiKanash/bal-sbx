# Step 02 — Core domain: identity, paths, errors

## Goal

Implement the pure-functional core of the package: deterministic sandbox identity, path layout, status enum, metadata dataclass, and the public exception hierarchy. No I/O, no subprocesses.

## Files created

- `bal_sbx/core/__init__.py`
- `bal_sbx/core/identity.py`
- `bal_sbx/core/paths.py`
- `bal_sbx/core/status.py`
- `bal_sbx/core/metadata.py`
- `bal_sbx/core/errors.py`
- `tests/unit/core/__init__.py`
- `tests/unit/core/test_identity.py`
- `tests/unit/core/test_paths.py`
- `tests/unit/core/test_metadata.py`

## Public surface introduced

```python
# bal_sbx/core/identity.py
class SandboxIdentity:
    id: str         # e.g. "bal_f81d4f"
    user: str       # same as id by default
    workspace: str  # canonicalized absolute path
    home: str       # absolute path to sandbox HOME
    workspace_link: str  # absolute path to .bal/workspace symlink

    @classmethod
    def from_workspace(cls, workspace_path: str, layout: PathLayout) -> "SandboxIdentity": ...

# bal_sbx/core/paths.py
@dataclass(frozen=True)
class PathLayout:
    home_root: str           # default: "/home" on Linux, "/Users" on macOS — but configurable
    registry_path: str       # default: ~/.bal/sandboxes.json
    workspace_config_dir: str = ".bal"     # relative to workspace
    workspace_config_file: str = ".bal/config.json"

    @classmethod
    def default(cls) -> "PathLayout": ...
    def home_for(self, identity_id: str) -> str: ...
    def workspace_link_for(self, identity_id: str) -> str: ...

# bal_sbx/core/status.py
class SandboxStatus(str, Enum):
    OK = "ok"
    MISSING_USER = "missing_user"
    MISSING_HOME = "missing_home"
    BROKEN_SYMLINK = "broken_symlink"
    MISSING_WORKSPACE = "missing_workspace"
    DANGLING_ACL = "dangling_acl"
    ORPHAN_HOME = "orphan_home"
    INVALID_METADATA = "invalid_metadata"

# bal_sbx/core/metadata.py
@dataclass
class SandboxMetadata:
    workspace: str
    created_at: str    # ISO 8601 UTC
    last_used_at: str
    agent: str | None = None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "SandboxMetadata": ...

# bal_sbx/core/errors.py
class BalSbxError(Exception): ...
class PrivilegeDenied(BalSbxError): ...
class SandboxNotFound(BalSbxError): ...
class SandboxBroken(BalSbxError): ...
class PlatformUnsupported(BalSbxError): ...
class RegistryCorrupt(BalSbxError): ...
```

## Acceptance criteria

### Code
- `SandboxIdentity.from_workspace` canonicalizes the path (`os.path.realpath`) before hashing.
- Hash: `hashlib.blake2s(canonical_path.encode(), digest_size=3).hexdigest()` → 6 hex chars → `bal_<hex>`. Document the choice in a module-level docstring (≤2 lines).
- `PathLayout.default()` chooses `home_root` based on `sys.platform` (`/Users` for darwin, `/home` for linux). On unsupported platforms, raise `PlatformUnsupported`.
- `SandboxMetadata.to_dict`/`from_dict` round-trip is lossless. ISO timestamps via `datetime.now(timezone.utc).isoformat()` — use stdlib only.
- All exception classes live in `core/errors.py`. They take a single string message; no extra fields yet.

### Tests
- Identity determinism: same workspace path → same ID across 100 invocations and across `~/foo` vs `/Users/me/foo` (after realpath).
- Identity uniqueness: 1000 random paths yield 1000 distinct IDs (collision probability sanity check, not a guarantee).
- `PathLayout.default()` returns the expected `home_root` per platform (patch `sys.platform`).
- `PathLayout.default()` raises `PlatformUnsupported` on `"win32"`.
- Metadata round-trip via `to_dict` / `from_dict`.
- Error hierarchy: every concrete error is a subclass of `BalSbxError`.

## Notes / gotchas

- Do **not** import anything from `bal_sbx/registry`, `system`, `backends`, or `exec` here — `core` is the leaf.
- `SandboxIdentity` is a frozen dataclass; comparing two identities from the same workspace must succeed with `==`.
- 6 hex chars = 16.7M possible IDs. Collisions are theoretically possible. The strategy doc accepts this; do not lengthen yet.
- `core/__init__.py` re-exports nothing — modules are imported by their full path (`from bal_sbx.core.identity import SandboxIdentity`).
- See plan.md A5 (centralized `PathLayout`) and A6 (errors are public contract).
