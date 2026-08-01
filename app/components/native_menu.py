# coding: utf-8
"""Shared native macOS Edit, View and Window menus."""
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QTranslator
from PyQt5.QtWidgets import QApplication

from ..common.event_logger import (
    exceptionDetail,
    logAction,
    logFailed,
    logInitialized,
)
from ..common.setting import DEBUG
from ..common.translator import translate


class MacApplicationMenuTranslator(QTranslator):
    """Keep Qt-regenerated application-menu labels in the app language."""

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context == 'MAC_APPLICATION_MENU':
            keys = {
                'About %1': 'MacApplicationMenu.About',
                'Preferences...': 'MenuBar.Preferences',
                'Services': 'MacApplicationMenu.Services',
                'Hide %1': 'MacApplicationMenu.Hide',
                'Hide Others': 'MacApplicationMenu.HideOthers',
                'Show All': 'MacApplicationMenu.ShowAll',
                'Quit %1': 'MacApplicationMenu.Quit',
            }
            key = keys.get(source_text)
            if key:
                value = translate(key)
                return value.replace('%s', '%1')
        if context == 'QCocoaMenuItem' and source_text == 'About Qt':
            return translate('MacApplicationMenu.AboutQt')
        # ``None`` maps to a null QString and lets Qt continue searching the
        # remaining translators. Returning ``''`` would be treated as a real,
        # empty translation and causes QString::arg warnings throughout Qt.
        return None


def prepareMacApplicationName(app_name):
    """Set interpreter host metadata before QApplication caches Python.app."""
    if sys.platform != 'darwin' or not DEBUG:
        return
    try:
        from Foundation import NSBundle, NSProcessInfo
        info = NSBundle.mainBundle().infoDictionary()
        info['CFBundleName'] = app_name
        info['CFBundleDisplayName'] = app_name
        NSProcessInfo.processInfo().setProcessName_(app_name)
        _setMacProcessManagerName(app_name)
    except Exception as error:
        # The AppKit menu title is corrected again when native menus install.
        logFailed('Log.Action.ApplicationHost', error, level='warning')


def _setMacProcessManagerName(app_name):
    """Update the Dock's cached process label on macOS (best effort)."""
    from ctypes import (
        CDLL,
        POINTER,
        Structure,
        byref,
        c_char_p,
        c_int32,
        c_uint32,
        c_void_p,
    )

    class ProcessSerialNumber(Structure):
        _fields_ = [('high', c_uint32), ('low', c_uint32)]

    core_graphics = CDLL(
        '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    core_foundation = CDLL(
        '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    core_graphics.CPSGetCurrentProcess.argtypes = [
        POINTER(ProcessSerialNumber)]
    core_graphics.CPSGetCurrentProcess.restype = c_int32
    core_graphics.CPSSetProcessName.argtypes = [
        POINTER(ProcessSerialNumber), c_void_p]
    core_graphics.CPSSetProcessName.restype = c_int32
    core_foundation.CFStringCreateWithCString.argtypes = [
        c_void_p, c_char_p, c_uint32]
    core_foundation.CFStringCreateWithCString.restype = c_void_p
    core_foundation.CFRelease.argtypes = [c_void_p]

    process = ProcessSerialNumber()
    if core_graphics.CPSGetCurrentProcess(byref(process)) != 0:
        return
    name = core_foundation.CFStringCreateWithCString(
        None, app_name.encode('utf-8'), 0x08000100)
    if not name:
        return
    try:
        core_graphics.CPSSetProcessName(byref(process), name)
    finally:
        core_foundation.CFRelease(name)


def setMacDockIcon():
    """Use the project icon for the current interpreter-hosted Dock tile."""
    if sys.platform != 'darwin' or not DEBUG:
        return
    try:
        from AppKit import NSApplication, NSImage
        candidates = (
            Path(__file__).resolve().parents[1]
            / 'resource' / 'images' / 'logo.icns',
            Path(sys.argv[0]).resolve().parent
            / 'app' / 'resource' / 'images' / 'logo.icns',
        )
        for path in candidates:
            if not path.is_file():
                continue
            image = NSImage.alloc().initWithContentsOfFile_(str(path))
            if image is not None:
                NSApplication.sharedApplication().setApplicationIconImage_(
                    image)
                return
    except Exception as error:
        logFailed('Log.Action.ApplicationHost', error, level='warning')


