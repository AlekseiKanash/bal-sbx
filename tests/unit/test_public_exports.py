"""Verify the top-level public surface listed in `bal_sbx.__all__`."""

import importlib

import bal_sbx


def test_all_names_are_importable_from_package():
    for name in bal_sbx.__all__:
        assert hasattr(bal_sbx, name), f"bal_sbx.__all__ advertises {name!r} but it is missing"


def test_expected_public_names_present():
    expected = {
        "Capabilities",
        "SandboxIdentity",
        "SandboxManager",
        "SandboxMetadata",
        "SandboxMode",
        "SandboxStatus",
        "errors",
    }
    assert expected <= set(bal_sbx.__all__)


def test_errors_module_is_reexported():
    errors_module = importlib.import_module("bal_sbx.core.errors")
    assert bal_sbx.errors is errors_module
    for name in (
        "BalSbxError",
        "PrivilegeDenied",
        "SandboxNotFound",
        "SandboxBroken",
        "PlatformUnsupported",
        "RegistryCorrupt",
    ):
        assert hasattr(bal_sbx.errors, name)
