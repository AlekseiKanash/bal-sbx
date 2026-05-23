import dataclasses
import subprocess

import pytest

from bal_sbx.system.privilege import NullPrivilegeBroker
from tests.unit.system.fakes import (
    FakeAclManager,
    FakeHomeLayout,
    FakeSystemOps,
    FakeUserProvisioner,
)


def test_fake_user_exists_false_when_unseen():
    assert FakeUserProvisioner().exists("alice") is False


def test_fake_user_create_then_exists():
    users = FakeUserProvisioner()
    users.create("alice", "/home/alice")
    assert users.exists("alice") is True


def test_fake_user_create_delete_round_trip():
    users = FakeUserProvisioner()
    users.create("alice", "/home/alice")
    users.delete("alice")
    assert users.exists("alice") is False


def test_fake_user_delete_absent_is_noop():
    FakeUserProvisioner().delete("ghost")


def test_fake_acl_is_granted_false_by_default():
    assert FakeAclManager().is_granted("/w", "alice") is False


def test_fake_acl_grant_revoke_round_trip():
    acl = FakeAclManager()
    acl.grant("/w", "alice")
    assert acl.is_granted("/w", "alice") is True
    acl.revoke("/w", "alice")
    assert acl.is_granted("/w", "alice") is False


def test_fake_acl_grants_isolated_per_path():
    acl = FakeAclManager()
    acl.grant("/w1", "alice")
    assert acl.is_granted("/w1", "alice") is True
    assert acl.is_granted("/w2", "alice") is False


def test_fake_acl_grants_isolated_per_user():
    acl = FakeAclManager()
    acl.grant("/w", "alice")
    assert acl.is_granted("/w", "bob") is False


def test_fake_acl_revoke_absent_is_noop():
    acl = FakeAclManager()
    acl.revoke("/w", "alice")
    assert acl.is_granted("/w", "alice") is False


def test_fake_acl_is_supported_true():
    assert FakeAclManager().is_supported() is True


def test_fake_home_exists_false_by_default():
    assert FakeHomeLayout().exists("/home/alice") is False


def test_fake_home_create_then_exists():
    home = FakeHomeLayout()
    home.create("/home/alice", "alice")
    assert home.exists("/home/alice") is True


def test_fake_home_create_destroy_round_trip():
    home = FakeHomeLayout()
    home.create("/home/alice", "alice")
    home.destroy("/home/alice")
    assert home.exists("/home/alice") is False


def test_fake_home_workspace_link_target_none_after_create():
    home = FakeHomeLayout()
    home.create("/home/alice", "alice")
    assert home.workspace_link_target("/home/alice") is None


def test_fake_home_link_workspace_sets_target():
    home = FakeHomeLayout()
    home.create("/home/alice", "alice")
    home.link_workspace("/home/alice", "/workspace/proj")
    assert home.workspace_link_target("/home/alice") == "/workspace/proj"


def test_fake_home_link_workspace_replaces_target():
    home = FakeHomeLayout()
    home.create("/home/alice", "alice")
    home.link_workspace("/home/alice", "/workspace/a")
    home.link_workspace("/home/alice", "/workspace/b")
    assert home.workspace_link_target("/home/alice") == "/workspace/b"


def test_fake_home_workspace_link_target_none_for_missing_home():
    assert FakeHomeLayout().workspace_link_target("/home/ghost") is None


def test_null_privilege_broker_returns_success():
    result = NullPrivilegeBroker().run_privileged(["whoami"])
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.args == ["whoami"]
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_null_privilege_broker_is_available_false():
    assert NullPrivilegeBroker().is_available() is False


def test_fake_system_ops_bundles_all_four_providers():
    ops = FakeSystemOps()
    assert isinstance(ops.users, FakeUserProvisioner)
    assert isinstance(ops.acl, FakeAclManager)
    assert isinstance(ops.home, FakeHomeLayout)
    assert isinstance(ops.privilege, NullPrivilegeBroker)


def test_fake_system_ops_returns_fresh_instances():
    a = FakeSystemOps()
    b = FakeSystemOps()
    a.users.create("alice", "/home/alice")
    assert b.users.exists("alice") is False


def test_fake_system_ops_is_frozen():
    ops = FakeSystemOps()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ops.users = FakeUserProvisioner()  # type: ignore[misc]


def test_fake_system_ops_fixture_yields_fresh_instance(fake_system_ops):
    assert fake_system_ops.users.exists("alice") is False
    fake_system_ops.users.create("alice", "/home/alice")
    assert fake_system_ops.users.exists("alice") is True
