# coding: utf-8
import sys

if sys.platform == 'win32' and sys.getwindowsversion().build >= 14393:
    from qfluentwidgets import SystemThemeListener
elif sys.platform == 'darwin':
    from qfluentwidgets import SystemThemeListener
else:
    from PyQt5.QtCore import QThread, pyqtSignal

    class SystemThemeListener(QThread):
        """ System theme listener (fake) """

        systemThemeChanged = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent=parent)

        def run(self):
            pass

        def _onThemeChanged(self, time: str):
            pass


def stopSystemThemeListener(listener):
    """Synchronously stop a theme listener before its owner is destroyed."""
    if listener is None or not listener.isRunning():
        return
    listener.terminate()
    listener.wait()
