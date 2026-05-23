import subprocess
from unittest.mock import MagicMock

import pytest

from bal_sbx.system.acl.macos import MacosAclManager, _grant_spec, _revoke_spec
from bal_sbx.system.privilege import PrivilegeBroker

PINNED_RIGHTS = (
    "read,write,execute,delete,append,"
    "readattr,writeattr,readextattr,writeextattr,"
    "readsecurity,writesecurity,chown,"
    "list,search,add_file,add_subdirectory,delete_child"
)


@pytest.fixture
def broker():
    return MagicMock(spec=PrivilegeBroker)


def test_grant_spec_pinned_string():
    assert _grant_spec("alice") == f"alice allow {PINNED_RIGHTS}"


def test_revoke_spec_pinned_string():
    assert _revoke_spec("alice") == f"alice allow {PINNED_RIGHTS}"


def test_grant_single_file_emits_one_chmod(broker, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    MacosAclManager(broker).grant(str(target), "alice")
    broker.run_privileged.assert_called_once_with(
        ["chmod", "+a", f"alice allow {PINNED_RIGHTS}", str(target)]
    )


def test_grant_directory_recurses_via_walk(broker, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "leaf.txt").write_text("x")
    MacosAclManager(broker).grant(str(tmp_path), "alice")
    spec = f"alice allow {PINNED_RIGHTS}"
    argvs = [c.args[0] for c in broker.run_privileged.call_args_list]
    targets = {argv[-1] for argv in argvs}
    assert targets == {
        str(tmp_path),
        str(tmp_path / "sub"),
        str(tmp_path / "sub" / "leaf.txt"),
    }
    for argv in argvs:
        assert argv[:3] == ["chmod", "+a", spec]


def test_revoke_uses_minus_a_with_same_spec(broker, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    MacosAclManager(broker).revoke(str(target), "alice")
    broker.run_privileged.assert_called_once_with(
        ["chmod", "-a", f"alice allow {PINNED_RIGHTS}", str(target)]
    )


def test_is_granted_true_when_ls_lists_user(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout="drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n 0: alice allow read,write,execute\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    assert MacosAclManager(broker).is_granted("/w", "alice") is True


def test_is_granted_false_when_user_absent(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout="drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    assert MacosAclManager(broker).is_granted("/w", "alice") is False


def test_is_granted_false_when_ls_fails(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"], returncode=1, stdout="", stderr="No such file"
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    assert MacosAclManager(broker).is_granted("/w", "alice") is False


def test_is_supported_true_on_darwin(broker, monkeypatch):
    monkeypatch.setattr("bal_sbx.system.acl.macos.sys.platform", "darwin")
    assert MacosAclManager(broker).is_supported() is True


def test_is_supported_false_off_darwin(broker, monkeypatch):
    monkeypatch.setattr("bal_sbx.system.acl.macos.sys.platform", "linux")
    assert MacosAclManager(broker).is_supported() is False
