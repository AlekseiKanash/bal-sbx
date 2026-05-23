import subprocess

import pytest

from bal_sbx.system.privilege import SudoBroker, SudoPerOpBroker


class FakeRunner:
    """Recorder for monkeypatched subprocess.run."""

    def __init__(self, side_effects=None):
        self.calls: list[list[str]] = []
        self._side_effects = list(side_effects) if side_effects else []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self._side_effects:
            effect = self._side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")


@pytest.fixture
def runner(monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr("bal_sbx.system.privilege.subprocess.run", fake)
    return fake


def test_sudo_broker_validates_once_across_multiple_calls(runner):
    broker = SudoBroker()
    broker.run_privileged(["useradd", "alice"])
    broker.run_privileged(["userdel", "alice"])
    validate_calls = [c for c in runner.calls if c == ["sudo", "-v"]]
    assert len(validate_calls) == 1


def test_sudo_broker_prefixes_subsequent_calls_with_sudo_n(runner):
    broker = SudoBroker()
    broker.run_privileged(["useradd", "alice"])
    broker.run_privileged(["userdel", "alice"])
    privileged = [c for c in runner.calls if c[:1] == ["sudo"] and c != ["sudo", "-v"]]
    assert privileged == [
        ["sudo", "-n", "useradd", "alice"],
        ["sudo", "-n", "userdel", "alice"],
    ]


def test_sudo_broker_revalidates_once_when_n_fails(monkeypatch):
    side_effects = [
        subprocess.CompletedProcess(args=["sudo", "-v"], returncode=0),
        subprocess.CalledProcessError(returncode=1, cmd=["sudo", "-n", "useradd", "alice"]),
        subprocess.CompletedProcess(args=["sudo", "-v"], returncode=0),
        subprocess.CompletedProcess(args=["sudo", "-n", "useradd", "alice"], returncode=0),
    ]
    fake = FakeRunner(side_effects=side_effects)
    monkeypatch.setattr("bal_sbx.system.privilege.subprocess.run", fake)
    SudoBroker().run_privileged(["useradd", "alice"])
    assert fake.calls == [
        ["sudo", "-v"],
        ["sudo", "-n", "useradd", "alice"],
        ["sudo", "-v"],
        ["sudo", "-n", "useradd", "alice"],
    ]


def test_sudo_broker_propagates_error_if_retry_also_fails(monkeypatch):
    side_effects = [
        subprocess.CompletedProcess(args=["sudo", "-v"], returncode=0),
        subprocess.CalledProcessError(returncode=1, cmd=["sudo", "-n", "x"]),
        subprocess.CompletedProcess(args=["sudo", "-v"], returncode=0),
        subprocess.CalledProcessError(returncode=1, cmd=["sudo", "-n", "x"]),
    ]
    monkeypatch.setattr(
        "bal_sbx.system.privilege.subprocess.run", FakeRunner(side_effects=side_effects)
    )
    with pytest.raises(subprocess.CalledProcessError):
        SudoBroker().run_privileged(["x"])


def test_sudo_broker_is_available_true_when_probe_succeeds(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.privilege.shutil.which", lambda b: "/usr/bin/sudo")
    fake = FakeRunner(
        side_effects=[subprocess.CompletedProcess(args=["sudo", "-n", "true"], returncode=0)]
    )
    monkeypatch.setattr("bal_sbx.system.privilege.subprocess.run", fake)
    assert SudoBroker().is_available() is True


def test_sudo_broker_is_available_false_when_sudo_missing(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.privilege.shutil.which", lambda b: None)
    assert SudoBroker().is_available() is False


def test_sudo_broker_is_available_false_when_probe_fails(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.privilege.shutil.which", lambda b: "/usr/bin/sudo")
    fake = FakeRunner(
        side_effects=[subprocess.CompletedProcess(args=["sudo", "-n", "true"], returncode=1)]
    )
    monkeypatch.setattr("bal_sbx.system.privilege.subprocess.run", fake)
    assert SudoBroker().is_available() is False


def test_per_op_broker_prefixes_every_call_with_sudo(runner):
    broker = SudoPerOpBroker()
    broker.run_privileged(["useradd", "alice"])
    broker.run_privileged(["userdel", "alice"])
    assert runner.calls == [
        ["sudo", "useradd", "alice"],
        ["sudo", "userdel", "alice"],
    ]


def test_per_op_broker_never_calls_sudo_v(runner):
    SudoPerOpBroker().run_privileged(["whoami"])
    assert ["sudo", "-v"] not in runner.calls


def test_per_op_broker_is_available_tracks_sudo_on_path(monkeypatch):
    monkeypatch.setattr("bal_sbx.system.privilege.shutil.which", lambda b: "/usr/bin/sudo")
    assert SudoPerOpBroker().is_available() is True
    monkeypatch.setattr("bal_sbx.system.privilege.shutil.which", lambda b: None)
    assert SudoPerOpBroker().is_available() is False
