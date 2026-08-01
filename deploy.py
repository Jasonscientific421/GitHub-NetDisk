# coding: utf-8
"""Build GitHub NetDisk and add target-system localized metadata."""
import ctypes
import json
import os
import plistlib
import struct
import subprocess
import sys
import shutil
from pathlib import Path

from app.common.setting import APP_NAME, VERSION


PROJECT_ROOT = Path(__file__).resolve().parent
LANGUAGE_FOLDER = PROJECT_ROOT / 'app' / 'resource' / 'lang'
DIST_FOLDER = PROJECT_ROOT / 'dist'
BUILD_BASENAME = 'GitHub-NetDisk'

MAC_LOCALIZATIONS = {
    'en': 'en_us',
    'zh-Hans': 'zh_cn',
    'zh-Hant': 'zh_hk',
}

# Windows language IDs. The same translation is used for regions sharing a
# writing system, so the target OS can select the closest VERSIONINFO resource.
WINDOWS_LOCALIZATIONS = {
    0x0409: 'en_us',       # English (United States)
    0x0804: 'zh_cn',       # Chinese (Simplified, China)
    0x1004: 'zh_cn',       # Chinese (Simplified, Singapore)
    0x0404: 'zh_hk',       # Chinese (Traditional, Taiwan)
    0x0C04: 'zh_hk',       # Chinese (Traditional, Hong Kong)
    0x1404: 'zh_hk',       # Chinese (Traditional, Macao)
}


def getLocalizedAppNames():
    """Return application names from the translations embedded in the app."""
    names = {}
    for locale_name in {'en_us', 'zh_cn', 'zh_hk'}:
        language_file = LANGUAGE_FOLDER / f'{locale_name}.json'
        try:
            with language_file.open(encoding='utf-8') as file:
                names[locale_name] = json.load(file).get('App.Name') or APP_NAME
        except (OSError, ValueError, TypeError):
            names[locale_name] = APP_NAME
    return names


def is_arm64_build():
    """Detect ARM64 build by env or platform."""
    return os.getenv("GITHUB_NETDISK_WINDOWS_ARM64", "") == "1" or platform.machine().lower() in ("arm64", "aarch64")


def createBuildCommand(platform_name=None):
    """Create the compiler command; localization is added after compilation."""
    platform_name = platform_name or sys.platform

    if platform_name == 'win32':
        # Base command without pyqt5 plugin args
        command = [
            sys.executable,
            '-m',
            'nuitka',
            '--standalone',
            '--windows-disable-console',
            '--include-package=keyring',
            '--assume-yes-for-downloads',
            '--show-memory',
            '--show-progress',
            '--windows-icon-from-ico=app/resource/images/logo.ico',
            '--windows-company-name=XiaoshuDeXiaowo',
            '--windows-product-name=GitHub NetDisk',
            f'--windows-file-version={VERSION}',
            f'--windows-product-version={VERSION}',
            '--windows-file-description=GitHub NetDisk',
            '--output-dir=dist',
            'GitHub-NetDisk.py',
        ]
        # The normal PyPI build uses CPython/MSVC. Native Windows ARM64 uses
        # MSYS2's CLANGARM64 Python, Qt and PyQt5, whose ABI must be compiled
        # with the matching Clang/UCRT toolchain already present on PATH.
        if not os.environ.get('GITHUB_NETDISK_WINDOWS_ARM64'):
            # Insert MSVC option for non-ARM builds
            command.insert(8, '--msvc=latest')
            # For non-ARM (amd64) keep using the pyqt5 plugin and sensible qt plugins
            # (the plugin is known to fail on ARM64 currently)
            command.insert(9, '--plugin-enable=pyqt5')
            command.insert(10, '--include-qt-plugins=sensible')
        return command

    if platform_name == 'darwin':
        return [
            sys.executable,
            '-m',
            'nuitka',
            '--standalone',
            '--plugin-enable=pyqt5',
            '--include-qt-plugins=sensible',
            '--include-package=keyring',
            '--show-memory',
            '--show-progress',
            '--macos-create-app-bundle',
            '--assume-yes-for-downloads',
            '--macos-disable-console',
            f'--macos-app-version={VERSION}',
            f'--macos-app-name={BUILD_BASENAME}',
            '--macos-app-icon=app/resource/images/logo.icns',
            '--copyright=XiaoshuDeXiaowo',
            '--output-dir=dist',
            'GitHub-NetDisk.py',
        ]

    return [
        sys.executable,
        '-m',
        'PyInstaller',
        '--collect-all',
        'keyring',
        '-w',
        'GitHub-NetDisk.py',
    ]


