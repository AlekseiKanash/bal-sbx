import os
from unittest.mock import MagicMock

import pytest

from bal_sbx.system.home import RealHomeLayout
from bal_sbx.system.privilege import PrivilegeBroker


@pytest.fixture
def broker():
    return MagicMock(spec=PrivilegeBroker)


def test_create_makes_directory(broker, tmp_path):
    home = tmp_path / "alice"
    RealHomeLayout(broker).create(str(home), "alice")
    assert home.is_dir()


def test_create_routes_chown_through_broker(broker, tmp_path):
    home = tmp_path / "alice"
    RealHomeLayout(broker).create(str(home), "alice")
    broker.run_privileged.assert_called_once_with(["chown", "-R", "alice", str(home)])


def test_create_is_idempotent(broker, tmp_path):
    home = tmp_path / "alice"
    layout = RealHomeLayout(broker)
    layout.create(str(home), "alice")
    layout.create(str(home), "alice")
    assert home.is_dir()


def test_destroy_removes_existing_home(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    (home / "data.txt").write_text("payload")
    RealHomeLayout(broker).destroy(str(home))
    assert not home.exists()


def test_destroy_absent_home_is_noop(broker, tmp_path):
    RealHomeLayout(broker).destroy(str(tmp_path / "ghost"))


def test_exists_true_for_directory(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    assert RealHomeLayout(broker).exists(str(home)) is True


def test_exists_false_for_missing(broker, tmp_path):
    assert RealHomeLayout(broker).exists(str(tmp_path / "ghost")) is False


def test_link_workspace_creates_symlink(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    workspace = tmp_path / "proj"
    workspace.mkdir()
    RealHomeLayout(broker).link_workspace(str(home), str(workspace))
    link = home / ".bal" / "workspace"
    assert link.is_symlink()
    assert os.readlink(link) == str(workspace)


def test_link_workspace_replaces_existing_link(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    layout = RealHomeLayout(broker)
    layout.link_workspace(str(home), str(a))
    layout.link_workspace(str(home), str(b))
    assert os.readlink(home / ".bal" / "workspace") == str(b)


def test_workspace_link_target_returns_target(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    workspace = tmp_path / "proj"
    workspace.mkdir()
    layout = RealHomeLayout(broker)
    layout.link_workspace(str(home), str(workspace))
    assert layout.workspace_link_target(str(home)) == str(workspace)


def test_workspace_link_target_none_when_missing(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    assert RealHomeLayout(broker).workspace_link_target(str(home)) is None


def test_link_workspace_does_not_call_privilege_broker(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    workspace = tmp_path / "proj"
    workspace.mkdir()
    RealHomeLayout(broker).link_workspace(str(home), str(workspace))
    broker.run_privileged.assert_not_called()
