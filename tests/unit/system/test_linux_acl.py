import subprocess
from unittest.mock import MagicMock, call

import pytest

from bal_sbx.core.shared_tools import Permission
from bal_sbx.system.acl.linux import LinuxAclManager, _rights_for
from bal_sbx.system.privilege import PrivilegeBroker


@pytest.fixture
def broker():
    return MagicMock(spec=PrivilegeBroker)


def test_rights_for_none_returns_rwx():
    assert _rights_for(None) == "rwx"


def test_rights_for_read_only_returns_r():
    assert _rights_for(frozenset({Permission.READ})) == "r"


def test_rights_for_read_and_execute_returns_rx():
    assert _rights_for(frozenset({Permission.READ, Permission.EXECUTE})) == "rx"


def test_rights_for_read_write_execute_returns_rwx():
    assert _rights_for(
        frozenset({Permission.READ, Permission.WRITE, Permission.EXECUTE})
    ) == "rwx"


def test_rights_for_env_only_falls_back_to_rwx():
    # Defensive — SharedTool validation prevents this, but the helper must
    # never produce an empty rights string for setfacl.
    assert _rights_for(frozenset({Permission.ENV})) == "rwx"


def test_grant_issues_access_and_default_acls(broker):
    LinuxAclManager(broker).grant("/workspace/proj", "alice")
    assert broker.run_privileged.call_args_list == [
        call(["setfacl", "-Rm", "u:alice:rwx", "/workspace/proj"]),
        call(["setfacl", "-dRm", "u:alice:rwx", "/workspace/proj"]),
    ]


def test_grant_subset_uses_subset_rights(broker):
    LinuxAclManager(broker).grant(
        "/opt/homebrew/bin", "alice",
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )
    assert broker.run_privileged.call_args_list == [
        call(["setfacl", "-Rm", "u:alice:rx", "/opt/homebrew/bin"]),
        call(["setfacl", "-dRm", "u:alice:rx", "/opt/homebrew/bin"]),
    ]


def test_revoke_strips_access_and_default_acls(broker):
    LinuxAclManager(broker).revoke("/workspace/proj", "alice")
    assert broker.run_privileged.call_args_list == [
        call(["setfacl", "-Rx", "u:alice", "/workspace/proj"]),
        call(["setfacl", "-dRx", "u:alice", "/workspace/proj"]),
    ]


def test_revoke_with_subset_still_targets_principal_only(broker):
    LinuxAclManager(broker).revoke(
        "/opt/homebrew/bin", "alice",
        permissions=frozenset({Permission.READ}),
    )
    # setfacl -x removes the principal regardless of rights — same call.
    assert broker.run_privileged.call_args_list == [
        call(["setfacl", "-Rx", "u:alice", "/opt/homebrew/bin"]),
        call(["setfacl", "-dRx", "u:alice", "/opt/homebrew/bin"]),
    ]


def test_is_granted_true_when_getfacl_lists_user(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["getfacl", "-c", "/w"],
        returncode=0,
        stdout="user::rwx\nuser:alice:rwx\ngroup::r-x\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.linux.subprocess.run", lambda *a, **kw: completed)
    assert LinuxAclManager(broker).is_granted("/w", "alice") is True


def test_is_granted_subset_true_when_actual_is_superset(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["getfacl", "-c", "/w"],
        returncode=0,
        stdout="user:alice:rwx\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.linux.subprocess.run", lambda *a, **kw: completed)
    result = LinuxAclManager(broker).is_granted(
        "/w", "alice",
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )
    assert result is True


def test_is_granted_subset_false_when_actual_missing_a_letter(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["getfacl", "-c", "/w"],
        returncode=0,
        stdout="user:alice:r-x\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.linux.subprocess.run", lambda *a, **kw: completed)
    result = LinuxAclManager(broker).is_granted(
        "/w", "alice",
        permissions=frozenset({Permission.READ, Permission.WRITE}),
    )
    assert result is False


def test_is_granted_false_when_user_absent(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["getfacl", "-c", "/w"],
        returncode=0,
        stdout="user::rwx\ngroup::r-x\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.linux.subprocess.run", lambda *a, **kw: completed)
    assert LinuxAclManager(broker).is_granted("/w", "alice") is False


def test_is_granted_false_when_getfacl_fails(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["getfacl", "-c", "/w"], returncode=1, stdout="", stderr="No such file"
    )
    monkeypatch.setattr("bal_sbx.system.acl.linux.subprocess.run", lambda *a, **kw: completed)
    assert LinuxAclManager(broker).is_granted("/w", "alice") is False


def test_is_supported_true_on_linux_with_setfacl(broker, monkeypatch):
    monkeypatch.setattr("bal_sbx.system.acl.linux.sys.platform", "linux")
    monkeypatch.setattr("bal_sbx.system.acl.linux.shutil.which", lambda b: "/usr/bin/setfacl")
    assert LinuxAclManager(broker).is_supported() is True


def test_is_supported_false_off_linux(broker, monkeypatch):
    monkeypatch.setattr("bal_sbx.system.acl.linux.sys.platform", "darwin")
    monkeypatch.setattr("bal_sbx.system.acl.linux.shutil.which", lambda b: "/usr/bin/setfacl")
    assert LinuxAclManager(broker).is_supported() is False


def test_is_supported_false_when_setfacl_missing(broker, monkeypatch):
    monkeypatch.setattr("bal_sbx.system.acl.linux.sys.platform", "linux")
    monkeypatch.setattr("bal_sbx.system.acl.linux.shutil.which", lambda b: None)
    assert LinuxAclManager(broker).is_supported() is False
