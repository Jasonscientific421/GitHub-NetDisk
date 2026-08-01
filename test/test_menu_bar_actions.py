from app.components import menu_bar


def test_edit_actions_target_focused_qt_widget(monkeypatch):
    operations = []

    class FocusWidget:
        def copy(self):
            operations.append('copy')

    monkeypatch.setattr(
        menu_bar.QApplication, 'focusWidget', lambda: FocusWidget())

    assert menu_bar.MenuBar.triggerEdit(object(), 'copy') is True
    assert operations == ['copy']


def test_platform_specific_settings_and_back_shortcuts():
    assert [item.toString() for item in
            menu_bar.settingsShortcuts('win32')] == ['Ctrl+,']
    assert [item.toString() for item in
            menu_bar.backShortcuts('darwin')] == ['Ctrl+[']
    assert [item.toString() for item in
            menu_bar.backShortcuts('win32')] == ['Alt+Left']
    assert [item.toString() for item in
            menu_bar.backShortcuts('linux')] == ['Alt+Left']


def test_edit_action_enabled_state_tracks_focused_widget(monkeypatch):
    class MimeData:
        def hasText(self):
            return True

    class Clipboard:
        def mimeData(self):
            return MimeData()

    class FocusWidget:
        def __init__(self, read_only=False):
            self.read_only = read_only

        def isEnabled(self):
            return True

        def isReadOnly(self):
            return self.read_only

        def hasSelectedText(self):
            return True

        def isUndoAvailable(self):
            return True

        def isRedoAvailable(self):
            return False

        def cut(self):
            pass

        def copy(self):
            pass

        def paste(self):
            pass

        def selectAll(self):
            pass

        def text(self):
            return 'selected text'

    widget = FocusWidget()
    monkeypatch.setattr(menu_bar.QApplication, 'focusWidget', lambda: widget)
    monkeypatch.setattr(menu_bar.QApplication, 'clipboard', lambda: Clipboard())

    enabled = lambda operation: menu_bar.MenuBar.isEditOperationEnabled(
        object(), operation)
    assert enabled('undo')
    assert not enabled('redo')
    assert enabled('cut')
    assert enabled('copy')
    assert enabled('paste')
    assert enabled('delete')
    assert enabled('selectAll')

    widget.read_only = True
    assert not enabled('undo')
    assert not enabled('cut')
    assert enabled('copy')
    assert not enabled('paste')
    assert not enabled('delete')
    assert enabled('selectAll')


def test_guide_menu_bar_exposes_native_edit_state_interface(monkeypatch):
    """The macOS native menu controller calls this method on both menu bars."""
    monkeypatch.setattr(menu_bar.QApplication, 'focusWidget', lambda: None)

    assert menu_bar.GuideMenuBar.isEditOperationEnabled(
        object(), 'copy') is False
