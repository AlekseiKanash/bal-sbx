"""Public exception taxonomy for bal-sbx."""


class BalSbxError(Exception):
    """Base class for every error raised by bal-sbx."""


class PrivilegeDenied(BalSbxError):
    pass


class SandboxNotFound(BalSbxError):
    pass


class SandboxBroken(BalSbxError):
    pass


class PlatformUnsupported(BalSbxError):
    pass


class RegistryCorrupt(BalSbxError):
    pass
