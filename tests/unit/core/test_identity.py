import os
import secrets

from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/registry.json")


def test_id_is_deterministic(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ids = {SandboxIdentity.from_workspace(str(workspace), LAYOUT).id for _ in range(100)}
    assert len(ids) == 1


def test_id_canonicalizes_path(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "alias"
    os.symlink(target, link)

    via_real = SandboxIdentity.from_workspace(str(target), LAYOUT)
    via_link = SandboxIdentity.from_workspace(str(link), LAYOUT)
    assert via_real == via_link


def test_id_format():
    identity = SandboxIdentity.from_workspace("/tmp/some/path", LAYOUT)
    assert identity.id.startswith("bal_")
    assert len(identity.id) == len("bal_") + 6
    int(identity.id.removeprefix("bal_"), 16)  # hex parse, raises if not


def test_id_uniqueness_sample():
    ids = set()
    for _ in range(1000):
        path = f"/tmp/{secrets.token_hex(8)}"
        ids.add(SandboxIdentity.from_workspace(path, LAYOUT).id)
    assert len(ids) == 1000


def test_identity_fields(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    identity = SandboxIdentity.from_workspace(str(workspace), LAYOUT)

    assert identity.user == identity.id
    assert identity.workspace == os.path.realpath(workspace)
    assert identity.home == os.path.join("/home", identity.id)
    assert identity.workspace_link == os.path.join("/home", identity.id, "workspace")


def test_identity_is_frozen(tmp_path):
    identity = SandboxIdentity.from_workspace(str(tmp_path), LAYOUT)
    import dataclasses

    assert dataclasses.is_dataclass(identity)
    try:
        identity.id = "mutated"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("SandboxIdentity must be frozen")