def _writeMacStrings(path, app_name):
    escaped_name = app_name.replace('\\', '\\\\').replace('"', '\\"')
    content = (
        f'"CFBundleDisplayName" = "{escaped_name}";\n'
        f'"CFBundleName" = "{escaped_name}";\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')


def localizeMacBundle(bundle_path):
    """Add Finder display names selected by the target user's language."""
    bundle_path = Path(bundle_path)
    contents_folder = bundle_path / 'Contents'
    resources_folder = contents_folder / 'Resources'
    info_file = contents_folder / 'Info.plist'
    names = getLocalizedAppNames()

    for apple_locale, app_locale in MAC_LOCALIZATIONS.items():
        _writeMacStrings(
            resources_folder / f'{apple_locale}.lproj' / 'InfoPlist.strings',
            names[app_locale],
        )

    with info_file.open('rb') as file:
        info = plistlib.load(file)
    info['CFBundleDevelopmentRegion'] = 'en'
    info['CFBundleLocalizations'] = list(MAC_LOCALIZATIONS)
    info['LSHasLocalizedDisplayName'] = True
    info['CFBundleURLTypes'] = [{
        'CFBundleURLName': 'GitHub-NetDisk URL',
        'CFBundleURLSchemes': ['github-netdisk'],
    }]
    with info_file.open('wb') as file:
        plistlib.dump(info, file, sort_keys=False)


def _align(data, boundary=4):
    data.extend(b'\0' * (-len(data) % boundary))


def _utf16(value):
    return (value + '\0').encode('utf-16le')


def _versionBlock(key, value=b'', value_length=0, value_type=1,
                  children=()):
    data = bytearray(b'\0' * 6)
    data.extend(_utf16(key))
    _align(data)
    data.extend(value)
    if children:
        _align(data)
        for child in children:
            data.extend(child)
            _align(data)
    struct.pack_into(
        '<HHH', data, 0, len(data), value_length, value_type)
    return bytes(data)


def _versionNumbers(version):
    numbers = []
    for part in version.split('.'):
        try:
            numbers.append(int(part))
        except ValueError:
            numbers.append(0)
    return (numbers + [0, 0, 0, 0])[:4]


def createWindowsVersionInfo(language_id, app_name):
    """Create one language-specific RT_VERSION resource."""
    codepage = 1200
    version_numbers = _versionNumbers(VERSION)
    version_ms = (version_numbers[0] << 16) | version_numbers[1]
    version_ls = (version_numbers[2] << 16) | version_numbers[3]
    version_text = '.'.join(str(i) for i in version_numbers)

    values = {
        'CompanyName': 'XiaoshuDeXiaowo',
        'FileDescription': app_name,
        'FileVersion': version_text,
        'InternalName': BUILD_BASENAME,
        'LegalCopyright': 'Copyright XiaoshuDeXiaowo',
        'OriginalFilename': f'{BUILD_BASENAME}.exe',
        'ProductName': app_name,
        'ProductVersion': version_text,
    }
    string_blocks = []
    for key, value in values.items():
        encoded_value = _utf16(value)
        string_blocks.append(_versionBlock(
            key,
            encoded_value,
            len(value) + 1,
            1,
        ))

    string_table = _versionBlock(
        f'{language_id:04X}{codepage:04X}',
        children=string_blocks,
    )
    string_file_info = _versionBlock(
        'StringFileInfo', children=(string_table,))
    translation = struct.pack('<HH', language_id, codepage)
    translation_block = _versionBlock(
        'Translation', translation, len(translation), 0)
    var_file_info = _versionBlock(
        'VarFileInfo', children=(translation_block,))

    fixed_file_info = struct.pack(
        '<13I',
        0xFEEF04BD,       # dwSignature
        0x00010000,       # dwStrucVersion
        version_ms,
        version_ls,
        version_ms,
        version_ls,
        0x0000003F,       # dwFileFlagsMask
        0,
        0x00040004,       # VOS_NT_WINDOWS32
        0x00000001,       # VFT_APP
        0,
        0,
        0,
    )
    return _versionBlock(
        'VS_VERSION_INFO',
        fixed_file_info,
        len(fixed_file_info),
        0,
        (string_file_info, var_file_info),
    )


