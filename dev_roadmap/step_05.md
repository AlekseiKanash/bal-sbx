# Step 05 — Platform implementations

## Goal

Implement the real Linux and macOS providers behind the ABCs from step 04. All privileged calls go through `PrivilegeBroker`; subprocess invocations are unit-tested by mocking `subprocess.run`. No real `sudo` is invoked by the test suite.

## Files created

- `bal_sbx/system/users/linux.py`     # LinuxUserProvisioner — useradd / userdel
- `bal_sbx/system/users/macos.py`     # MacosUserProvisioner — dscl
- `bal_sbx/system/acl/linux.py`       # LinuxAclManager — setfacl
- `bal_sbx/system/acl/macos.py`       # MacosAclManager — chmod +a
- `bal_sbx/system/home.py`            # extend with `RealHomeLayout` (cross-platform via stdlib)
- `bal_sbx/system/privilege.py`       # extend with `SudoBroker` (cached) and `SudoPerOpBroker`
- `bal_sbx/system/ops.py`             # add `SystemOps.detect()` and `SystemOps.unsupported_reason()`
- `tests/unit/system/test_linux_users.py`
- `tests/unit/system/test_macos_users.py`
- `tests/unit/system/test_linux_acl.py`
- `tests/unit/system/test_macos_acl.py`
- `tests/unit/system/test_real_home.py`
- `tests/unit/system/test_privilege.py`
- `tests/unit/system/test_detect.py`

## Public surface introduced

```python
# bal_sbx/system/privilege.py
class SudoBroker(PrivilegeBroker):
    """Caches sudo timestamp once (sudo -v) then runs privileged commands without re-prompting."""

class SudoPerOpBroker(PrivilegeBroker):
    """Invokes sudo on every call. Useful when settings.privilege.mode = 'per_operation'."""

# bal_sbx/system/ops.py
class SystemOps:
    @classmethod
    def detect(cls, privilege_mode: str = "cached") -> "SystemOps": ...
    @classmethod
    def unsupported_reason(cls) -> str | None: ...
```

## Acceptance criteria

### Code
- `LinuxUserProvisioner.create(username, home)` builds `["useradd", "-m", "-d", home, "-s", "/bin/bash", username]` and routes it through `PrivilegeBroker.run_privileged`.
- `LinuxUserProvisioner.delete(username)` builds `["userdel", "-r", username]`.
- `LinuxUserProvisioner.exists(username)` uses `pwd.getpwnam` (stdlib, unprivileged) — catches `KeyError`.
- `MacosUserProvisioner` builds the appropriate `dscl . -create /Users/<user> ...` sequence. Document the exact command list in the module docstring; tests assert on the argv.
- `LinuxAclManager.grant` builds two commands: `setfacl -Rm u:<user>:rwx <path>` and `setfacl -dRm u:<user>:rwx <path>` (default ACL for new files).
- `MacosAclManager.grant` builds `chmod +a "<user> allow read,write,execute,delete,append,readattr,writeattr,readextattr,writeextattr,readsecurity,writesecurity,chown,list,search,add_file,add_subdirectory,delete_child" <path>`. Recurse with a separate `find` pipeline or stdlib walk — pick one and document.
- `AclManager.is_supported()` probes for the binary's existence via `shutil.which` and platform check.
- `RealHomeLayout` is platform-agnostic — uses `os.makedirs`, `os.symlink`, `os.readlink`. Permissions and ownership are set via privileged `chown` through `PrivilegeBroker`.
- `SudoBroker`: lazily calls `subprocess.run(["sudo", "-v"], check=True)` on first `run_privileged`. Subsequent calls prefix the command with `sudo -n` (non-interactive). If `-n` fails with timestamp expired, fall back to one re-prompt.
- `SudoPerOpBroker`: every call prefixes with `sudo` (interactive). No caching.
- `SystemOps.detect(privilege_mode)`:
  - `sys.platform == "linux"` → `LinuxUserProvisioner`, `LinuxAclManager`, `RealHomeLayout`, broker per mode.
  - `sys.platform == "darwin"` → macOS variants.
  - Other → raise `PlatformUnsupported`.
- `SystemOps.unsupported_reason()` returns a human-readable string when `detect()` would raise; `None` otherwise. Used by `capabilities()` in step 08.

### Tests
- Each provider has a test that constructs it with a `FakePrivilegeBroker` (a `MagicMock` wrapping `PrivilegeBroker`) and asserts on the exact argv passed to `run_privileged`.
- `SudoBroker` test patches `subprocess.run` and verifies `sudo -v` is called once across multiple `run_privileged` invocations.
- `SudoPerOpBroker` test verifies every invocation prefixes `sudo`.
- `RealHomeLayout` tests use `tmp_path` for actual filesystem ops (no privilege needed for unprivileged file creation in a tmp dir); patch chown calls.
- `SystemOps.detect()` returns the correct concrete types per `sys.platform` (patch it).
- `SystemOps.detect()` on `win32` raises `PlatformUnsupported`.

## Notes / gotchas

- macOS ACL syntax is brittle — the exact rights list is documented in `man chmod`. Pin the string in code and assert on it in tests so it cannot drift silently.
- `dscl` is the modern way to create users on macOS (`sysadminctl` is also viable; pick one — `dscl` is more reliable in non-GUI contexts). Document the choice.
- Some Linux distros use `adduser` instead of `useradd`. Stick to `useradd` (POSIX-ish, present everywhere). Document.
- `SudoBroker` must never echo passwords or sensitive arguments to logs; the test suite verifies argv-only assertions, never stdin content.
- No third-party packages — use `subprocess`, `shutil`, `pwd`, `os`, `sys`.
- See plan.md A1.
