# coding: utf-8
import ctypes
import os
import sys
import re
from collections import OrderedDict
from ctypes import wintypes
from functools import _CacheInfo, wraps, lru_cache
from pathlib import Path
from typing import Union

from PyQt5.QtCore import QFile, QUrl, QFileInfo, QDir, QProcess, QMimeDatabase
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import QFileIconProvider, QApplication, QStyle
from loguru import logger

from .translator import translate


def lru_cache_noexcept(maxsize=128, typed=False):
    """LRU cache that does **not** cache raised exceptions.

    Unlike :func:`functools.lru_cache`, when the wrapped function raises an
    exception the exception is propagated immediately and the failing call is
    *not* stored in the cache.  The next call with the same arguments will
    execute the function again instead of re-raising a cached exception.

    This is useful for functions like ``getRepo`` where a transient error
    (network timeout, rate-limit) should not prevent future retries.

    Accepts the same parameters as :func:`functools.lru_cache`.
    """
    if callable(maxsize):
        # Called without parentheses, e.g. @lru_cache_noexcept
        func = maxsize
        return _build_lru_cache_noexcept(func, 128, typed)

    def decorator(func):
        return _build_lru_cache_noexcept(func, maxsize, typed)
    return decorator


def _build_lru_cache_noexcept(func, maxsize, typed):
    """Build an LRU cache wrapper that only stores successful results."""
    maxsize = float('inf') if maxsize is None else maxsize
    cache = OrderedDict()
    hits = [0]
    misses = [0]

    if typed:
        def _make_key(args, kwargs):
            return (args, tuple((k, v, type(v))
                    for k, v in sorted(kwargs.items())))
    else:
        def _make_key(args, kwargs):
            return (args, tuple(sorted(kwargs.items()))) if kwargs else args

    @wraps(func)
    def wrapper(*args, **kwargs):
        key = _make_key(args, kwargs)
        if key in cache:
            hits[0] += 1
            cache.move_to_end(key)
            return cache[key]

        misses[0] += 1
        # Let exceptions propagate — they are intentionally NOT cached.
        result = func(*args, **kwargs)

        if len(cache) >= maxsize:
            cache.popitem(last=False)
        cache[key] = result
        return result

    def cache_clear():
        cache.clear()
        hits[0] = 0
        misses[0] = 0

    def cache_info():
        return _CacheInfo(hits[0], misses[0], maxsize, len(cache))

    wrapper.cache_clear = cache_clear
    wrapper.cache_info = cache_info
    return wrapper


def unwrapFutureError(error):
    """Return the original exception hidden by pyqt5-concurrent wrappers."""
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        original = getattr(current, 'original', None)
        if original is None or original is current:
            break
        current = original
    return current


@lru_cache()
def adjustFileName(name: str) -> str:
    """ adjust file name

    Returns
    -------
    name: str
        file name after adjusting
    """
    name = re.sub(r'[\\/:*?"<>|\r\n\s]+', "_", name.strip()).strip()
    return name.rstrip(".")


def readFile(filePath: str):
    """ read file content """
    file = QFile(filePath)
    file.open(QFile.OpenModeFlag.ReadOnly)
    data = str(file.readAll(), encoding='utf-8')
    file.close()
    return data


def getUniqueFilePath(filePath: Union[str, Path], reservedPaths=()) -> str:
    """Return an unused file path, adding `` (n)`` before its suffix."""
    filePath = os.path.abspath(os.fspath(filePath))
    reserved = {
        os.path.normcase(os.path.abspath(os.fspath(path)))
        for path in reservedPaths
    }
    if not os.path.exists(filePath) and os.path.normcase(filePath) not in reserved:
        return filePath

    folder, fileName = os.path.split(filePath)
    stem, suffix = os.path.splitext(fileName)
    index = 1
    while True:
        candidate = os.path.join(folder, f'{stem} ({index}){suffix}')
        if (
            not os.path.exists(candidate)
            and os.path.normcase(candidate) not in reserved
        ):
            return candidate
        index += 1


def openUrl(url: str):
    logger.info(translate('Log.Utils.OpenUrl.Started', url))
    if not url.startswith("http"):
        if not os.path.exists(url):
            logger.warning(translate('Log.Utils.OpenUrl.Failed.NotFound', url))
            return False

        QDesktopServices.openUrl(QUrl.fromLocalFile(url))
    else:
        QDesktopServices.openUrl(QUrl(url))

    logger.info(translate('Log.Utils.OpenUrl.Success', url))
    return True


