"""Tests for `bal-sbx tools` subcommands."""

from __future__ import annotations

import json
from unittest.mock import patch

from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.core.config import SandboxConfig
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.shared_tools import Permission, SharedTool
from bal_sbx.registry.json_file import JsonFileRegistry


def _manager(tmp_path, fake_system_ops) -> SandboxManager:
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def _workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# ---- list -------------------------------------------------------------------

def test_list_empty_workspace_prints_friendly_message(capsys, tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(["tools", "list", "--workspace", str(ws)], manager_factory=lambda: manager)
    assert rc == 0
    assert "No shared tools" in capsys.readouterr().out


def test_list_global_after_add(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        [
            "tools", "add", "brew",
            "--path", "/opt/homebrew/bin",
            "--perm", "read", "--perm", "execute",
            "--global",
        ],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    capsys.readouterr()

    rc = main(["tools", "list", "--global"], manager_factory=lambda: manager)
    out = capsys.readouterr().out
    assert "brew" in out
    assert "/opt/homebrew/bin" in out
    assert "read,execute" in out


# ---- add --------------------------------------------------------------------

def test_add_global_writes_registry(tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        [
            "tools", "add", "brew",
            "--path", "/opt/homebrew/bin",
            "--path", "/opt/homebrew/Cellar",
            "--perm", "read", "--perm", "execute", "--perm", "env",
            "--env", "HOMEBREW_PREFIX=/opt/homebrew",
            "--global",
        ],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    cfg = manager._registry.global_config()
    tool = cfg.shared_tools["brew"]
    assert tool.paths == ("/opt/homebrew/bin", "/opt/homebrew/Cellar")
    assert Permission.ENV in tool.permissions
    assert tool.env == {"HOMEBREW_PREFIX": "/opt/homebrew"}


def test_add_per_sandbox_writes_per_sandbox_config(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        [
            "tools", "add", "node",
            "--path", "/opt/homebrew/bin/node",
            "--perm", "read", "--perm", "execute",
            "--workspace", str(ws),
        ],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    identity = manager.resolve(str(ws))
    meta = manager._registry.get(identity.id)
    assert "node" in meta.config.shared_tools
    # And global was not touched
    assert manager._registry.global_config().shared_tools == {}


def test_add_with_bad_env_format_raises(tmp_path, fake_system_ops):
    from bal_sbx.core.errors import ConfigInvalid

    manager = _manager(tmp_path, fake_system_ops)
    try:
        main(
            [
                "tools", "add", "brew",
                "--path", "/opt/homebrew/bin",
                "--perm", "read", "--perm", "execute",
                "--env", "BAD_NO_EQUALS",
                "--global",
            ],
            manager_factory=lambda: manager,
        )
    except ConfigInvalid:
        return
    raise AssertionError("expected ConfigInvalid for malformed --env")


def test_add_invalid_permission_combination_rejected(tmp_path, fake_system_ops):
    from bal_sbx.core.errors import ConfigInvalid

    manager = _manager(tmp_path, fake_system_ops)
    try:
        main(
            [
                "tools", "add", "brew",
                "--path", "/opt/homebrew/bin",
                "--perm", "execute",  # execute without read
                "--global",
            ],
            manager_factory=lambda: manager,
        )
    except ConfigInvalid:
        return
    raise AssertionError("expected ConfigInvalid for execute without read")


# ---- remove -----------------------------------------------------------------

def test_remove_global_revokes_acls_on_affected_sandboxes(tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew_bin"
    bin_dir.mkdir()
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(
            shared_tools={
                "brew": SharedTool(
                    name="brew",
                    paths=(str(bin_dir),),
                    permissions=frozenset({Permission.READ, Permission.EXECUTE}),
                ),
            },
        )
    )
    # Provision the sandbox so the ACL is actually granted
    sandbox = manager.get_or_create(str(ws))
    assert fake_system_ops.acl.is_granted(str(bin_dir), sandbox.identity.user)

    rc = main(["tools", "remove", "brew", "--global"], manager_factory=lambda: manager)
    assert rc == 0
    assert not fake_system_ops.acl.is_granted(str(bin_dir), sandbox.identity.user)
    assert "brew" not in manager._registry.global_config().shared_tools


def test_remove_global_skips_sandboxes_with_per_sandbox_override(tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew_bin"
    bin_dir.mkdir()
    override_dir = tmp_path / "override_bin"
    override_dir.mkdir()
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(
            shared_tools={
                "brew": SharedTool(
                    name="brew",
                    paths=(str(bin_dir),),
                    permissions=frozenset({Permission.READ, Permission.EXECUTE}),
                ),
            },
        )
    )
    # Workspace overrides brew with its own version
    main(
        [
            "tools", "add", "brew",
            "--path", str(override_dir),
            "--perm", "read", "--perm", "execute",
            "--workspace", str(ws),
        ],
        manager_factory=lambda: manager,
    )
    sandbox = manager.get_or_create(str(ws))
    user = sandbox.identity.user
    assert fake_system_ops.acl.is_granted(str(override_dir), user)
    # global brew bin was not granted because per-sandbox replaced it
    assert not fake_system_ops.acl.is_granted(str(bin_dir), user)

    # Removing global brew should NOT revoke the override sandbox's ACL
    main(["tools", "remove", "brew", "--global"], manager_factory=lambda: manager)
    assert fake_system_ops.acl.is_granted(str(override_dir), user)


def test_remove_per_sandbox_revokes_only_that_sandbox(tmp_path, fake_system_ops):
    bin_dir = tmp_path / "node_bin"
    bin_dir.mkdir()
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        [
            "tools", "add", "node",
            "--path", str(bin_dir),
            "--perm", "read", "--perm", "execute",
            "--workspace", str(ws),
        ],
        manager_factory=lambda: manager,
    )
    sandbox = manager.get_or_create(str(ws))
    user = sandbox.identity.user
    assert fake_system_ops.acl.is_granted(str(bin_dir), user)

    main(
        ["tools", "remove", "node", "--workspace", str(ws)],
        manager_factory=lambda: manager,
    )
    assert not fake_system_ops.acl.is_granted(str(bin_dir), user)
    identity = manager.resolve(str(ws))
    assert "node" not in manager._registry.get(identity.id).config.shared_tools


def test_remove_unknown_tool_returns_one(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        ["tools", "remove", "ghost", "--global"],
        manager_factory=lambda: manager,
    )
    assert rc == 1
    assert "ghost" in capsys.readouterr().err


# ---- discover ---------------------------------------------------------------

def test_discover_prints_json_snippet(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    from bal_sbx.core.shared_tools import SharedTool

    class _FakeDetector:
        name = "brew"

        def detect(self):
            return SharedTool(
                name=self.name,
                paths=("/opt/homebrew/bin",),
                permissions=frozenset({Permission.READ, Permission.EXECUTE}),
            )

    with patch(
        "bal_sbx.cli.commands.tools.discover_tools",
        lambda: {"brew": _FakeDetector().detect()},
    ):
        rc = main(["tools", "discover"], manager_factory=lambda: manager)
    assert rc == 0
    snippet = json.loads(capsys.readouterr().out)
    assert "brew" in snippet["shared_tools"]
    assert snippet["shared_tools"]["brew"]["paths"] == ["/opt/homebrew/bin"]


def test_discover_apply_writes_global(tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    from bal_sbx.core.shared_tools import SharedTool

    fake_tools = {
        "brew": SharedTool(
            name="brew",
            paths=("/opt/homebrew/bin",),
            permissions=frozenset({Permission.READ, Permission.EXECUTE}),
        ),
    }

    with patch(
        "bal_sbx.cli.commands.tools.discover_tools",
        lambda: fake_tools,
    ):
        rc = main(
            ["tools", "discover", "--apply", "--global"],
            manager_factory=lambda: manager,
        )
    assert rc == 0
    assert "brew" in manager._registry.global_config().shared_tools


def test_discover_apply_workspace_creates_config_entry(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    from bal_sbx.core.shared_tools import SharedTool

    fake_tools = {
        "node": SharedTool(
            name="node",
            paths=("/opt/homebrew/bin/node",),
            permissions=frozenset({Permission.READ, Permission.EXECUTE}),
        ),
    }

    with patch(
        "bal_sbx.cli.commands.tools.discover_tools",
        lambda: fake_tools,
    ):
        rc = main(
            ["tools", "discover", "--apply", "--workspace", str(ws)],
            manager_factory=lambda: manager,
        )
    assert rc == 0
    identity = manager.resolve(str(ws))
    meta = manager._registry.get(identity.id)
    assert "node" in meta.config.shared_tools


def test_discover_no_tools_prints_message(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    with patch("bal_sbx.cli.commands.tools.discover_tools", lambda: {}):
        rc = main(["tools", "discover"], manager_factory=lambda: manager)
    assert rc == 0
    assert "No host tools" in capsys.readouterr().out
