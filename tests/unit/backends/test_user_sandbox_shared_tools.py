"""UserSandbox tests for shared-tool ACL reconciliation."""

from __future__ import annotations

import pytest

from bal_sbx.backends.user import ToolGrant, UserSandbox
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.shared_tools import Permission
from bal_sbx.core.status import SandboxStatus

LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/r.json")


def _identity(tmp_path) -> SandboxIdentity:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return SandboxIdentity.from_workspace(str(workspace), LAYOUT)


def _grant(path: str, perms=None) -> ToolGrant:
    return ToolGrant(
        path=path,
        permissions=perms or frozenset({Permission.READ, Permission.EXECUTE}),
    )


def test_create_grants_each_shared_tool_path(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    grants = (
        _grant("/opt/homebrew/bin"),
        _grant("/opt/homebrew/Cellar"),
    )
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    user = identity.user
    for grant in grants:
        assert fake_system_ops.acl.is_granted(grant.path, user, grant.permissions)


def test_create_records_subset_permissions(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    perms = frozenset({Permission.READ})
    grants = (_grant("/opt/homebrew/bin", perms=perms),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    stored = fake_system_ops.acl.permissions[("/opt/homebrew/bin", identity.user)]
    assert stored == perms


def test_create_is_idempotent_for_shared_tools(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    grants = (_grant("/opt/homebrew/bin"),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    sandbox.create()
    # Still exactly one user-entry on that path
    users = fake_system_ops.acl.grants["/opt/homebrew/bin"]
    assert users == {identity.user}


def test_create_skips_empty_permission_grants(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    # env-only tool resolved to zero acl perms
    grants = (ToolGrant(path="/opt/homebrew/bin", permissions=frozenset()),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    assert "/opt/homebrew/bin" not in fake_system_ops.acl.grants


def test_destroy_revokes_each_shared_tool_path(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    grants = (
        _grant("/opt/homebrew/bin"),
        _grant("/opt/homebrew/Cellar"),
    )
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    sandbox.destroy()
    for grant in grants:
        assert not fake_system_ops.acl.is_granted(grant.path, identity.user)


def test_status_dangling_when_shared_tool_acl_missing(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    grants = (_grant("/opt/homebrew/bin"),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    # Wipe just the shared-tool ACL — workspace ACL still present.
    fake_system_ops.acl.revoke("/opt/homebrew/bin", identity.user)
    assert sandbox.status() is SandboxStatus.DANGLING_ACL


def test_repair_restores_missing_shared_tool_acl(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    grants = (_grant("/opt/homebrew/bin"),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    fake_system_ops.acl.revoke("/opt/homebrew/bin", identity.user)
    fixed = sandbox.repair()
    assert fixed == [SandboxStatus.DANGLING_ACL]
    assert sandbox.status() is SandboxStatus.OK


def test_repair_combines_workspace_and_tool_acl_into_one_status(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    grants = (_grant("/opt/homebrew/bin"),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    fake_system_ops.acl.revoke(identity.workspace, identity.user)
    fake_system_ops.acl.revoke("/opt/homebrew/bin", identity.user)
    fixed = sandbox.repair()
    # Both ACL drifts coalesce into one DANGLING_ACL entry.
    assert fixed == [SandboxStatus.DANGLING_ACL]


def test_create_grants_full_when_existing_acl_was_full(fake_system_ops, tmp_path):
    """If is_granted with a subset says True (actual is superset), don't re-grant."""
    identity = _identity(tmp_path)
    # Pre-grant a superset (full rights).
    fake_system_ops.acl.grant("/opt/homebrew/bin", identity.user)
    grants = (_grant("/opt/homebrew/bin"),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()
    # The original full grant survives — no downgrade.
    assert fake_system_ops.acl.permissions[("/opt/homebrew/bin", identity.user)] is None


def test_destroy_continues_on_shared_tool_revoke_failure(fake_system_ops, tmp_path):
    from unittest.mock import patch

    identity = _identity(tmp_path)
    grants = (_grant("/opt/homebrew/bin"),)
    sandbox = UserSandbox(identity, fake_system_ops, shared_tool_grants=grants)
    sandbox.create()

    def boom_only_for_tool(path, username, permissions=None):
        if path == "/opt/homebrew/bin":
            raise RuntimeError("permission denied")
        # Workspace revoke still works.
        fake_system_ops.acl.grants.get(path, set()).discard(username)
        fake_system_ops.acl.permissions.pop((path, username), None)

    from bal_sbx.core.errors import SandboxBroken

    with patch.object(fake_system_ops.acl, "revoke", side_effect=boom_only_for_tool):
        with pytest.raises(SandboxBroken):
            sandbox.destroy()
    # Despite the failure, user / home cleanup still ran.
    assert not fake_system_ops.users.exists(identity.user)
    assert not fake_system_ops.home.exists(identity.home)
