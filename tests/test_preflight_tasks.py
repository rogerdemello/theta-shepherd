"""Regression tests for the scheduled-task readiness check.

On Mon Aug 31 all four tasks were registered — the old check passed — yet none
had ever run: paths were stored unquoted (0x80070002 every 20 min) and
DisallowStartIfOnBatteries kept them Queued on an unplugged laptop. Two hours
of a live session were lost. Registration is not readiness.
"""

import xml.etree.ElementTree as ET

import pytest

from theta_shepherd import preflight

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def task_xml(command: str, arguments: str = "", *, on_batteries: bool = False,
             enabled: bool = True) -> ET.Element:
    return ET.fromstring(f"""<?xml version="1.0"?>
    <Task xmlns="{NS}">
      <Settings>
        <DisallowStartIfOnBatteries>{str(on_batteries).lower()}</DisallowStartIfOnBatteries>
        <Enabled>{str(enabled).lower()}</Enabled>
      </Settings>
      <Actions>
        <Exec>
          <Command>{command}</Command>
          <Arguments>{arguments}</Arguments>
        </Exec>
      </Actions>
    </Task>""")


def test_launched_target_unwraps_cmd_wrapper():
    root = task_xml("cmd.exe", '/c ""E:\\Alapaca hackathon\\scheduler_cycle.bat""')
    assert preflight._launched_target(root) == "E:\\Alapaca hackathon\\scheduler_cycle.bat"


def test_launched_target_handles_direct_exec():
    root = task_xml('"E:\\Alapaca hackathon\\scheduler_cycle.bat"')
    assert preflight._launched_target(root) == "E:\\Alapaca hackathon\\scheduler_cycle.bat"


def test_launched_target_keeps_space_bearing_path_intact():
    """The original bug: the path split at the space and only 'E:\\Alapaca' ran."""
    root = task_xml("E:\\Alapaca hackathon\\scheduler_cycle.bat")
    assert preflight._launched_target(root) != "E:\\Alapaca"
    assert "hackathon" in preflight._launched_target(root)


@pytest.fixture
def stub_schtasks(monkeypatch):
    """Drive _check_schtasks with one synthetic task."""
    def apply(root, last_result=0):
        monkeypatch.setattr(preflight, "SCHEDULED_TASKS", ["Fake Task"])
        monkeypatch.setattr(preflight, "_task_xml", lambda name: root)
        monkeypatch.setattr(preflight, "_last_result", lambda name: last_result)
    return apply


def test_battery_gate_is_a_failure(stub_schtasks, tmp_path):
    bat = tmp_path / "cycle.bat"
    bat.write_text("@echo off")
    stub_schtasks(task_xml("cmd.exe", f'/c ""{bat}""', on_batteries=True))
    ok, detail = preflight._check_schtasks()
    assert not ok and "battery" in detail


def test_launch_failure_result_is_a_failure(stub_schtasks, tmp_path):
    bat = tmp_path / "cycle.bat"
    bat.write_text("@echo off")
    stub_schtasks(task_xml("cmd.exe", f'/c ""{bat}""'), last_result=-2147024894)
    ok, detail = preflight._check_schtasks()
    assert not ok and "0x80070002" in detail


def test_missing_target_script_is_a_failure(stub_schtasks, tmp_path):
    stub_schtasks(task_xml("cmd.exe", f'/c ""{tmp_path / "gone.bat"}""'))
    ok, detail = preflight._check_schtasks()
    assert not ok and "target missing" in detail


def test_disabled_task_is_a_failure(stub_schtasks, tmp_path):
    bat = tmp_path / "cycle.bat"
    bat.write_text("@echo off")
    stub_schtasks(task_xml("cmd.exe", f'/c ""{bat}""', enabled=False))
    ok, detail = preflight._check_schtasks()
    assert not ok and "disabled" in detail


def test_unregistered_task_is_a_failure(stub_schtasks):
    stub_schtasks(None)
    ok, detail = preflight._check_schtasks()
    assert not ok and "not registered" in detail


def test_healthy_task_passes(stub_schtasks, tmp_path):
    bat = tmp_path / "cycle.bat"
    bat.write_text("@echo off")
    stub_schtasks(task_xml("cmd.exe", f'/c ""{bat}""'))
    ok, detail = preflight._check_schtasks()
    assert ok and "launchable" in detail
