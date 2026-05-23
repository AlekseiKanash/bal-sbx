import os
from unittest.mock import patch

import pytest

from bal_sbx.backends.user import UserSandbox
from bal_sbx.core.errors import SandboxBroken
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.status import SandboxStatus


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/registry.json")


def _identity(tmp_path, name: str = "ws") -> SandboxIdentity:
    workspace = tmp_path / name
    workspace.mkdir()
    return SandboxIdentity.from_workspace(str(workspace), LAYOUT)


# ---- lifecycle ----------------------------------------------------------

def test_create_then_status_ok(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    assert sandbox.status() is SandboxStatus.OK


def test_create_idempotent_does_not_recreate_user(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()

    with patch.object(
        fake_system_ops.users, "create", wraps=fake_system_ops.users.create
    ) as user_create, patch.object(
        fake_system_ops.home, "create", wraps=fake_system_ops.home.create
    ) as home_create, patch.object(
        fake_system_ops.home, "link_workspace", wraps=fake_system_ops.home.link_workspace
    ) as link_workspace, patch.object(
        fake_system_ops.acl, "grant", wraps=fake_system_ops.acl.grant
    ) as grant:
        sandbox.create()
        user_create.assert_not_called()
        home_create.assert_not_called()
        link_workspace.assert_not_called()
        grant.assert_not_called()


def test_create_writes_expected_arguments(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    UserSandbox(identity, fake_system_ops).create()

    assert fake_system_ops.users.exists(identity.user)
    assert fake_system_ops.home.exists(identity.home)
    assert fake_system_ops.home.workspace_link_target(identity.home) == identity.workspace
    assert fake_system_ops.acl.is_granted(identity.workspace, identity.user)


# ---- status detection ---------------------------------------------------

def test_status_missing_workspace(fake_system_ops, tmp_path):
    ghost = tmp_path / "ghost"
    identity = SandboxIdentity.from_workspace(str(ghost), LAYOUT)
    sandbox = UserSandbox(identity, fake_system_ops)
    assert sandbox.status() is SandboxStatus.MISSING_WORKSPACE


def test_status_missing_user_on_fresh_ops(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    assert UserSandbox(identity, fake_system_ops).status() is SandboxStatus.MISSING_USER


def test_status_missing_home_when_user_exists_but_home_does_not(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    fake_system_ops.users.create(identity.user, identity.home)
    assert UserSandbox(identity, fake_system_ops).status() is SandboxStatus.MISSING_HOME


def test_status_broken_symlink_when_link_missing(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    fake_system_ops.users.create(identity.user, identity.home)
    fake_system_ops.home.create(identity.home, identity.user)
    assert UserSandbox(identity, fake_system_ops).status() is SandboxStatus.BROKEN_SYMLINK


def test_status_broken_symlink_when_link_points_elsewhere(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    fake_system_ops.users.create(identity.user, identity.home)
    fake_system_ops.home.create(identity.home, identity.user)
    fake_system_ops.home.link_workspace(identity.home, "/somewhere/else")
    assert UserSandbox(identity, fake_system_ops).status() is SandboxStatus.BROKEN_SYMLINK


def test_status_dangling_acl_when_only_acl_missing(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    fake_system_ops.users.create(identity.user, identity.home)
    fake_system_ops.home.create(identity.home, identity.user)
    fake_system_ops.home.link_workspace(identity.home, identity.workspace)
    assert UserSandbox(identity, fake_system_ops).status() is SandboxStatus.DANGLING_ACL


def test_status_ok_after_full_create(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    assert sandbox.status() is SandboxStatus.OK


def test_status_reports_first_problem_only(fake_system_ops, tmp_path):
    """Missing workspace AND missing user — workspace wins (higher priority)."""
    ghost = tmp_path / "ghost"
    identity = SandboxIdentity.from_workspace(str(ghost), LAYOUT)
    assert UserSandbox(identity, fake_system_ops).status() is SandboxStatus.MISSING_WORKSPACE


# ---- repair -------------------------------------------------------------

def test_repair_fixes_all_and_returns_status_list(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    fixed = sandbox.repair()
    assert fixed == [
        SandboxStatus.MISSING_USER,
        SandboxStatus.MISSING_HOME,
        SandboxStatus.BROKEN_SYMLINK,
        SandboxStatus.DANGLING_ACL,
    ]
    assert sandbox.status() is SandboxStatus.OK


def test_repair_on_healthy_returns_empty(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    assert sandbox.repair() == []


def test_repair_twice_idempotent(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.repair()
    assert sandbox.repair() == []


def test_repair_refuses_missing_workspace(fake_system_ops, tmp_path):
    ghost = tmp_path / "ghost"
    identity = SandboxIdentity.from_workspace(str(ghost), LAYOUT)
    sandbox = UserSandbox(identity, fake_system_ops)
    with pytest.raises(SandboxBroken):
        sandbox.repair()


def test_repair_only_dangling_acl(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    fake_system_ops.users.create(identity.user, identity.home)
    fake_system_ops.home.create(identity.home, identity.user)
    fake_system_ops.home.link_workspace(identity.home, identity.workspace)
    sandbox = UserSandbox(identity, fake_system_ops)
    assert sandbox.repair() == [SandboxStatus.DANGLING_ACL]
    assert sandbox.status() is SandboxStatus.OK


# ---- destroy ------------------------------------------------------------

def test_destroy_removes_everything(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    sandbox.destroy()
    assert not fake_system_ops.users.exists(identity.user)
    assert not fake_system_ops.home.exists(identity.home)
    assert not fake_system_ops.acl.is_granted(identity.workspace, identity.user)


def test_destroy_tolerates_already_missing_user(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    fake_system_ops.users.delete(identity.user)
    sandbox.destroy()
    assert not fake_system_ops.home.exists(identity.home)
    assert not fake_system_ops.acl.is_granted(identity.workspace, identity.user)


def test_destroy_tolerates_already_missing_home(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    fake_system_ops.home.destroy(identity.home)
    sandbox.destroy()
    assert not fake_system_ops.users.exists(identity.user)
    assert not fake_system_ops.acl.is_granted(identity.workspace, identity.user)


def test_destroy_tolerates_already_missing_acl(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    fake_system_ops.acl.revoke(identity.workspace, identity.user)
    sandbox.destroy()
    assert not fake_system_ops.users.exists(identity.user)
    assert not fake_system_ops.home.exists(identity.home)


def test_destroy_on_fresh_is_noop(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    UserSandbox(identity, fake_system_ops).destroy()


def test_destroy_collects_failures_and_raises_sandbox_broken(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()

    def boom(*_a, **_kw):
        raise RuntimeError("kaboom")

    with patch.object(fake_system_ops.users, "delete", side_effect=boom), patch.object(
        fake_system_ops.acl, "revoke", side_effect=boom
    ):
        with pytest.raises(SandboxBroken):
            sandbox.destroy()

    # The non-failing step (home.destroy) still ran.
    assert not fake_system_ops.home.exists(identity.home)


# ---- enter --------------------------------------------------------------

def test_enter_execs_sudo_with_bash(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)

    captured: dict = {}

    def fake_execvp(file, args):
        captured["file"] = file
        captured["args"] = list(args)

    monkeypatch.setattr("bal_sbx.backends.user.shutil.which", lambda _: "/usr/bin/bash")
    monkeypatch.setattr(os, "execvp", fake_execvp)

    with pytest.raises(RuntimeError):
        sandbox.enter()

    assert captured["file"] == "sudo"
    assert captured["args"] == ["sudo", "-u", identity.user, "-H", "bash", "-l"]


def test_enter_falls_back_to_sh_without_bash(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)

    captured: dict = {}

    def fake_execvp(file, args):
        captured["file"] = file
        captured["args"] = list(args)

    monkeypatch.setattr("bal_sbx.backends.user.shutil.which", lambda _: None)
    monkeypatch.setattr(os, "execvp", fake_execvp)

    with pytest.raises(RuntimeError):
        sandbox.enter()

    assert captured["args"] == ["sudo", "-u", identity.user, "-H", "/bin/sh", "-l"]
