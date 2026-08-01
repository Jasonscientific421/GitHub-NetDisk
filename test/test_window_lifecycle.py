# coding: utf-8
from types import SimpleNamespace

from PyQt5.QtWidgets import QSystemTrayIcon

from app.components.system_tray_icon import SystemTrayIcon
from app.view.main_window import MainWindow
from app.common.url_scheme import BrowseRepoRequest


class CloseEvent:
    def __init__(self):
        self.accepted = False
        self.ignored = False

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def test_close_event_hides_window_without_quitting(monkeypatch):
    hidden = []
    window = SimpleNamespace(
        _isQuitting=False,
        hide=lambda: hidden.append(True),
        tr=lambda key: key,
    )
    event = CloseEvent()
    monkeypatch.setattr(
        'app.view.main_window.cfg.get', lambda item: False)
    monkeypatch.setattr('app.view.main_window.logChanged', lambda *args, **kwargs: None)

    MainWindow.closeEvent(window, event)

    assert event.ignored
    assert not event.accepted
    assert hidden == [True]


def test_close_event_is_accepted_during_real_quit():
    window = SimpleNamespace(_isQuitting=True)
    event = CloseEvent()

    MainWindow.closeEvent(window, event)

    assert event.accepted
    assert not event.ignored


def test_close_event_quits_when_setting_is_enabled(monkeypatch):
    quit_calls = []
    window = SimpleNamespace(
        _isQuitting=False,
        quitApplication=lambda: quit_calls.append(True),
    )
    event = CloseEvent()
    monkeypatch.setattr(
        'app.view.main_window.cfg.get', lambda item: True)

    MainWindow.closeEvent(window, event)

    assert event.accepted
    assert not event.ignored
    assert quit_calls == [True]


def test_tray_icon_setting_is_applied_immediately():
    calls = []
    tray = SimpleNamespace(
        hide=lambda: calls.append('hide'),
        show=lambda: calls.append('show'),
    )
    window = SimpleNamespace(systemTrayIcon=tray)

    MainWindow.setTrayIconDisabled(window, True)
    MainWindow.setTrayIconDisabled(window, False)

    assert calls == ['hide', 'show']


def test_tray_icon_single_click_requests_show_window():
    calls = []
    tray = SimpleNamespace(
        showWindowRequested=SimpleNamespace(
            emit=lambda: calls.append('show'),
        ),
    )

    SystemTrayIcon.onActivated(tray, QSystemTrayIcon.Trigger)
    SystemTrayIcon.onActivated(tray, QSystemTrayIcon.Context)

    assert calls == ['show']


def test_app_message_activates_window_before_routing(monkeypatch):
    calls = []
    browse = SimpleNamespace(
        browse=lambda repo, branch='': calls.append(('browse', repo, branch)),
    )
    window = SimpleNamespace(
        browseInterface=browse,
        showWindow=lambda: calls.append(('show',)),
        switchTo=lambda interface: calls.append(('switch', interface)),
        tr=lambda key, *args: key,
    )
    monkeypatch.setattr(
        'app.view.main_window.logReceived', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        'app.view.main_window.logger',
        SimpleNamespace(info=lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        'app.view.main_window.parse_app_url',
        lambda value: BrowseRepoRequest('owner/repo', 'main'),
    )

    MainWindow.onAppMessage(window, 'github-netdisk://browse?repo=owner/repo')

    assert calls[0] == ('show',)
    assert calls[1] == ('switch', browse)
    assert calls[2] == ('browse', 'owner/repo', 'main')


def test_new_transfer_task_switches_to_task_interface():
    calls = []
    task_interface = SimpleNamespace(selectPreferredCategory=lambda: calls.append('select'))
    window = SimpleNamespace(
        taskInterface=task_interface,
        stackedWidget=SimpleNamespace(currentWidget=lambda: None),
        showWindow=lambda: calls.append('show'),
        switchTo=lambda interface: calls.append(('switch', interface)),
    )

    MainWindow.showTaskInterfaceForNewTask(window, object())

    assert calls == ['show', ('switch', task_interface)]


def test_new_transfer_task_refreshes_task_tab_when_already_visible():
    calls = []
    task_interface = SimpleNamespace(selectPreferredCategory=lambda: calls.append('select'))
    window = SimpleNamespace(
        taskInterface=task_interface,
        stackedWidget=SimpleNamespace(currentWidget=lambda: task_interface),
        showWindow=lambda: calls.append('show'),
        switchTo=lambda interface: calls.append(('switch', interface)),
    )

    MainWindow.showTaskInterfaceForNewTask(window, object())

    assert calls == ['show', 'select']
