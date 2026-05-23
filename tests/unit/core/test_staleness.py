"""Per-variant tests for `detect_stale`.

One test per stale condition listed in step 11. Each test constructs a
`FakeSystemOps` plus an identity/metadata pair producing exactly that
condition and asserts `detect_stale` returns the expected status list.
"""

from __future__ import annotations

from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.staleness import detect_stale
from bal_sbx.core.status import SandboxStatus
from tests.unit.system.fakes import FakeSystemOps


def _layout(tmp_path) -> PathLayout:
    return PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )


def _make(tmp_path, *, with_workspace: bool = True):
    """Return (identity, metadata, FakeSystemOps). Workspace dir may be skipped."""
    layout = _layout(tmp_path)
    workspace = tmp_path / "ws"
    if with_workspace:
        workspace.mkdir()
    identity = SandboxIdentity.from_workspace(str(workspace), layout)
    meta = SandboxMetadata(
        workspace=identity.workspace,
        created_at="2026-05-23T10:00:00+00:00",
        last_used_at="2026-05-23T10:00:00+00:00",
    )
    return identity, meta, FakeSystemOps()


def _make_healthy(tmp_path):
    identity, meta, ops = _make(tmp_path)
    ops.users.create(identity.user, identity.home)
    ops.home.create(identity.home, identity.user)
    ops.home.link_workspace(identity.home, identity.workspace)
    ops.acl.grant(identity.workspace, identity.user)
    return identity, meta, ops


def test_healthy_sandbox_returns_empty(tmp_path):
    identity, meta, ops = _make_healthy(tmp_path)
    report = detect_stale(identity, meta, ops)
    assert report.statuses == []
    assert report.recoverable is True


def test_missing_workspace(tmp_path):
    identity, meta, ops = _make(tmp_path, with_workspace=False)
    # Otherwise healthy: user, home, link present. ACL grant moot (workspace gone).
    ops.users.create(identity.user, identity.home)
    ops.home.create(identity.home, identity.user)
    ops.home.link_workspace(identity.home, identity.workspace)

    report = detect_stale(identity, meta, ops)
    assert report.statuses == [SandboxStatus.MISSING_WORKSPACE]
    assert report.recoverable is False


def test_missing_user(tmp_path):
    identity, meta, ops = _make(tmp_path)
    # User missing; home also missing → MISSING_USER (not ORPHAN_HOME).
    ops.acl.grant(identity.workspace, identity.user)

    report = detect_stale(identity, meta, ops)
    assert report.statuses == [SandboxStatus.MISSING_USER]
    assert report.recoverable is True


def test_missing_home(tmp_path):
    identity, meta, ops = _make(tmp_path)
    ops.users.create(identity.user, identity.home)
    ops.acl.grant(identity.workspace, identity.user)

    report = detect_stale(identity, meta, ops)
    assert report.statuses == [SandboxStatus.MISSING_HOME]
    assert report.recoverable is True


def test_broken_symlink(tmp_path):
    identity, meta, ops = _make(tmp_path)
    ops.users.create(identity.user, identity.home)
    ops.home.create(identity.home, identity.user)
    ops.home.link_workspace(identity.home, "/some/other/path")
    ops.acl.grant(identity.workspace, identity.user)

    report = detect_stale(identity, meta, ops)
    assert report.statuses == [SandboxStatus.BROKEN_SYMLINK]
    assert report.recoverable is True


def test_dangling_acl(tmp_path):
    identity, meta, ops = _make(tmp_path)
    ops.users.create(identity.user, identity.home)
    ops.home.create(identity.home, identity.user)
    ops.home.link_workspace(identity.home, identity.workspace)
    # No ACL grant.

    report = detect_stale(identity, meta, ops)
    assert report.statuses == [SandboxStatus.DANGLING_ACL]
    assert report.recoverable is True


def test_orphan_home(tmp_path):
    identity, meta, ops = _make(tmp_path)
    # Home present, user missing → ORPHAN_HOME (excludes MISSING_USER).
    ops.home.create(identity.home, identity.user)
    ops.home.link_workspace(identity.home, identity.workspace)
    ops.acl.grant(identity.workspace, identity.user)

    report = detect_stale(identity, meta, ops)
    assert report.statuses == [SandboxStatus.ORPHAN_HOME]
    assert report.recoverable is True


def test_invalid_metadata_bad_timestamp(tmp_path):
    identity, _meta, ops = _make_healthy(tmp_path)
    bad = SandboxMetadata(
        workspace=identity.workspace,
        created_at="not-a-date",
        last_used_at="2026-05-23T10:00:00+00:00",
    )

    report = detect_stale(identity, bad, ops)
    assert SandboxStatus.INVALID_METADATA in report.statuses
    assert report.recoverable is False


def test_invalid_metadata_empty_workspace(tmp_path):
    identity, _meta, ops = _make_healthy(tmp_path)
    bad = SandboxMetadata(
        workspace="",
        created_at="2026-05-23T10:00:00+00:00",
        last_used_at="2026-05-23T10:00:00+00:00",
    )

    report = detect_stale(identity, bad, ops)
    assert SandboxStatus.INVALID_METADATA in report.statuses
    assert report.recoverable is False


def test_detect_stale_runs_all_checks_not_first_wins(tmp_path):
    """Unlike `Sandbox.status()`, detect_stale enumerates every problem."""
    identity, meta, ops = _make(tmp_path)
    # User missing AND home missing AND ACL missing — multiple independent issues.
    report = detect_stale(identity, meta, ops)
    assert SandboxStatus.MISSING_USER in report.statuses
    assert SandboxStatus.DANGLING_ACL in report.statuses
    # MISSING_HOME requires user_present; here user missing, so it's not added.
    assert SandboxStatus.MISSING_HOME not in report.statuses
    # Multiple statuses → not first-wins.
    assert len(report.statuses) >= 2
