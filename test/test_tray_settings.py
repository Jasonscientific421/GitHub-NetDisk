# coding: utf-8
from types import SimpleNamespace

from app.common.config import SafeFolderValidator
from app.common.config import Config
from app.view.setting_interface import SettingInterface


class Switch:
    def __init__(self, checked=False):
        self.checked = checked
        self.enabled = True
        self.blocked = False

    def blockSignals(self, blocked):
        self.blocked = blocked

    def setChecked(self, checked):
        self.checked = checked

    def setEnabled(self, enabled):
        self.enabled = enabled


def test_disable_tray_icon_defaults_to_off():
    assert Config.disableTrayIcon.defaultValue is False
    assert Config.exitOnClose.defaultValue is False


def test_exit_on_close_is_forced_on_when_disable_tray_is_on(monkeypatch):
    switch = Switch(False)
    interface = SimpleNamespace(exitOnCloseSwitch=switch)
    writes = []
    monkeypatch.setattr(
        'app.view.setting_interface.cfg.set',
        lambda item, value: writes.append((item, value)),
    )

    SettingInterface._syncTraySettingDependency(
        interface, True, persist=True)

    assert switch.checked
    assert not switch.enabled
    assert writes[-1] == (Config.exitOnClose, True)


def test_exit_on_close_is_editable_when_disable_tray_is_off():
    switch = Switch(True)
    interface = SimpleNamespace(exitOnCloseSwitch=switch)

    SettingInterface._syncTraySettingDependency(
        interface, False, persist=False)

    assert switch.checked
    assert switch.enabled


def test_unavailable_save_folder_falls_back(monkeypatch, tmp_path):
    fallback = tmp_path / 'downloads'
    validator = SafeFolderValidator(str(fallback))

    def fail_for_configured_path(self, *args, **kwargs):
        if self.as_posix().endswith('blocked'):
            raise PermissionError('blocked')
        return original_mkdir(self, *args, **kwargs)

    original_mkdir = type(fallback).mkdir
    monkeypatch.setattr(type(fallback), 'mkdir', fail_for_configured_path)

    assert validator.correct(str(tmp_path / 'blocked')) == str(
        fallback.absolute()).replace('\\', '/')
