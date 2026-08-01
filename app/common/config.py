# coding:utf-8
import sys
import json
from pathlib import Path

from getpass import getuser
from PyQt5.QtCore import QLocale, QStandardPaths
from qframelesswindow.utils import getSystemAccentColor
from qfluentwidgets import (qconfig, QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, Theme, FolderValidator, ConfigSerializer, ColorConfigItem, setThemeColor,
                            themeColor, ConfigValidator)

from .setting import CONFIG_FILE
from .translator import getTranslateQLocalesList
from . import resource


def _migrateCacheKeys():
    """Split the legacy ambiguous username fields and remove userName."""
    if not CONFIG_FILE.exists():
        return
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        caches = data.get('Caches')
        if not isinstance(caches, dict):
            return
        changed = False
        if 'userName' in caches:
            login = str(caches.get('username') or '')
            display_name = str(caches.pop('userName') or login)
            caches['login'] = login
            caches['username'] = display_name
            changed = True
        elif 'login' not in caches and 'username' in caches:
            caches['login'] = str(caches.get('username') or '')
            changed = True
        if changed:
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=4),
                encoding='utf-8',
            )
    except (OSError, TypeError, ValueError):
        pass

class LanguageSerializer(ConfigSerializer):
    """ Language serializer """

    def serialize(self, language):
        return language.name() if language != QLocale() else "Auto"

    def deserialize(self, value: str):
        return QLocale(value) if value != "Auto" else QLocale()


class SafeFolderValidator(FolderValidator):
    """Folder validator that falls back when a saved path is unavailable."""

    def __init__(self, fallback):
        super().__init__()
        self.fallback = fallback

    def correct(self, value):
        candidates = [
            value,
            self.fallback,
            QStandardPaths.writableLocation(QStandardPaths.DownloadLocation),
            str(Path.home()),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                path = Path(candidate).expanduser()
                path.mkdir(exist_ok=True, parents=True)
                if path.is_dir():
                    return str(path.absolute()).replace("\\", "/")
            except (OSError, RuntimeError, ValueError):
                continue
        return str(Path.cwd().absolute()).replace("\\", "/")


def isWin11():
    return sys.platform == 'win32' and sys.getwindowsversion().build >= 22000


class Config(QConfig):
    """ Config of application """
    # first time to use
    firstUse = ConfigItem("MainWindow", "FirstUse", True, BoolValidator())

    # main window
    micaEnabled = ConfigItem("MainWindow", "MicaEnabled", isWin11(), BoolValidator())
    disableTrayIcon = ConfigItem(
        "MainWindow", "DisableTrayIcon", False, BoolValidator())
    exitOnClose = ConfigItem(
        "MainWindow", "ExitOnClose", False, BoolValidator())
    dpiScale = OptionsConfigItem(
        "MainWindow", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)

    language = OptionsConfigItem("MainWindow", "Language",
                                 QLocale(), OptionsValidator(getTranslateQLocalesList(':/app/lang')+[QLocale()]), LanguageSerializer(), restart=True)

    # software update
    checkUpdateAtStartUp = ConfigItem("Update", "CheckUpdateAtStartUp", True, BoolValidator())

    # download
    saveFolder = ConfigItem(
        "Download",
        "SaveFolder",
        QStandardPaths.writableLocation(QStandardPaths.DownloadLocation),
        SafeFolderValidator(QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)),
    )
    aria2Enabled = ConfigItem(
        "Download", "Aria2Enabled", True, BoolValidator())
    aria2Path = ConfigItem("Download", "Aria2Path", "")

    # github
    githubMirrorEnabled = ConfigItem('GitHub', 'GitHubMirrorEnabled', True, BoolValidator())
##    apiMirrorEnabled = ConfigItem('GitHub', 'ApiMirrorEnabled', False, BoolValidator())
    loginType = OptionsConfigItem(
        'GitHub', 'LoginType', 'Anonymous',
        OptionsValidator(['GitHubApp', 'Token', 'Anonymous']),
    )
    authExpiresAt = ConfigItem('GitHub', 'AuthExpiresAt', 0)

    # NetdiskService
    quickAccessList = ConfigItem('NetdiskService', 'QuickAccessList', [])
    dirAhead = ConfigItem('NetdiskService', 'DirAhead', True, BoolValidator())

    # splitter
    treeWidth = ConfigItem('Splitter', 'treeWidth', 600)
    fileCardWidth = ConfigItem('Splitter', 'fileCardWidth', 400)

    # caches
    userLoginCache = ConfigItem('Caches', 'login', '')
    usernameCache = ConfigItem('Caches', 'username', getuser())
    repoCache = ConfigItem('Caches', 'repo', '')

    # Most Recent Used List
    # mruList = ConfigItem('Caches', 'MRUList', [])

_migrateCacheKeys()
cfg = Config()
cfg.themeMode.value = Theme.AUTO
qconfig.load(str(CONFIG_FILE.absolute()), cfg)
if cfg.get(cfg.disableTrayIcon) and not cfg.get(cfg.exitOnClose):
    # With no tray icon, closing the only window must not leave an
    # inaccessible background process.
    cfg.set(cfg.exitOnClose, True)
