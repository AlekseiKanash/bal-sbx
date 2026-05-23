from bal_sbx.core.errors import (
    BalSbxError,
    PlatformUnsupported,
    PrivilegeDenied,
    RegistryCorrupt,
    SandboxBroken,
    SandboxNotFound,
)


def test_all_concrete_errors_subclass_base():
    for cls in (
        PrivilegeDenied,
        SandboxNotFound,
        SandboxBroken,
        PlatformUnsupported,
        RegistryCorrupt,
    ):
        assert issubclass(cls, BalSbxError)


def test_errors_accept_single_message():
    for cls in (
        BalSbxError,
        PrivilegeDenied,
        SandboxNotFound,
        SandboxBroken,
        PlatformUnsupported,
        RegistryCorrupt,
    ):
        err = cls("boom")
        assert str(err) == "boom"
