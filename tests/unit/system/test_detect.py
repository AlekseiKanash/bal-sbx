import pytest

from bal_sbx.core.errors import PlatformUnsupported
from bal_sbx.system.acl.linux import LinuxAclManager
from bal_sbx.system.acl.macos import MacosAclManager
from bal_sbx.system.home import RealHomeLayout
from bal_sbx.system.ops import SystemOps
from bal_sbx.system.privilege import SudoBroker, SudoPerOpBroker
from bal_sbx.system.users.linux import LinuxUserProvisioner
from bal_sbx.system.users.macos import MacosUserProvisioner


def test_detect_linux_wires_linux_providers(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "linux")
    ops = SystemOps.detect()
    assert isinstance(ops.users, LinuxUserProvisioner)
    assert isinstance(ops.acl, LinuxAclManager)
    assert isinstance(ops.home, RealHomeLayout)
    assert isinstance(ops.privilege, SudoBroker)


def test_detect_darwin_wires_macos_providers(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "darwin")
    ops = SystemOps.detect()
    assert isinstance(ops.users, MacosUserProvisioner)
    assert isinstance(ops.acl, MacosAclManager)
    assert isinstance(ops.home, RealHomeLayout)
    assert isinstance(ops.privilege, SudoBroker)


def test_detect_per_operation_mode_yields_per_op_broker(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "linux")
    ops = SystemOps.detect(privilege_mode="per_operation")
    assert isinstance(ops.privilege, SudoPerOpBroker)


def test_detect_unknown_mode_raises(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "linux")
    with pytest.raises(ValueError, match="unknown privilege_mode"):
        SystemOps.detect(privilege_mode="bogus")


def test_detect_on_win32_raises_platform_unsupported(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "win32")
    with pytest.raises(PlatformUnsupported, match="win32"):
        SystemOps.detect()


def test_detect_shares_broker_across_providers(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "linux")
    ops = SystemOps.detect()
    assert ops.users._privilege is ops.privilege
    assert ops.acl._privilege is ops.privilege
    assert ops.home._privilege is ops.privilege


def test_unsupported_reason_none_on_linux(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "linux")
    assert SystemOps.unsupported_reason() is None


def test_unsupported_reason_none_on_darwin(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "darwin")
    assert SystemOps.unsupported_reason() is None


def test_unsupported_reason_string_on_other(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.ops.sys.platform", "win32")
    reason = SystemOps.unsupported_reason()
    assert reason is not None
    assert "win32" in reason
