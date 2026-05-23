# Step 04 — System layer ABCs + fakes

## Goal

Define the four platform-capability interfaces (A1) and provide in-memory fakes for testing. **No real platform code in this step** — that arrives in step 05. After this step every later step can use `FakeSystemOps` to test sandbox lifecycle without `sudo`.

## Files created

- `bal_sbx/system/__init__.py`
- `bal_sbx/system/users/__init__.py`
- `bal_sbx/system/users/base.py`
- `bal_sbx/system/acl/__init__.py`
- `bal_sbx/system/acl/base.py`
- `bal_sbx/system/home.py`         # ABC only — implementation in step 05
- `bal_sbx/system/privilege.py`    # ABC + a NullPrivilegeBroker for fakes
- `bal_sbx/system/ops.py`          # SystemOps value object
- `tests/unit/system/__init__.py`
- `tests/unit/system/fakes.py`     # FakeUserProvisioner, FakeAclManager, FakeHomeLayout, FakeSystemOps
- `tests/unit/system/test_fakes.py`
- update `tests/conftest.py` to expose a `fake_system_ops` fixture

## Public surface introduced

```python
# bal_sbx/system/users/base.py
class UserProvisioner(ABC):
    @abstractmethod
    def exists(self, username: str) -> bool: ...
    @abstractmethod
    def create(self, username: str, home: str) -> None: ...
    @abstractmethod
    def delete(self, username: str) -> None: ...

# bal_sbx/system/acl/base.py
class AclManager(ABC):
    @abstractmethod
    def grant(self, path: str, username: str) -> None: ...
    @abstractmethod
    def revoke(self, path: str, username: str) -> None: ...
    @abstractmethod
    def is_granted(self, path: str, username: str) -> bool: ...
    @abstractmethod
    def is_supported(self) -> bool: ...

# bal_sbx/system/home.py
class HomeLayout(ABC):
    @abstractmethod
    def create(self, home: str, username: str) -> None: ...
    @abstractmethod
    def destroy(self, home: str) -> None: ...
    @abstractmethod
    def exists(self, home: str) -> bool: ...
    @abstractmethod
    def link_workspace(self, home: str, workspace: str) -> None: ...
    @abstractmethod
    def workspace_link_target(self, home: str) -> str | None: ...

# bal_sbx/system/privilege.py
class PrivilegeBroker(ABC):
    @abstractmethod
    def run_privileged(self, argv: list[str]) -> subprocess.CompletedProcess: ...
    @abstractmethod
    def is_available(self) -> bool: ...

class NullPrivilegeBroker(PrivilegeBroker):
    """No-op broker used by fakes — runs nothing, returns success."""

# bal_sbx/system/ops.py
@dataclass(frozen=True)
class SystemOps:
    users: UserProvisioner
    acl: AclManager
    home: HomeLayout
    privilege: PrivilegeBroker
```

## Acceptance criteria

### Code
- Every ABC method has a one-line docstring describing the contract.
- `SystemOps` is a frozen dataclass — providers are injected at construction. **No `SystemOps.detect()` yet** — that lands in step 05.
- `NullPrivilegeBroker.run_privileged` returns `subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")` and never invokes anything real.
- The fakes in `tests/unit/system/fakes.py`:
  - `FakeUserProvisioner` — backed by a `set[str]` of usernames.
  - `FakeAclManager` — backed by a `dict[str, set[str]]` mapping path → granted users.
  - `FakeHomeLayout` — backed by a `dict[str, str | None]` mapping home path → workspace symlink target (or `None`).
  - `FakeSystemOps` — constructs all four with `NullPrivilegeBroker`.

### Tests
- Each fake passes a minimal contract test (create/delete/exists round-trip, grant/revoke round-trip, etc.).
- The `fake_system_ops` fixture yields a fresh `FakeSystemOps` per test.

## Notes / gotchas

- These ABCs are the seams that make the rest of the project testable. Resist adding methods until a real caller needs them (step 06 will surface gaps — fix them then).
- `HomeLayout` deliberately knows about `.bal/workspace` because that symlink is part of the layout, not of the workspace itself.
- `PrivilegeBroker.is_available()` is what `SandboxManager.capabilities()` (step 08) calls to populate `can_sudo`.
- See plan.md A1.
