import pytest

from bal_sbx.core.config import SandboxConfig
from bal_sbx.core.errors import ConfigInvalid
from bal_sbx.core.shared_tools import Permission, SharedTool


def _brew() -> SharedTool:
    return SharedTool(
        name="brew",
        paths=("/opt/homebrew/bin",),
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )


def _node() -> SharedTool:
    return SharedTool(
        name="node",
        paths=("/opt/homebrew/bin/node",),
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )


def test_empty_config_round_trip():
    cfg = SandboxConfig()
    assert SandboxConfig.from_dict(cfg.to_dict()) == cfg


def test_to_dict_omits_empty_sections():
    assert SandboxConfig().to_dict() == {}


def test_from_dict_handles_none():
    assert SandboxConfig.from_dict(None) == SandboxConfig()


def test_round_trip_with_env_and_tools():
    cfg = SandboxConfig(env={"K": "v"}, shared_tools={"brew": _brew()})
    assert SandboxConfig.from_dict(cfg.to_dict()) == cfg


def test_from_dict_non_object_raises():
    with pytest.raises(ConfigInvalid):
        SandboxConfig.from_dict([])


def test_from_dict_env_must_be_object():
    with pytest.raises(ConfigInvalid):
        SandboxConfig.from_dict({"env": []})


def test_from_dict_env_values_must_be_strings():
    with pytest.raises(ConfigInvalid):
        SandboxConfig.from_dict({"env": {"K": 1}})


def test_from_dict_shared_tools_must_be_object():
    with pytest.raises(ConfigInvalid):
        SandboxConfig.from_dict({"shared_tools": []})


def test_merged_with_replaces_env_per_key():
    base = SandboxConfig(env={"A": "1", "B": "2"})
    override = SandboxConfig(env={"B": "20", "C": "3"})
    merged = base.merged_with(override)
    assert merged.env == {"A": "1", "B": "20", "C": "3"}


def test_merged_with_replaces_tools_per_name():
    base = SandboxConfig(shared_tools={"brew": _brew(), "node": _node()})
    replacement = SharedTool(
        name="brew",
        paths=("/usr/local/bin",),
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
    )
    override = SandboxConfig(shared_tools={"brew": replacement})
    merged = base.merged_with(override)
    assert merged.shared_tools["brew"] == replacement
    assert merged.shared_tools["node"] == _node()


def test_merged_with_does_not_mutate_inputs():
    base = SandboxConfig(env={"A": "1"}, shared_tools={"brew": _brew()})
    override = SandboxConfig(env={"A": "2"}, shared_tools={"node": _node()})
    base.merged_with(override)
    assert base.env == {"A": "1"}
    assert override.env == {"A": "2"}
