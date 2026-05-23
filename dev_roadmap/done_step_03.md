# Step 03 — JSON registry

## Goal

Implement persistent sandbox tracking at `~/.bal/sandboxes.json`. A single concrete class (`JsonFileRegistry`) handles load/save/get/put/delete/list with atomic writes and corruption recovery.

## Files created

- `bal_sbx/registry/__init__.py`
- `bal_sbx/registry/json_file.py`
- `tests/unit/registry/__init__.py`
- `tests/unit/registry/test_json_file.py`

## Public surface introduced

```python
# bal_sbx/registry/json_file.py
class JsonFileRegistry:
    def __init__(self, path: str): ...

    def list(self) -> list[tuple[str, SandboxMetadata]]: ...
    def get(self, identity_id: str) -> SandboxMetadata | None: ...
    def put(self, identity_id: str, metadata: SandboxMetadata) -> None: ...
    def delete(self, identity_id: str) -> bool: ...
    def touch(self, identity_id: str) -> None: ...   # updates last_used_at
```

## Acceptance criteria

### Code
- File format: `{"<sandbox_id>": {<SandboxMetadata.to_dict()>}, ...}`. Top-level dict keyed by identity ID.
- Atomic write: write to `<path>.tmp` in the same directory, `os.replace` onto the target. Never leave a half-written `sandboxes.json`.
- Read path: missing file → empty registry (no error). Unparseable JSON → raise `RegistryCorrupt(path)`. A repair workflow consumes this in step 11.
- `put` updates `last_used_at` to "now" if the caller passes a metadata where it is set to the empty string (escape hatch for callers that don't care). Otherwise it persists as-is.
- `touch` is a convenience that loads, updates `last_used_at`, and saves.
- Parent directory is created on first write (`os.makedirs(parent, exist_ok=True)`).
- No locking. Concurrent writes are documented as "last writer wins" in a module docstring. Step 11 may introduce a lockfile if needed.

### Tests
- `list()` on a non-existent file returns `[]`.
- Round-trip: `put` then `get` returns the same metadata.
- `delete` returns `True` for present entries, `False` for absent.
- `touch` advances `last_used_at` (compare two timestamps via `>=`, not `>` — same-second writes are legal).
- Atomic write: simulate a write that crashes mid-way by patching `os.replace` to raise — the original file is untouched.
- Corruption recovery: write `"not json"` to the file, `list()` raises `RegistryCorrupt`.
- Parent directory auto-creation: use `tmp_path / "deep" / "registry.json"`.

## Notes / gotchas

- The registry holds **metadata about sandboxes**, not the sandboxes themselves. Filesystem state (HOME, ACLs, users) is owned by `backends/` in step 06.
- See plan.md A4 — no ABC. If a SQLite/remote registry ever materializes, refactor at that point.
- Use only stdlib (`json`, `os`, `tempfile` if needed). No `filelock`, no `pydantic`.