def localizeWindowsExecutable(executable_path):
    """Add multiple VERSIONINFO resources selected by target Windows."""
    if sys.platform != 'win32':
        raise RuntimeError('Windows resources can only be updated on Windows')

    from ctypes import wintypes

    executable_path = str(Path(executable_path).resolve())
    kernel32 = ctypes.windll.kernel32
    begin_update = kernel32.BeginUpdateResourceW
    begin_update.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    begin_update.restype = wintypes.HANDLE
    update_resource = kernel32.UpdateResourceW
    update_resource.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.WORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    update_resource.restype = wintypes.BOOL
    end_update = kernel32.EndUpdateResourceW
    end_update.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    end_update.restype = wintypes.BOOL

    handle = begin_update(executable_path, False)
    if not handle:
        raise ctypes.WinError()

    committed = False
    buffers = []
    try:
        # Nuitka may create a language-neutral fallback. Removing it prevents
        # it from taking precedence over a target-language resource.
        update_resource(handle, ctypes.c_void_p(16), ctypes.c_void_p(1),
                        0, None, 0)

        names = getLocalizedAppNames()
        for language_id, app_locale in WINDOWS_LOCALIZATIONS.items():
            data = createWindowsVersionInfo(
                language_id, names[app_locale])
            buffer = ctypes.create_string_buffer(data)
            buffers.append(buffer)
            if not update_resource(
                    handle,
                    ctypes.c_void_p(16),
                    ctypes.c_void_p(1),
                    language_id,
                    buffer,
                    len(data)):
                raise ctypes.WinError()

        if not end_update(handle, False):
            raise ctypes.WinError()
        committed = True
    finally:
        if not committed:
            end_update(handle, True)


def _findArtifact(pattern):
    artifacts = list(DIST_FOLDER.rglob(pattern))
    if not artifacts:
        raise FileNotFoundError(f'Build artifact not found: {pattern}')
    return max(artifacts, key=lambda path: path.stat().st_mtime)


def copy_qt_plugins_to_dist(dist_root=DIST_FOLDER):
    """
    Copy Qt plugin subfolders from the PyQt5 installation into the Nuitka dist
    so runtime finds platform/imageformat/plugins when the plugin cannot be used.
    """
    try:
        import PyQt5
    except Exception as e:
        print("copy_qt_plugins_to_dist: 无法导入 PyQt5，跳过复制 Qt 插件：", e)
        return

    pyqt_root = Path(PyQt5.__file__).parent
    candidates = [
        pyqt_root / "Qt" / "plugins",
        pyqt_root / "qt_plugins",
        pyqt_root / "qt" / "plugins",
    ]
    src_plugins = None
    for c in candidates:
        if c.is_dir():
            src_plugins = c
            break

    if not src_plugins:
        print("copy_qt_plugins_to_dist: 未找到 PyQt5 的 plugins 目录，已检查候选:", candidates)
        return

    wanted = ["platforms", "imageformats", "iconengines", "printsupport", "styles"]
    # Nuitka creates dist/<BUILD_BASENAME>.dist
    target_base = Path(dist_root) / f"{BUILD_BASENAME}.dist" / "PyQt5" / "qt-plugins"
    target_base.mkdir(parents=True, exist_ok=True)

    for sub in wanted:
        src = src_plugins / sub
        if src.is_dir():
            dst = target_base / sub
            print(f"复制 Qt 插件: {src} -> {dst}")
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            print(f"copy_qt_plugins_to_dist: 插件子目录不存在: {src} (跳过)")


def addLocalizedMetadata(platform=None):
    """Add metadata that changes with the language of the target system."""
    platform = platform or sys.platform
    if platform == 'win32':
        localizeWindowsExecutable(_findArtifact(f'{BUILD_BASENAME}.exe'))
    elif platform == 'darwin':
        bundle_path = _findArtifact(f'{BUILD_BASENAME}.app')
        localizeMacBundle(bundle_path)
        # Updating bundle resources invalidates Nuitka's ad-hoc signature.
        subprocess.run(
            ['codesign', '--force', '--deep', '--sign', '-', str(bundle_path)],
            check=True,
        )


def main():
    command = createBuildCommand()
    print("Running build command:", " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)

    # If this is an ARM64 native build, the Nuitka pyqt5 plugin may have been
    # skipped earlier; ensure Qt plugins are present in the dist so runtime
    # can load them.
    if sys.platform == 'win32' and is_arm64_build():
        try:
            copy_qt_plugins_to_dist(DIST_FOLDER)
        except Exception as e:
            # Log but don't fail the build here; allow the build artifact to be
            # inspected even if plugin copying fails.
            print("copy_qt_plugins_to_dist 出错:", e)

    addLocalizedMetadata()


if __name__ == '__main__':
    main()
