"""SystemOps — value object bundling the four platform-capability providers."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from bal_sbx.core.errors import PlatformUnsupported
from bal_sbx.system.acl.base import AclManager
from bal_sbx.system.acl.linux import LinuxAclManager
from bal_sbx.system.acl.macos import MacosAclManager
from bal_sbx.system.home import HomeLayout, RealHomeLayout
from bal_sbx.system.privilege import (
    PrivilegeBroker,
    SudoBroker,
    SudoPerOpBroker,
)
from bal_sbx.system.users.base import UserProvisioner
from bal_sbx.system.users.linux import LinuxUserProvisioner
from bal_sbx.system.users.macos import MacosUserProvisioner

_PRIVILEGE_MODES = {"cached": SudoBroker, "per_operation": SudoPerOpBroker}


def _build_broker(privilege_mode: str) -> PrivilegeBroker:
    try:
        return _PRIVILEGE_MODES[privilege_mode]()
    except KeyError as exc:
        raise ValueError(
            f"unknown privilege_mode {privilege_mode!r}; expected one of {sorted(_PRIVILEGE_MODES)}"
        ) from exc


@dataclass(frozen=True)
class SystemOps:
    users: UserProvisioner
    acl: AclManager
    home: HomeLayout
    privilege: PrivilegeBroker

    @classmethod
    def detect(cls, privilege_mode: str = "cached") -> "SystemOps":
        reason = cls.unsupported_reason()
        if reason is not None:
            raise PlatformUnsupported(reason)
        broker = _build_broker(privilege_mode)
        if sys.platform == "linux":
            return cls(
                users=LinuxUserProvisioner(broker),
                acl=LinuxAclManager(broker),
                home=RealHomeLayout(broker),
                privilege=broker,
            )
        if sys.platform == "darwin":
            return cls(
                users=MacosUserProvisioner(broker),
                acl=MacosAclManager(broker),
                home=RealHomeLayout(broker),
                privilege=broker,
            )
        raise PlatformUnsupported(f"unsupported platform {sys.platform!r}")

    @classmethod
    def unsupported_reason(cls) -> str | None:
        if sys.platform in ("linux", "darwin"):
            return None
        return f"unsupported platform {sys.platform!r}; expected 'linux' or 'darwin'"
