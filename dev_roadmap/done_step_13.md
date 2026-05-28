# Step 13 — Shared tools data model, ACL subset grants, registry shape

## Goal

Lay the foundations for the unified-sandbox-config feature (see
`docs/bal_sandboxing_strategy.md` Phase 3 — shared host tools): a `SharedTool`
+ `SandboxConfig` data model, ACL grants that accept a subset of
`read/write/execute`, and a new registry file shape with a top-level `global`
section plus per-sandbox `config` overrides. No behavior changes yet —
`UserSandbox` and the launcher are wired in step 14.

## Files created / modified

- `bal_sbx/core/shared_tools.py`           # `SharedTool`, `Permission`, `parse_shared_tool`
- `bal_sbx/core/config.py`                 # `SandboxConfig`
- `bal_sbx/core/metadata.py`               # `SandboxMetadata.config`
- `bal_sbx/registry/json_file.py`          # new shape + structural migration + `global_config()`
- `bal_sbx/system/acl/base.py`             # extended ABC signatures
- `bal_sbx/system/acl/macos.py`            # subset rights translation
- `bal_sbx/system/acl/linux.py`            # subset rights translation
- `bal_sbx/__init__.py`                    # export `SharedTool`, `Permission`, `SandboxConfig`
- `tests/unit/system/fakes.py`             # `FakeAclManager.permissions`
- `tests/unit/core/test_shared_tools.py`
- `tests/unit/core/test_config.py`
- `tests/unit/registry/test_json_file.py`  # new-shape, legacy-migration, global-config
- `tests/unit/system/test_macos_acl.py`    # subset cases
- `tests/unit/system/test_linux_acl.py`    # subset cases

## Public surface introduced

```python
# bal_sbx/core/shared_tools.py
class Permission(str, Enum):
    READ = "read"; EXECUTE = "execute"; WRITE = "write"; ENV = "env"

@dataclass(frozen=True)
class SharedTool:
    name: str
    paths: tuple[str, ...]
    permissions: frozenset[Permission]
    env: Mapping[str, str]

    @property
    def acl_permissions(self) -> frozenset[Permission]: ...
    def path_entries(self) -> list[str]: ...
    def to_dict(self) -> dict: ...

def parse_shared_tool(name: str, data: Mapping) -> SharedTool: ...
```

```python
# bal_sbx/core/config.py
@dataclass(frozen=True)
class SandboxConfig:
    env: Mapping[str, str]
    shared_tools: Mapping[str, SharedTool]

    @classmethod
    def from_dict(cls, data: Mapping | None) -> "SandboxConfig": ...
    def to_dict(self) -> dict: ...
    def merged_with(self, override: "SandboxConfig") -> "SandboxConfig": ...
```

```python
# bal_sbx/core/metadata.py
@dataclass
class SandboxMetadata:
    ...
    config: SandboxConfig = field(default_factory=SandboxConfig)
```

```python
# bal_sbx/system/acl/base.py
class AclManager(ABC):
    def grant(self, path, username, permissions: frozenset[Permission] | None = None): ...
    def revoke(self, path, username, permissions: frozenset[Permission] | None = None): ...
    def is_granted(self, path, username, permissions: frozenset[Permission] | None = None) -> bool: ...
```

```python
# bal_sbx/registry/json_file.py
class JsonFileRegistry:
    def global_config(self) -> SandboxConfig: ...
    def set_global_config(self, cfg: SandboxConfig) -> None: ...
```

On-disk shape:

```json
{
  "global":    { "env": {...}, "shared_tools": {...} },
  "sandboxes": { "<id>": {<metadata.to_dict>}, ... }
}
```

## Acceptance criteria

### Code
- `SharedTool.__post_init__` rejects empty name, empty paths, non-absolute paths,
  empty permissions, and `EXECUTE`/`WRITE` without `READ`. `env` field has no
  permission gating — always honored when present.
- `path_entries()` is a pure string heuristic: a path is included iff it (a)
  ends in `/bin` or (b) its parent ends in `/bin`. Dedupes while preserving
  order.
- `SandboxConfig.merged_with` replaces per env key and per tool name (no deep
  merge).
- `AclManager.grant/revoke/is_granted` accept an optional `permissions`
  subset. `None` preserves today's full-rights behavior, so the existing
  workspace ACL call in `UserSandbox.create()` is unchanged.
- macOS rights translation: `_PERMISSION_RIGHTS` maps `READ`/`EXECUTE`/`WRITE`
  into slices of the canonical right set; subset output preserves canonical
  order so tests can assert exact strings.
- Linux rights translation: subset maps to `r`/`w`/`x` in that order.
- `JsonFileRegistry` writes the new `{global, sandboxes}` shape. Reads
  structurally detect the legacy `{<id>: metadata}` shape (no `global` or
  `sandboxes` key) and migrate in-memory; next `_save` rewrites to the new
  shape.
- `SandboxMetadata.to_dict` omits `config` when empty (back-compat for any
  hand-edited registry).

### Tests
- `tests/unit/core/test_shared_tools.py` — 24 cases covering validation,
  PATH heuristic, round-trip, and parser edge cases.
- `tests/unit/core/test_config.py` — 11 cases covering construction,
  round-trip, validation, and `merged_with` semantics.
- `tests/unit/registry/test_json_file.py` — adds global-config round-trip,
  per-sandbox-config round-trip, legacy-shape migration, and on-disk-format
  assertion.
- `tests/unit/system/test_macos_acl.py` — adds `_rights_for` subset cases,
  `grant`/`revoke`/`is_granted` with subsets, and superset-check semantics.
- `tests/unit/system/test_linux_acl.py` — adds `_rights_for` letter
  composition, `grant`/`revoke` with subsets, and superset semantics on
  `is_granted`.
- All 282 pre-existing tests still pass; suite grows to 344.

## Notes / gotchas

- `FakeAclManager` keeps its legacy `.grants: dict[path, set[user]]` shape
  for back-compat with `tests/unit/test_api.py` and
  `tests/unit/cli/test_sandbox_repair.py`; the new permission tracking lives
  in a parallel `.permissions: dict[(path,user), frozenset[Permission]|None]`.
- macOS `_rights_for` falls back to `_FULL_RIGHTS` when given only `ENV` (or
  an empty set). `SharedTool` validation prevents the case from occurring
  in production, but the defensive default ensures we never emit an empty
  rights string to `chmod`.
- Linux `revoke` calls `setfacl -x` which targets the principal regardless
  of rights — the new `permissions` kwarg is accepted but does not change
  the argv.
- No `version` key in the registry file — shape is detected structurally
  by the presence of `global`/`sandboxes` keys at the top level.
- `SandboxConfig` and `SharedTool` are now part of `bal_sbx.__all__`; future
  steps consume them.
