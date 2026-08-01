# coding: utf-8
"""Cross-platform QSystemTrayIcon and tray menu."""
import sys

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon
from qfluentwidgets import SystemTrayMenu

from ..common.event_logger import logInitialized
from ..common.translator import translate


class SystemTrayIcon(QSystemTrayIcon):
    showWindowRequested = pyqtSignal()
    toggleWindowRequested = pyqtSignal()
    settingsRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self._initializedLogged = False
        self.setIcon(parent.windowIcon())
        self.setToolTip(self.tr('App.Name'))

        self.menu = (
            QMenu(parent)
            if sys.platform == 'darwin'
            else SystemTrayMenu(parent=parent)
        )
        self.visibilityAction = QAction(
            self.tr('SystemTray.ToggleWindow'), self)
        self.settingsAction = QAction(
            self.tr('SystemTray.Settings'), self)
        self.quitAction = QAction(
            self.tr('SystemTray.Quit'), self)
        self.menu.addActions([self.visibilityAction, self.settingsAction])
        self.menu.addSeparator()
        self.menu.addAction(self.quitAction)
        self.setContextMenu(self.menu)

        self.visibilityAction.triggered.connect(
            lambda _: self.toggleWindowRequested.emit())
        self.settingsAction.triggered.connect(
            lambda _: self.settingsRequested.emit())
        self.quitAction.triggered.connect(
            lambda _: self.quitRequested.emit())
        self.activated.connect(self.onActivated)

    def onActivated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.showWindowRequested.emit()

    def show(self):
        super().show()
        if not self._initializedLogged:
            self._initializedLogged = True
            logInitialized('Log.Action.SystemTray', self.tr('App.Name'))
