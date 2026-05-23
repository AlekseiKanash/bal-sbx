"""Tests for `bal-sbx sandbox repair` and `SandboxManager.repair_all`."""

from __future__ import annotations

from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.status import SandboxStatus
from bal_sbx.registry.json_file import JsonFileRegistry


def _layout(tmp_path) -> PathLayout:
    return PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )


def _manager(tmp_path, fake_system_ops) -> SandboxManager:
    layout = _layout(tmp_path)
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def _register(manager: SandboxManager, workspace: str) -> SandboxIdentity:
    identity = SandboxIdentity.from_workspace(workspace, manager._path_layout)
    manager._registry.put(
        identity.id,
        SandboxMetadata(
            workspace=identity.workspace,
            created_at="2026-05-23T10:00:00+00:00",
            last_used_at="2026-05-23T10:00:00+00:00",
        ),
    )
    return identity


def _snapshot(ops):
    return (
        set(ops.users.users),
        dict(ops.home.homes),
        {k: set(v) for k, v in ops.acl.grants.items()},
    )


def test_repair_all_dry_run_does_not_mutate(tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _register(manager, str(workspace))

    before = _snapshot(fake_system_ops)
    reports = manager.repair_all(dry_run=True)
    after = _snapshot(fake_system_ops)

    assert before == after
    assert len(reports) == 1
    assert reports[0].statuses  # at least one issue


def test_repair_all_fixes_recoverable_leaves_missing_workspace(
    tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)

    ws_a = tmp_path / "ws_a"  # user missing (recoverable)
    ws_b = tmp_path / "ws_b"  # ACL missing only (recoverable)
    ws_c_path = str(tmp_path / "ws_c_gone")  # never created (MISSING_WORKSPACE)
    ws_a.mkdir()
    ws_b.mkdir()

    id_a = _register(manager, str(ws_a))
    id_b = _register(manager, str(ws_b))
    id_c = _register(manager, ws_c_path)

    # B is otherwise healthy except ACL.
    fake_system_ops.users.create(id_b.user, id_b.home)
    fake_system_ops.home.create(id_b.home, id_b.user)
    fake_system_ops.home.link_workspace(id_b.home, id_b.workspace)

    reports = manager.repair_all(dry_run=False)

    assert len(reports) == 3

    # A was repaired: user + home + link + ACL grant all present.
    assert fake_system_ops.users.exists(id_a.user)
    assert fake_system_ops.home.exists(id_a.home)
    assert fake_system_ops.home.workspace_link_target(id_a.home) == id_a.workspace
    assert fake_system_ops.acl.is_granted(id_a.workspace, id_a.user)

    # B was repaired: ACL grant now present.
    assert fake_system_ops.acl.is_granted(id_b.workspace, id_b.user)

    # C was NOT repaired: workspace still missing, no user/home created.
    assert not fake_system_ops.users.exists(id_c.user)
    assert not fake_system_ops.home.exists(id_c.home)

    # Find the C report and assert MISSING_WORKSPACE flagged.
    c_report = next(r for r in reports if r.identity.id == id_c.id)
    assert SandboxStatus.MISSING_WORKSPACE in c_report.statuses
    assert c_report.recoverable is False


def test_cmd_repair_prints_summary(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    ws = tmp_path / "ws"
    ws.mkdir()
    identity = _register(manager, str(ws))

    rc = main(["sandbox", "repair"], manager_factory=lambda: manager)

    assert rc == 0
    out = capsys.readouterr().out
    assert identity.id in out
    assert "repaired" in out


def test_cmd_repair_dry_run_prints_would(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    ws = tmp_path / "ws"
    ws.mkdir()
    identity = _register(manager, str(ws))

    rc = main(["sandbox", "repair", "--dry-run"], manager_factory=lambda: manager)

    assert rc == 0
    out = capsys.readouterr().out
    assert identity.id in out
    assert "would repair" in out
    # Dry-run leaves system untouched.
    assert not fake_system_ops.users.exists(identity.user)


def test_cmd_repair_healthy_returns_ok(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    ws = tmp_path / "ws"
    ws.mkdir()
    manager.get_or_create(str(ws))

    rc = main(["sandbox", "repair"], manager_factory=lambda: manager)

    assert rc == 0
    assert "All sandboxes healthy." in capsys.readouterr().out
