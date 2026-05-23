from unittest.mock import MagicMock, call

import pytest

from bal_sbx.system.privilege import PrivilegeBroker
from bal_sbx.system.users.macos import MacosUserProvisioner, _uid_for


@pytest.fixture
def broker():
    return MagicMock(spec=PrivilegeBroker)


def test_create_issues_full_dscl_sequence(broker):
    MacosUserProvisioner(broker).create("alice", "/Users/alice")
    record = "/Users/alice"
    uid = str(_uid_for("alice"))
    assert broker.run_privileged.call_args_list == [
        call(["dscl", ".", "-create", record]),
        call(["dscl", ".", "-create", record, "UserShell", "/bin/bash"]),
        call(["dscl", ".", "-create", record, "RealName", "alice"]),
        call(["dscl", ".", "-create", record, "UniqueID", uid]),
        call(["dscl", ".", "-create", record, "PrimaryGroupID", "20"]),
        call(["dscl", ".", "-create", record, "NFSHomeDirectory", "/Users/alice"]),
    ]


def test_delete_issues_dscl_delete(broker):
    MacosUserProvisioner(broker).delete("alice")
    broker.run_privileged.assert_called_once_with(["dscl", ".", "-delete", "/Users/alice"])


def test_exists_true_for_known_user(broker, monkeypatch):
    monkeypatch.setattr("bal_sbx.system.users.macos.pwd.getpwnam", lambda u: object())
    assert MacosUserProvisioner(broker).exists("root") is True


def test_exists_false_for_unknown_user(broker, monkeypatch):
    def raise_keyerror(_username):
        raise KeyError(_username)

    monkeypatch.setattr("bal_sbx.system.users.macos.pwd.getpwnam", raise_keyerror)
    assert MacosUserProvisioner(broker).exists("ghost") is False


def test_uid_for_is_deterministic_and_in_range():
    uid = _uid_for("alice")
    assert _uid_for("alice") == uid
    assert 600 <= uid <= 999


def test_uid_for_differs_across_usernames():
    assert _uid_for("alice") != _uid_for("bob")
