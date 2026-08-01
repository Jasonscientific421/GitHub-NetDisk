# coding: utf-8
"""Application menus and cross-platform shortcuts."""
import sys

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent, QKeySequence
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QMenuBar)

from ..common.translator import translate


def settingsShortcuts(platform=None):
    platform = platform or sys.platform
    return (QKeySequence.Preferences if platform == 'darwin'
            else [QKeySequence('Ctrl+,')])


def backShortcuts(platform=None):
    platform = platform or sys.platform
    return [QKeySequence(
        'Ctrl+[' if platform == 'darwin' else 'Alt+Left'
    )]


class MenuBar(QMenuBar):
    """Menu bar for the main window."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.setNativeMenuBar(True)

        # File
        self.fileMenu = self.addMenu(self.tr('MenuBar.File'))
        self.addTaskAct = QAction(self.tr('AddTask.Action'), self)
        self.addTaskAct.setShortcuts(QKeySequence.New)
        self.homeAct = QAction(self.tr('MenuBar.Home'), self)
        self.browseAct = QAction(self.tr('MenuBar.Browse'), self)
        self.tasksAct = QAction(self.tr('MenuBar.Tasks'), self)
        self.accountAct = QAction(self.tr('MainWindow.Account'), self)
        self.interfaceActionGroup = QActionGroup(self)
        self.interfaceActionGroup.setExclusive(True)
        self.interfaceActions = {
            'homeInterface': self.homeAct,
            'browseInterface': self.browseAct,
            'taskInterface': self.tasksAct,
            'accountInterface': self.accountAct,
        }
        for index, action in enumerate(self.interfaceActions.values(), start=1):
            action.setCheckable(True)
            action.setShortcut(QKeySequence(f'Ctrl+{index}'))
            self.interfaceActionGroup.addAction(action)

        self.settingsAct = QAction(self.tr('MenuBar.Preferences'), self)
        self.settingsAct.setShortcuts(settingsShortcuts())
        self.settingsAct.setMenuRole(
            QAction.PreferencesRole
            if sys.platform == 'darwin'
            else QAction.NoRole)
        self.closeWindowAct = QAction(self.tr('MenuBar.CloseWindow'), self)
        self.closeWindowAct.setShortcuts(QKeySequence.Close)
        self.quitAct = QAction(self.tr('MenuBar.Quit'), self)
        self.quitAct.setShortcuts(QKeySequence.Quit)
        self.quitAct.setMenuRole(QAction.QuitRole)
        self.backAct = QAction(self.tr('MenuBar.Back'), self)
        self.backAct.setShortcuts(backShortcuts())
        self.fullScreenAct = QAction(
            self.tr('MenuBar.EnterFullScreen'), self)
        self.fullScreenAct.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.FullScreen))

        # Edit actions must call the focused Qt widget. Cocoa's responder
        # selectors do not reach widgets hosted by Qt, and a hidden menu bar
        # alone does not provide these shortcuts on other platforms.
        self.undoAct = self._createEditAction(
            'MenuBar.Undo', QKeySequence.Undo, 'undo')
        self.redoAct = self._createEditAction(
            'MenuBar.Redo', QKeySequence.Redo, 'redo')
        self.cutAct = self._createEditAction(
            'MenuBar.Cut', QKeySequence.Cut, 'cut')
        self.copyAct = self._createEditAction(
            'MenuBar.Copy', QKeySequence.Copy, 'copy')
        self.pasteAct = self._createEditAction(
            'MenuBar.Paste', QKeySequence.Paste, 'paste')
        self.deleteEditAct = self._createEditAction(
            'MenuBar.Delete', QKeySequence.Delete, 'delete')
        self.selectAllAct = self._createEditAction(
            'MenuBar.SelectAll', QKeySequence.SelectAll, 'selectAll')
        self.editActions = [
            self.undoAct, self.redoAct, self.cutAct, self.copyAct,
            self.pasteAct, self.deleteEditAct, self.selectAllAct,
        ]

        self.fileMenu.addAction(self.addTaskAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addActions(list(self.interfaceActions.values()))
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.settingsAct)
        self.fileMenu.addActions([self.closeWindowAct, self.quitAct])

        # Help
        self.helpMenu = self.addMenu(self.tr('MenuBar.Help'))
        self.helpAct = QAction(self.tr('MenuBar.OpenHelp'), self)
        self.helpAct.setShortcuts(QKeySequence.HelpContents)
        self.feedbackAct = QAction(self.tr('MenuBar.Feedback'), self)
        self.aboutQtAct = QAction(
            self.tr('MacApplicationMenu.AboutQt'), self)
        self.aboutQtAct.setMenuRole(QAction.AboutQtRole)
        self.aboutAct = QAction(self.tr('MenuBar.About'), self)
        self.aboutAct.setMenuRole(QAction.AboutRole)
        self.helpMenu.addActions([
            self.helpAct,
            self.feedbackAct,
            self.aboutQtAct,
            self.aboutAct,
        ])

    def shortcutActions(self):
        return [
            self.addTaskAct,
            *self.interfaceActions.values(),
            self.settingsAct,
            self.closeWindowAct,
            self.quitAct,
            self.helpAct,
            self.backAct,
            self.fullScreenAct,
            *self.editActions,
        ]

    def _createEditAction(self, text_key, standard_key, operation):
        action = QAction(self.tr(text_key), self)
        action.setShortcuts(QKeySequence.keyBindings(standard_key))
        action.triggered.connect(lambda _=False, name=operation:
                                 self.triggerEdit(name))
        return action

    def triggerEdit(self, operation):
        """Apply an Edit-menu operation to the current Qt focus widget."""
        widget = QApplication.focusWidget()
        if widget is None:
            return False
        if operation == 'delete':
            QApplication.sendEvent(
                widget, QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
            QApplication.sendEvent(
                widget, QKeyEvent(QEvent.KeyRelease, Qt.Key_Delete, Qt.NoModifier))
            return True
        callback = getattr(widget, operation, None)
        if not callable(callback):
            return False
        callback()
        return True

    def isEditOperationEnabled(self, operation):
        """Return whether the focused Qt widget can perform an edit action."""
        widget = QApplication.focusWidget()
        if widget is None or not widget.isEnabled():
            return False

        read_only = getattr(widget, 'isReadOnly', lambda: False)()
        has_selection = False
        cursor = None
        selected_text = getattr(widget, 'hasSelectedText', None)
        if callable(selected_text):
            has_selection = bool(selected_text())
        else:
            text_cursor = getattr(widget, 'textCursor', None)
            if callable(text_cursor):
                cursor = text_cursor()
                has_selection = bool(
                    cursor is not None and cursor.hasSelection())

        if operation in ('undo', 'redo'):
            method_name = (
                'isUndoAvailable' if operation == 'undo'
                else 'isRedoAvailable'
            )
            available = getattr(widget, method_name, None)
            if callable(available):
                return bool(available()) and not read_only
            document = getattr(widget, 'document', None)
            if callable(document):
                available = getattr(document(), method_name, None)
                if callable(available):
                    return bool(available()) and not read_only
            return False

        if operation == 'copy':
            return has_selection and callable(getattr(widget, 'copy', None))
        if operation == 'cut':
            return (
                has_selection and not read_only
                and callable(getattr(widget, 'cut', None))
            )
        if operation == 'delete':
            if read_only:
                return False
            if has_selection:
                return True
            text = getattr(widget, 'text', None)
            cursor_position = getattr(widget, 'cursorPosition', None)
            if callable(text) and callable(cursor_position):
                return cursor_position() < len(text())
            return bool(cursor is not None and not cursor.atEnd())
        if operation == 'paste':
            return (
                not read_only
                and callable(getattr(widget, 'paste', None))
                and QApplication.clipboard().mimeData().hasText()
            )
        if operation == 'selectAll':
            if not callable(getattr(widget, 'selectAll', None)):
                return False
            text = getattr(widget, 'text', None)
            if callable(text):
                return bool(text())
            plain_text = getattr(widget, 'toPlainText', None)
            return bool(plain_text()) if callable(plain_text) else True
        return False

    def setCurrentInterface(self, object_name):
        action = self.interfaceActions.get(object_name)
        if action:
            action.setChecked(True)
            return

        self.interfaceActionGroup.setExclusive(False)
        for item in self.interfaceActionGroup.actions():
            item.setChecked(False)
        self.interfaceActionGroup.setExclusive(True)


class GuideMenuBar(QMenuBar):
    """Menu bar used while the setup guide is active."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.setNativeMenuBar(True)

        self.fileMenu = self.addMenu(self.tr('MenuBar.File'))
        self.closeWindowAct = QAction(
            self.tr('MenuBar.CloseWindow'), self)
        self.closeWindowAct.setShortcuts(QKeySequence.Close)
        self.fileMenu.addAction(self.closeWindowAct)
        self.backAct = QAction(self.tr('MenuBar.Back'), self)
        self.backAct.setShortcuts(backShortcuts())
        self.fullScreenAct = QAction(
            self.tr('MenuBar.EnterFullScreen'), self)
        self.fullScreenAct.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.FullScreen))
        self.undoAct = self._createEditAction(
            'MenuBar.Undo', QKeySequence.Undo, 'undo')
        self.redoAct = self._createEditAction(
            'MenuBar.Redo', QKeySequence.Redo, 'redo')
        self.cutAct = self._createEditAction(
            'MenuBar.Cut', QKeySequence.Cut, 'cut')
        self.copyAct = self._createEditAction(
            'MenuBar.Copy', QKeySequence.Copy, 'copy')
        self.pasteAct = self._createEditAction(
            'MenuBar.Paste', QKeySequence.Paste, 'paste')
        self.deleteEditAct = self._createEditAction(
            'MenuBar.Delete', QKeySequence.Delete, 'delete')
        self.selectAllAct = self._createEditAction(
            'MenuBar.SelectAll', QKeySequence.SelectAll, 'selectAll')
        self.editActions = [
            self.undoAct, self.redoAct, self.cutAct, self.copyAct,
            self.pasteAct, self.deleteEditAct, self.selectAllAct,
        ]

        self.helpMenu = self.addMenu(self.tr('MenuBar.Help'))
        self.helpAct = QAction(self.tr('MenuBar.OpenHelp'), self)
        self.helpAct.setShortcuts(QKeySequence.HelpContents)
        self.feedbackAct = QAction(self.tr('MenuBar.Feedback'), self)
        self.aboutQtAct = QAction(
            self.tr('MacApplicationMenu.AboutQt'), self)
        self.aboutQtAct.setMenuRole(QAction.AboutQtRole)
        self.helpMenu.addActions([
            self.helpAct,
            self.feedbackAct,
            self.aboutQtAct,
        ])

    def shortcutActions(self):
        return [
            self.closeWindowAct,
            self.helpAct,
            self.backAct,
            self.fullScreenAct,
            *self.editActions,
        ]

    _createEditAction = MenuBar._createEditAction
    triggerEdit = MenuBar.triggerEdit
    isEditOperationEnabled = MenuBar.isEditOperationEnabled