if sys.platform == 'darwin':
    from Foundation import NSObject

    class _NativeMenuTarget(NSObject):

        def performUndo_(self, _sender):
            self.controller.menuBar.triggerEdit('undo')

        def performRedo_(self, _sender):
            self.controller.menuBar.triggerEdit('redo')

        def performCut_(self, _sender):
            self.controller.menuBar.triggerEdit('cut')

        def performCopy_(self, _sender):
            self.controller.menuBar.triggerEdit('copy')

        def performPaste_(self, _sender):
            self.controller.menuBar.triggerEdit('paste')

        def performDelete_(self, _sender):
            self.controller.menuBar.triggerEdit('delete')

        def performSelectAll_(self, _sender):
            self.controller.menuBar.triggerEdit('selectAll')

        def back_(self, _sender):
            self.controller.window.goBack()

        def minimize_(self, _sender):
            self.controller.window.minimizeWindow()

        def zoom_(self, _sender):
            self.controller.window.toggleWindowZoom()

        def bringAllToFront_(self, _sender):
            self.controller.window.bringAllToFront()

        def aboutQt_(self, _sender):
            logAction(
                'Log.Action.MenuBar',
                self.controller.window.tr('MacApplicationMenu.AboutQt'),
            )
            QApplication.aboutQt()

        def menuWillOpen_(self, _menu):
            self.controller.updateEditMenu()
            self.controller.updateViewMenu()

        def validateMenuItem_(self, item):
            operation = self.controller.editOperations.get(
                str(item.action()))
            if operation:
                return self.controller.menuBar.isEditOperationEnabled(
                    operation)
            return True


