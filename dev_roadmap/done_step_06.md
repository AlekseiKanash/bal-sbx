# Step 06 — `UserSandbox` backend

## Goal

Implement the `Sandbox` ABC and the first concrete backend, `UserSandbox`. This is the orchestration layer that composes `SystemOps` providers into a coherent create → status → repair → destroy lifecycle.

## Files created

- `bal_sbx/backends/__init__.py`
- `bal_sbx/backends/base.py`
- `bal_sbx/backends/user.py`
- `bal_sbx/backends/factory.py`
- `tests/unit/backends/__init__.py`
- `tests/unit/backends/test_user_sandbox.py`
- `tests/unit/backends/test_factory.py`

## Public surface introduced

```python
# bal_sbx/backends/base.py
class Sandbox(ABC):
    identity: SandboxIdentity

    @abstractmethod
    def create(self) -> None: ...
    @abstractmethod
    def destroy(self) -> None: ...
    @abstractmethod
    def status(self) -> SandboxStatus: ...
    @abstractmethod
    def repair(self) -> list[SandboxStatus]: ...
    @abstractmethod
    def enter(self) -> NoReturn: ...   # execs an interactive shell as the sandbox user

# bal_sbx/backends/user.py
class UserSandbox(Sandbox):
    def __init__(self, identity: SandboxIdentity, system_ops: SystemOps): ...

# bal_sbx/backends/factory.py
def build_sandbox(kind: str, identity: SandboxIdentity, system_ops: SystemOps) -> Sandbox: ...
```

## Acceptance criteria

### Code
- `UserSandbox.create()` is idempotent. Each step is a guard clause:
  1. If `users.exists(identity.user)` is `False` → `users.create(identity.user, identity.home)`.
  2. If `home.exists(identity.home)` is `False` → `home.create(identity.home, identity.user)`.
  3. If `home.workspace_link_target(identity.home) != identity.workspace` → `home.link_workspace(identity.home, identity.workspace)`.
  4. If `acl.is_granted(identity.workspace, identity.user)` is `False` → `acl.grant(identity.workspace, identity.user)`.
- `UserSandbox.destroy()` reverses the order: revoke ACL → destroy HOME → delete user. Each step guarded by an existence check. Failures of one step do not block the next; collected failures raise a single `SandboxBroken` at the end.
- `UserSandbox.status()`:
  - Workspace missing → `MISSING_WORKSPACE`.
  - User missing → `MISSING_USER`.
  - HOME missing → `MISSING_HOME`.
  - Symlink missing or pointing elsewhere → `BROKEN_SYMLINK`.
  - ACL not granted → `DANGLING_ACL`.
  - Otherwise → `OK`.
  Status is reported as the **first** problem encountered (in the order above). Comprehensive multi-issue reporting is `repair()`'s job.
- `UserSandbox.repair()` runs the same checks as `status()` but fixes each problem and returns the **list** of statuses that were repaired. Returns `[]` on a healthy sandbox. Refuses to repair `MISSING_WORKSPACE` (the user must restore the workspace).
- `UserSandbox.enter()` execs `sudo -u <user> -H bash -l` (or `/bin/sh` if bash unavailable). Uses `os.execvp` for true process replacement.
- `build_sandbox(kind, identity, system_ops)`:
  - `kind == "user"` → `UserSandbox(identity, system_ops)`.
  - Any other string → raise `ValueError(f"unknown sandbox kind: {kind!r}")`.
  - The factory exists now to make step 09 trivial; do not add Docker stubs.

### Tests
- Lifecycle: `create()` on a fresh `FakeSystemOps` then `status() == OK`.
- Idempotency: `create()` called twice does not re-create the user (verify via fake's call count).
- Status detection: for each `SandboxStatus` value, construct a `FakeSystemOps` that produces exactly that condition and assert `status()` returns it.
- `repair()` returns the list of fixed statuses; calling `repair()` again returns `[]`.
- `repair()` refuses `MISSING_WORKSPACE` — raises `SandboxBroken`.
- `destroy()` removes user, HOME, and ACL even if one of them was already missing.
- `enter()` is verified by monkeypatching `os.execvp` and asserting the argv.
- `build_sandbox("docker", ...)` raises `ValueError`.

## Notes / gotchas

- `UserSandbox` orchestrates — it does not reason about platform specifics. Anything platform-specific belongs in `system/`.
- The status enum is reported as a single value, not a bitmask. `repair()`'s list return type makes multi-issue handling explicit.
- See plan.md A2 — there is no `UnsafeSandbox`. Unsafe is an exec strategy (step 07), not a backend.
