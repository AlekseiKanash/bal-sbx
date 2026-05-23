# Step 11 — `repair`, `cleanup`, stale detection

## Goal

Detect and recover from every stale-sandbox condition listed in the strategy doc. Provide `bal-sbx sandbox repair` (fix in place) and `bal-sbx sandbox cleanup` (remove unrecoverable entries). Both commands support `--dry-run` and `--yes`.

## Files created / modified

- `bal_sbx/core/staleness.py`             # new — detect_stale() pure function
- `bal_sbx/backends/user.py`              # extend `repair()` if needed (most logic already present in step 06)
- `bal_sbx/cli/commands/sandbox.py`       # implement `cmd_repair` and `cmd_cleanup`
- `bal_sbx/api.py`                        # add `repair_all()` and `cleanup_stale()` to SandboxManager
- `tests/unit/core/test_staleness.py`
- `tests/unit/cli/test_sandbox_repair.py`
- `tests/unit/cli/test_sandbox_cleanup.py`

## Public surface introduced

```bash
bal-sbx sandbox repair [--workspace PATH] [--dry-run]
bal-sbx sandbox cleanup [--dry-run] [--yes]
```

```python
# bal_sbx/core/staleness.py
@dataclass(frozen=True)
class StaleReport:
    identity: SandboxIdentity
    metadata: SandboxMetadata
    statuses: list[SandboxStatus]   # in detection order
    recoverable: bool               # True if repair() can fix it

def detect_stale(
    identity: SandboxIdentity,
    metadata: SandboxMetadata,
    system_ops: SystemOps,
) -> StaleReport: ...

# bal_sbx/api.py
class SandboxManager:
    def repair_all(self, dry_run: bool = False) -> list[StaleReport]: ...
    def cleanup_stale(self, dry_run: bool = False) -> list[StaleReport]: ...
```

## Acceptance criteria

### Code
- `detect_stale` runs **all** checks (not first-wins like `Sandbox.status()`) and returns the complete list:
  - workspace path missing → `MISSING_WORKSPACE` (recoverable = `False`)
  - user missing → `MISSING_USER` (recoverable = `True`)
  - HOME missing → `MISSING_HOME` (recoverable = `True`)
  - symlink missing/wrong → `BROKEN_SYMLINK` (recoverable = `True`)
  - ACL not granted → `DANGLING_ACL` (recoverable = `True`)
  - HOME exists but no matching user → `ORPHAN_HOME` (recoverable = `True`)
  - metadata fails to parse → `INVALID_METADATA` (recoverable = `False`)
  - empty list → sandbox is healthy.
- `repair_all`:
  - Iterates registry entries.
  - For each, computes `StaleReport`.
  - If `dry_run` → return the list, do nothing.
  - Otherwise call `sandbox.repair()` per entry (uses existing step 06 logic).
  - `MISSING_WORKSPACE` is **not** repaired — surfaced in the result, left for `cleanup`.
- `cleanup_stale`:
  - Iterates registry entries.
  - Selects entries where `recoverable` is `False` (or where the user opts in via `--yes` to also remove recoverable but unused ones — out of scope: only unrecoverable are removed here).
  - For each: destroy the sandbox (`Sandbox.destroy()`), remove from registry.
  - Dry-run returns the list without acting.
- CLI:
  - `cmd_repair` calls `manager.repair_all(dry_run=args.dry_run)`. Renders a per-sandbox summary (id, statuses, action).
  - `cmd_cleanup` calls `manager.cleanup_stale(dry_run=args.dry_run)`. If not `--yes` and not `--dry-run` and the list is non-empty, prompt for confirmation. Refusal exits 0 with no action.

### Tests
- One test per stale variant: construct a `FakeSystemOps` + registry state producing that exact condition, assert `detect_stale` returns the expected list.
- `repair_all(dry_run=True)` does not mutate state (verify call counts on `FakeSystemOps` are zero).
- `repair_all()` against a registry with 3 broken sandboxes fixes the recoverable ones and leaves `MISSING_WORKSPACE` flagged.
- `cleanup_stale(dry_run=True)` returns the list without registry mutation.
- `cleanup_stale()` removes entries where workspace is gone.
- `cmd_cleanup` without `--yes` prompts; passing `n` aborts; passing `y` proceeds. Patch `builtins.input`.

## Notes / gotchas

- Keep `detect_stale` a **pure** function — it accepts a `SystemOps` and a `(identity, metadata)` pair and returns a value. No registry writes here.
- The "every stale variant has a test" rule is non-negotiable for this step — these checks are easy to get subtly wrong.
- Cleanup destroys real users and HOMEs. Tests use `FakeSystemOps` exclusively; manual real-system verification is part of the end-of-roadmap checklist.
- See plan.md Phase 2 exit criteria.
