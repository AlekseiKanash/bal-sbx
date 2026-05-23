import pytest

from tests.unit.system.fakes import FakeSystemOps


@pytest.fixture
def fake_system_ops():
    return FakeSystemOps()
