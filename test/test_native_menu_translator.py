# coding: utf-8
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QApplication

from app.components.native_menu import (
    MacApplicationMenuTranslator,
    MacNativeMenuController,
)


def test_native_menu_translator_falls_through_with_null_qstring():
    app = QApplication.instance() or QApplication([])
    translator = MacApplicationMenuTranslator(app)
    app.installTranslator(translator)
    try:
        assert QCoreApplication.translate(
            'UnhandledContext',
            'Message with %1',
        ) == 'Message with %1'
    finally:
        app.removeTranslator(translator)


def test_native_view_menu_uses_window_back_state():
    class BackItem:
        def setEnabled_(self, enabled):
            self.enabled = enabled

    class Window:
        def canGoBack(self):
            return False

    controller = MacNativeMenuController.__new__(MacNativeMenuController)
    controller.window = Window()
    controller.backItem = BackItem()
    controller.fullScreenItem = None

    controller.updateViewMenu()

    assert controller.backItem.enabled is False