class MacNativeMenuController:
    """Install AppKit menus alongside the Qt-provided File and Help menus."""

    def __init__(self, window, menu_bar, show_back=False):
        self.window = window
        self.menuBar = menu_bar
        self.showBack = show_back
        self.attempts = 0
        self.target = None
        self.editMenu = None
        self.editMenuItem = None
        self.editItems = {}
        self.editOperations = {}
        self.viewMenu = None
        self.viewMenuItem = None
        self.windowMenu = None
        self.windowMenuItem = None
        self.backItem = None
        self.fullScreenItem = None
        self._activationConnected = False

    def install(self):
        if sys.platform != 'darwin':
            return
        self.attempts += 1
        try:
            from AppKit import (NSApplication, NSMenu, NSMenuItem,
                                NSEventModifierFlagCommand,
                                NSEventModifierFlagFunction,
                                NSEventModifierFlagShift, NSImage)

            application = NSApplication.sharedApplication()
            main_menu = application.mainMenu()
            if main_menu is None:
                return self._retry('main menu')

            if not self._activationConnected:
                QApplication.instance().applicationStateChanged.connect(
                    self.onApplicationStateChanged)
                self._activationConnected = True

            self.target = _NativeMenuTarget.alloc().init()
            self.target.controller = self
            self.editMenu = NSMenu.alloc().initWithTitle_(
                self.window.tr('MenuBar.Edit'))
            self.editMenu.setAutoenablesItems_(False)
            self.editMenu.setDelegate_(self.target)

            def add_edit(operation, text_key, selector, key='', modifiers=None):
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    self.window.tr(text_key), selector, key)
                item.setTarget_(self.target)
                if key:
                    item.setKeyEquivalentModifierMask_(
                        modifiers if modifiers is not None
                        else NSEventModifierFlagCommand)
                self.editMenu.addItem_(item)
                self.editItems[operation] = item
                self.editOperations[selector] = operation
                return item

            add_edit('undo', 'MenuBar.Undo', 'performUndo:', 'z')
            add_edit(
                'redo', 'MenuBar.Redo', 'performRedo:', 'z',
                NSEventModifierFlagCommand | NSEventModifierFlagShift)
            self.editMenu.addItem_(NSMenuItem.separatorItem())
            add_edit('cut', 'MenuBar.Cut', 'performCut:', 'x')
            add_edit('copy', 'MenuBar.Copy', 'performCopy:', 'c')
            add_edit('paste', 'MenuBar.Paste', 'performPaste:', 'v')
            add_edit('delete', 'MenuBar.Delete', 'performDelete:')
            self.editMenu.addItem_(NSMenuItem.separatorItem())
            add_edit(
                'selectAll', 'MenuBar.SelectAll', 'performSelectAll:', 'a')
            self.updateEditMenu()

            self.viewMenu = NSMenu.alloc().initWithTitle_(
                self.window.tr('MenuBar.View'))
            self.viewMenu.setAutoenablesItems_(False)
            self.viewMenu.setDelegate_(self.target)
            if self.showBack:
                self.backItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    self.window.tr('MenuBar.Back'), 'back:', '[')
                self.backItem.setTarget_(self.target)
                self.backItem.setKeyEquivalentModifierMask_(
                    NSEventModifierFlagCommand)
                image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    'chevron.backward', self.window.tr('MenuBar.Back'))
                if image is not None:
                    self.backItem.setImage_(image)
                self.viewMenu.addItem_(self.backItem)
                self.viewMenu.addItem_(NSMenuItem.separatorItem())

            # QKeySequence.FullScreen still resolves to Control-Command-F in
            # Qt 5, while current AppKit menus use Function/Globe-F.  Build
            # this standard item with Cocoa's own modifier flag so the menu
            # displays the platform-native Globe symbol and handles the real
            # system shortcut.
            self.fullScreenItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                self.window.tr('MenuBar.EnterFullScreen'),
                'toggleFullScreen:', 'f')
            self.fullScreenItem.setTarget_(None)
            self.fullScreenItem.setKeyEquivalentModifierMask_(
                NSEventModifierFlagFunction)
            full_screen_image = (
                NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    'arrow.up.left.and.arrow.down.right',
                    self.window.tr('MenuBar.EnterFullScreen'),
                )
            )
            if full_screen_image is not None:
                self.fullScreenItem.setImage_(full_screen_image)
            self.viewMenu.addItem_(self.fullScreenItem)
            self.updateViewMenu()

            self.windowMenu = NSMenu.alloc().initWithTitle_(
                self.window.tr('MenuBar.Window'))
            self.windowMenu.setAutoenablesItems_(False)

            def add_window(text_key, selector, key=''):
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    self.window.tr(text_key), selector, key)
                item.setTarget_(self.target)
                if key:
                    item.setKeyEquivalentModifierMask_(
                        NSEventModifierFlagCommand)
                item.setEnabled_(True)
                self.windowMenu.addItem_(item)

            add_window('MenuBar.Minimize', 'minimize:', 'm')
            add_window('MenuBar.Zoom', 'zoom:')
            self.windowMenu.addItem_(NSMenuItem.separatorItem())
            add_window('MenuBar.BringAllToFront', 'bringAllToFront:')

            self.editMenuItem = self._submenuItem(
                NSMenuItem, 'MenuBar.Edit', self.editMenu)
            self.viewMenuItem = self._submenuItem(
                NSMenuItem, 'MenuBar.View', self.viewMenu)
            self.windowMenuItem = self._submenuItem(
                NSMenuItem, 'MenuBar.Window', self.windowMenu)
            help_title = self.menuBar.helpMenu.title().replace('&', '')
            index = main_menu.numberOfItems()
            for i, item in enumerate(main_menu.itemArray()):
                if item.title() == help_title:
                    index = i
                    break
            main_menu.insertItem_atIndex_(self.editMenuItem, index)
            main_menu.insertItem_atIndex_(self.viewMenuItem, index + 1)
            main_menu.insertItem_atIndex_(self.windowMenuItem, index + 2)
            application.setWindowsMenu_(self.windowMenu)
            native_window = self.nativeWindow()
            if native_window is not None:
                application.addWindowsItem_title_filename_(
                    native_window, self.window.windowTitle(), False)
            # Qt moves AboutRole/PreferencesRole/QuitRole actions into the
            # application menu asynchronously.  Rename them only afterwards,
            # otherwise Qt may create duplicate About/Quit items.
            QTimer.singleShot(
                100,
                lambda app=application, menu=main_menu:
                self._configureApplicationMenu(app, menu),
            )
            logInitialized(
                'Log.Action.NativeWindowMenu',
                self.window.tr('MenuBar.Window'))
        except Exception as error:
            self._retry(error)

    def onApplicationStateChanged(self, state):
        if state == Qt.ApplicationActive:
            self.restoreApplicationMenu()
            for delay in (0, 75, 250):
                QTimer.singleShot(delay, self.restoreApplicationMenu)

    def restoreApplicationMenu(self):
        if sys.platform != 'darwin':
            return
        try:
            from AppKit import NSApplication
            application = NSApplication.sharedApplication()
            prepareMacApplicationName(
                QApplication.applicationDisplayName())
            setMacDockIcon()
            main_menu = application.mainMenu()
            if main_menu is not None:
                self._configureApplicationMenu(application, main_menu)
        except Exception as error:
            logFailed('Log.Action.MenuBar', error)

    def _submenuItem(self, menu_item_class, title_key, submenu):
        item = menu_item_class.alloc().initWithTitle_action_keyEquivalent_(
            self.window.tr(title_key), None, '')
        item.setSubmenu_(submenu)
        return item

    def _configureApplicationMenu(self, application, main_menu):
        """Use the real app name and the selected application language."""
        if main_menu.numberOfItems() == 0:
            return

        app_name = (
            QApplication.applicationDisplayName()
            or QApplication.applicationName()
            or 'GitHub NetDisk'
        )
        app_item = main_menu.itemAtIndex_(0)
        app_menu = app_item.submenu()
        if app_menu is None:
            return

        app_item.setTitle_(app_name)
        app_menu.setTitle_(app_name)

        items = list(app_menu.itemArray())
        about_qt_title = self.window.tr('MacApplicationMenu.AboutQt')
        about_qt_items = [item for item in items if 'Qt' in item.title()]
        about_qt_item = about_qt_items[0] if about_qt_items else None
        if about_qt_item is None:
            from AppKit import NSMenuItem
            about_qt_item = (
                NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    about_qt_title, 'aboutQt:', ''))
            about_qt_item.setTarget_(self.target)
            app_menu.insertItem_atIndex_(about_qt_item, 1)
        else:
            for duplicate in about_qt_items[1:]:
                app_menu.removeItem_(duplicate)

        labels = {
            'orderFrontStandardAboutPanel:': self.window.tr(
                'MacApplicationMenu.About', (app_name,)),
            'submenuAction:': self.window.tr(
                'MacApplicationMenu.Services'),
            'hide:': self.window.tr(
                'MacApplicationMenu.Hide', (app_name,)),
            'hideOtherApplications:': self.window.tr(
                'MacApplicationMenu.HideOthers'),
            'unhideAllApplications:': self.window.tr(
                'MacApplicationMenu.ShowAll'),
            'terminate:': self.window.tr(
                'MacApplicationMenu.Quit', (app_name,)),
        }
        items = list(app_menu.itemArray())
        for index, item in enumerate(items):
            selector = str(item.action())
            key = item.keyEquivalent()
            if index == 0:
                item.setTitle_(self.window.tr(
                    'MacApplicationMenu.About', (app_name,)))
            elif selector in labels:
                item.setTitle_(labels[selector])
            elif key == ',':
                item.setTitle_(self.window.tr('MenuBar.Preferences'))
            elif key == 'q':
                item.setTitle_(self.window.tr(
                    'MacApplicationMenu.Quit', (app_name,)))

        about_qt_item.setTitle_(about_qt_title)

    def _retry(self, detail):
        if self.attempts < 5:
            QTimer.singleShot(200, self.install)
        else:
            logFailed('Log.Action.NativeWindowMenu', detail)

    def updateEditMenu(self):
        """Synchronize native Edit items with the focused Qt text widget."""
        for operation, item in self.editItems.items():
            item.setEnabled_(
                self.menuBar.isEditOperationEnabled(operation))

    def updateViewMenu(self):
        if self.backItem is not None:
            can_go_back = getattr(self.window, 'canGoBack', None)
            if callable(can_go_back):
                enabled = bool(can_go_back())
            else:
                button = self.window.navigationInterface.panel.returnButton
                enabled = button.isEnabled()
            self.backItem.setEnabled_(enabled)
        if self.fullScreenItem is not None:
            is_full_screen = self.window.isFullScreen()
            title = self.window.tr(
                'MenuBar.ExitFullScreen'
                if is_full_screen
                else 'MenuBar.EnterFullScreen')
            self.fullScreenItem.setTitle_(title)
            try:
                from AppKit import NSImage
                image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    'arrow.down.right.and.arrow.up.left'
                    if is_full_screen
                    else 'arrow.up.left.and.arrow.down.right',
                    title,
                )
                if image is not None:
                    self.fullScreenItem.setImage_(image)
            except Exception as error:
                logFailed('Log.Action.MenuBar', error, level='debug')
            native_window = self.nativeWindow()
            if native_window is not None:
                native_window.validateMenuItem_(self.fullScreenItem)

    @staticmethod
    def nativeWindow():
        if sys.platform != 'darwin':
            return None
        from AppKit import NSApplication
        application = NSApplication.sharedApplication()
        return application.keyWindow() or application.mainWindow()

