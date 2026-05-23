import subprocess
from unittest.mock import MagicMock, call

import pytest

from bal_sbx.system.acl.linux import LinuxAclManager
from bal_sbx.system.privilege import PrivilegeBroker


@pytest.fixture
def broker():
    return MagicMock(spec=PrivilegeBroker)


def test_grant_issues_access_and_default_acls(broker):
    LinuxAclManager(broker).grant("/workspace/proj", "alice")
    assert broker.run_privileged.call_args_list == [
        call(["setfacl", "-Rm", "u:alice:rwx", "/workspace/proj"]),
        call(["setfacl", "-dRm", "u:alice:rwx", "/workspace/proj"]),
    ]


def test_revoke_strips_access_and_default_acls(broker):
    LinuxAclManager(broker).revoke("/workspace/proj", "alice")
    assert broker.run_privileged.call_args_list == [
        call(["setfacl", "-Rx", "u:alice", "/workspace/proj"]),
        call(["setfacl", "-dRx", "u:alice", "/workspace/proj"]),
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
