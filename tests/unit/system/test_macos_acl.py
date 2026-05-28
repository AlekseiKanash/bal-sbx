import subprocess
from unittest.mock import MagicMock

import pytest

from bal_sbx.core.shared_tools import Permission
from bal_sbx.system.acl.macos import MacosAclManager, _grant_spec, _revoke_spec, _rights_for
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


def test_rights_for_none_returns_full():
    assert _rights_for(None) == PINNED_RIGHTS


def test_rights_for_read_only_subset():
    rights = _rights_for(frozenset({Permission.READ}))
    assert rights == "read,readattr,readextattr,readsecurity,list,search"


def test_rights_for_execute_only_subset():
    rights = _rights_for(frozenset({Permission.EXECUTE}))
    assert rights == "execute,search"


def test_rights_for_read_and_execute_includes_search_once():
    rights = _rights_for(frozenset({Permission.READ, Permission.EXECUTE}))
    parts = rights.split(",")
    assert parts.count("search") == 1
    assert "read" in parts
    assert "execute" in parts


def test_rights_for_write_includes_mutation_rights():
    rights = _rights_for(frozenset({Permission.READ, Permission.WRITE}))
    parts = set(rights.split(","))
    assert "write" in parts
    assert "delete" in parts
    assert "chown" in parts


def test_rights_for_canonical_order_preserved():
    rights = _rights_for(frozenset({Permission.READ, Permission.WRITE, Permission.EXECUTE}))
    # Same order as the pinned full string.
    canonical = PINNED_RIGHTS.split(",")
    assert rights.split(",") == [r for r in canonical if r in rights.split(",")]


def test_rights_for_env_only_falls_back_to_full():
    # Defensive — SharedTool validation prevents this, but the helper must
    # never produce an empty rights string for chmod.
    assert _rights_for(frozenset({Permission.ENV})) == PINNED_RIGHTS


def test_grant_single_file_emits_one_chmod(broker, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    MacosAclManager(broker).grant(str(target), "alice")
    broker.run_privileged.assert_called_once_with(
        ["chmod", "+a", f"alice allow {PINNED_RIGHTS}", str(target)]
    )


def test_grant_subset_uses_subset_rights(broker, tmp_path):
    target = tmp_path / "bin"
    target.mkdir()
    MacosAclManager(broker).grant(
        str(target), "alice",
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )
    spec = f"alice allow {_rights_for(frozenset({Permission.READ, Permission.EXECUTE}))}"
    broker.run_privileged.assert_called_once_with(["chmod", "+a", spec, str(target)])


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


def test_revoke_with_subset_uses_subset_rights(broker, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    MacosAclManager(broker).revoke(
        str(target), "alice",
        permissions=frozenset({Permission.READ}),
    )
    expected_rights = _rights_for(frozenset({Permission.READ}))
    broker.run_privileged.assert_called_once_with(
        ["chmod", "-a", f"alice allow {expected_rights}", str(target)]
    )


def test_is_granted_true_when_ls_lists_user_with_prefix(broker, monkeypatch):
    """Real macOS `ls -lde` emits `user:<name>` (with the `user:` prefix)."""
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout=(
            "drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n"
            " 0: user:alice allow list,add_file,search,delete\n"
        ),
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    assert MacosAclManager(broker).is_granted("/w", "alice") is True


def test_is_granted_subset_true_when_actual_is_superset(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout=(
            "drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n"
            f" 0: user:alice allow {PINNED_RIGHTS}\n"
        ),
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    result = MacosAclManager(broker).is_granted(
        "/w", "alice",
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )
    assert result is True


def test_is_granted_subset_false_when_actual_is_missing_a_right(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout=(
            "drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n"
            " 0: user:alice allow read,readattr,readextattr,readsecurity,list,search\n"
        ),
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    # Asking for WRITE — actual has only READ. Should be False.
    result = MacosAclManager(broker).is_granted(
        "/w", "alice",
        permissions=frozenset({Permission.READ, Permission.WRITE}),
    )
    assert result is False


def test_is_granted_false_for_orphaned_uuid_principal(broker, monkeypatch):
    """If the user has been deleted, `ls -lde` prints the bare UUID — not granted."""
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout=(
            "drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n"
            " 0: 3FB3E780-4FEF-4B49-A2BE-4011C8BF94E1 allow list,add_file\n"
        ),
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    assert MacosAclManager(broker).is_granted("/w", "alice") is False


def test_is_granted_false_when_user_absent(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout="drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n",
        stderr="",
    )
    monkeypatch.setattr("bal_sbx.system.acl.macos.subprocess.run", lambda *a, **kw: completed)
    assert MacosAclManager(broker).is_granted("/w", "alice") is False


def test_is_granted_false_when_different_user_listed(broker, monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ls", "-lde", "/w"],
        returncode=0,
        stdout=(
            "drwxr-xr-x   3 root  wheel  96 May 23 12:00 /w\n"
            " 0: user:bob allow list,add_file\n"
        ),
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