def showInFolder(path: Union[str, Path]):
    """ show file in file explorer """
    logger.info(translate('Log.Utils.ShowInFolder.Started', path))
    if not os.path.exists(path):
        logger.warning(translate('Log.Utils.ShowInFolder.Failed.NotFound', path))
        return False

    if isinstance(path, Path):
        path = str(path.absolute())

    if not path or path.lower().startswith('http'):
        logger.warning(translate('Log.Utils.ShowInFolder.Failed.InvalidPath', path))
        return False

    info = QFileInfo(path)   # type: QFileInfo
    if sys.platform == "win32":
        args = [QDir.toNativeSeparators(path)]
        if not info.isDir():
            args.insert(0, '/select,')

        QProcess.startDetached('explorer', args)
    elif sys.platform == "darwin":
        args = [
            "-e", 'tell application "Finder"', "-e", "activate",
            "-e", f'select POSIX file "{path}"', "-e", "end tell",
            "-e", "return"
        ]
        QProcess.execute("/usr/bin/osascript", args)
    else:
        url = QUrl.fromLocalFile(path if info.isDir() else info.path())
        QDesktopServices.openUrl(url)

    logger.info(translate('Log.Utils.ShowInFolder.Success', path))
    return True


def getFileTypeName(filePath: str) -> str:
    """ Get the localization type name of the file, return 'xxx File' when fetch fails

    Parameters
    ----------
    filePath: str
        The file to get the file type name, which can not exist

    Return
    ------
    typeName: str
        The name of the file type obtained
    """
    if sys.platform != 'win32':
        db = QMimeDatabase()
        # Get MIME type based on file name (file doesn't have to exist)
        mime = db.mimeTypeForFile(filePath, QMimeDatabase.MatchExtension)
        comment = mime.comment()
        if comment:
            return comment
        return f'{filePath.split(".")[-1].lower()} File'
    else:
        filePath = filePath.replace('\\', '/').split('/')[-1]
        if not '.' in filePath:
            ext = '.'
        else:
            ext = '.' + filePath.split('.')[-1]
        AssocQueryStringW = ctypes.windll.shlwapi.AssocQueryStringW
        AssocQueryStringW.argtypes = [
            wintypes.DWORD,  # flags
            wintypes.DWORD,  # str
            wintypes.LPCWSTR,  # pszAssoc
            wintypes.LPCWSTR,  # pszExtra
            wintypes.LPWSTR,  # pszOut
            wintypes.LPDWORD,  # pcchOut
        ]
        AssocQueryStringW.restype = ctypes.HRESULT

        buffer_size = wintypes.DWORD(0)
        hr = AssocQueryStringW(
            4,  # ASSOCF_INIT_DEFAULTTOSTAR
            3,  # ASSOCSTR_FRIENDLYDOCNAME
            ext,
            None,
            None,
            ctypes.byref(buffer_size)
        )
        if hr != 1:  # S_FALSE
            return f'{ext[1:]} File'

        buffer = ctypes.create_unicode_buffer(buffer_size.value)
        hr = AssocQueryStringW(
            4,  # ASSOCF_INIT_DEFAULTTOSTAR
            3,  # ASSOCSTR_FRIENDLYDOCNAME
            ext,
            None,
            buffer,
            ctypes.byref(buffer_size)
        )
        if hr == 0:
            return buffer.value
        return f'{ext[1:].lower()} File'

def getFileTypeIcon(filePath: str) -> QIcon:
    """ Get the icon of the file type

    Parameters
    ----------
    filePath: str
        The file to get the icon, which can not exist

    Return
    ------
    icon: QIcon
        The icon of the file type
    """
    return QFileIconProvider().icon(QFileInfo(filePath))


def getFolderTypeName() -> str:
    """ Get the localized name of the "folder" on the current system. """
    return QMimeDatabase().mimeTypeForName('inode/directory').comment() or 'Folder'


def getFolderTypeIcon() -> QIcon:
    """ Get the icon of the "folder" on the current system. """
    return QFileIconProvider().icon(QFileIconProvider.Folder) or QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
