import pytest

from bal_sbx.core.errors import ConfigInvalid
from bal_sbx.core.shared_tools import Permission, SharedTool, parse_shared_tool


def _tool(**overrides) -> SharedTool:
    defaults = dict(
        name="brew",
        paths=("/opt/homebrew/bin",),
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
        env={},
    )
    defaults.update(overrides)
    return SharedTool(**defaults)


def test_minimal_tool_construction():
    tool = _tool()
    assert tool.name == "brew"
    assert tool.paths == ("/opt/homebrew/bin",)
    assert Permission.READ in tool.permissions


def test_empty_name_rejected():
    with pytest.raises(ConfigInvalid):
        _tool(name="")


def test_empty_paths_rejected():
    with pytest.raises(ConfigInvalid):
        _tool(paths=())


def test_relative_path_rejected():
    with pytest.raises(ConfigInvalid):
        _tool(paths=("relative/path",))


def test_empty_permissions_rejected():
    with pytest.raises(ConfigInvalid):
        _tool(permissions=frozenset())


def test_execute_without_read_rejected():
    with pytest.raises(ConfigInvalid):
        _tool(permissions=frozenset({Permission.EXECUTE}))


def test_write_without_read_rejected():
    with pytest.raises(ConfigInvalid):
        _tool(permissions=frozenset({Permission.WRITE}))


def test_env_only_permission_allowed_without_read():
    tool = _tool(permissions=frozenset({Permission.ENV}))
    assert tool.acl_permissions == frozenset()


def test_acl_permissions_drops_env():
    tool = _tool(
        permissions=frozenset({Permission.READ, Permission.EXECUTE, Permission.ENV}),
    )
    assert tool.acl_permissions == frozenset({Permission.READ, Permission.EXECUTE})


def test_path_entries_dir_ending_in_bin():
    tool = _tool(paths=("/opt/homebrew/bin",))
    assert tool.path_entries() == ["/opt/homebrew/bin"]


def test_path_entries_strips_trailing_slash():
    tool = _tool(paths=("/opt/homebrew/bin/",))
    assert tool.path_entries() == ["/opt/homebrew/bin"]


def test_path_entries_single_file_uses_parent_when_parent_is_bin():
    tool = _tool(paths=("/usr/local/bin/python3.11",))
    assert tool.path_entries() == ["/usr/local/bin"]


def test_path_entries_omits_non_bin_directories():
    tool = _tool(paths=("/opt/homebrew/Cellar",))
    assert tool.path_entries() == []


def test_path_entries_mixed_bin_and_data():
    tool = _tool(
        paths=("/opt/homebrew/bin", "/opt/homebrew/Cellar", "/opt/homebrew/opt"),
    )
    assert tool.path_entries() == ["/opt/homebrew/bin"]


def test_path_entries_deduplicates():
    tool = _tool(
        paths=(
            "/opt/homebrew/bin",
            "/opt/homebrew/bin/brew",
            "/opt/homebrew/bin/git",
        ),
    )
    assert tool.path_entries() == ["/opt/homebrew/bin"]


def test_to_dict_round_trip_minimal():
    tool = _tool()
    rebuilt = parse_shared_tool("brew", tool.to_dict())
    assert rebuilt == tool


def test_to_dict_round_trip_with_env_permission_and_env():
    tool = _tool(
        permissions=frozenset({Permission.READ, Permission.EXECUTE, Permission.ENV}),
        env={"HOMEBREW_PREFIX": "/opt/homebrew"},
    )
    rebuilt = parse_shared_tool("brew", tool.to_dict())
    assert rebuilt == tool


def test_to_dict_omits_empty_env():
    tool = _tool()
    assert "env" not in tool.to_dict()


def test_to_dict_permissions_are_sorted():
    tool = _tool(
        permissions=frozenset({Permission.EXECUTE, Permission.READ}),
    )
    perms = tool.to_dict()["permissions"]
    assert perms == sorted(perms)


def test_parse_unknown_permission_raises():
    with pytest.raises(ConfigInvalid):
        parse_shared_tool("brew", {"paths": ["/x/bin"], "permissions": ["fly"]})


def test_parse_missing_paths_raises():
    with pytest.raises(ConfigInvalid):
        parse_shared_tool("brew", {"permissions": ["read"]})


def test_parse_missing_permissions_raises():
    with pytest.raises(ConfigInvalid):
        parse_shared_tool("brew", {"paths": ["/x/bin"]})


def test_parse_non_object_entry_raises():
    with pytest.raises(ConfigInvalid):
        parse_shared_tool("brew", "not an object")


def test_parse_non_string_env_value_raises():
    with pytest.raises(ConfigInvalid):
        parse_shared_tool(
            "brew",
            {"paths": ["/x/bin"], "permissions": ["read"], "env": {"K": 1}},
        )
