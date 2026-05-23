from unittest.mock import MagicMock

import pytest

from bal_sbx.system.privilege import PrivilegeBroker
from bal_sbx.system.users.linux import LinuxUserProvisioner


@pytest.fixture
def broker():
    return MagicMock(spec=PrivilegeBroker)


def test_create_routes_useradd_with_expected_argv(broker):
    LinuxUserProvisioner(broker).create("alice", "/home/alice")
    broker.run_privileged.assert_called_once_with(
        ["useradd", "-m", "-d", "/home/alice", "-s", "/bin/bash", "alice"]
    )


def test_delete_routes_userdel_with_r_flag(broker):
    LinuxUserProvisioner(broker).delete("alice")
    broker.run_privileged.assert_called_once_with(["userdel", "-r", "alice"])


def test_exists_true_for_known_user(broker, monkeypatch):
    fake_entry = object()
    monkeypatch.setattr("bal_sbx.system.users.linux.pwd.getpwnam", lambda u: fake_entry)
    assert LinuxUserProvisioner(broker).exists("root") is True


def test_exists_false_for_unknown_user(broker, monkeypatch):
    def raise_keyerror(_username):
        raise KeyError(_username)

    monkeypatch.setattr("bal_sbx.system.users.linux.pwd.getpwnam", raise_keyerror)
    assert LinuxUserProvisioner(broker).exists("ghost") is False


def test_exists_does_not_invoke_privilege_broker(broker, monkeypatch):
    monkeypatch.setattr(
        "bal_sbx.system.users.linux.pwd.getpwnam", lambda u: (_ for _ in ()).throw(KeyError(u))
    )
    LinuxUserProvisioner(broker).exists("anyone")
    broker.run_privileged.assert_not_called()
