# coding: utf-8
import os
from types import SimpleNamespace

from app.view.browse_interface import BrowseInterface
from app.components.file_info_card import FileToolBar


def test_save_as_dialog_uses_current_file_name_and_save_folder(monkeypatch):
    toolbar = FileToolBar.__new__(FileToolBar)
    calls = []
    emitted = []
    monkeypatch.setattr(toolbar, 'tr', lambda key, *args: key)
    monkeypatch.setattr(toolbar, 'window', lambda: None)
    monkeypatch.setattr(toolbar, 'currentFileName', lambda: '头像.jpg')
    monkeypatch.setattr(
        'app.components.file_info_card.cfg.get',
        lambda item: r'C:\Downloads',
    )
    monkeypatch.setattr(
        'app.components.file_info_card.QFileDialog.getSaveFileName',
        lambda parent, title, path: calls.append((parent, title, path))
        or (r'C:\Downloads\头像.jpg', ''),
    )
    monkeypatch.setattr(
        'app.components.file_info_card.signalBus',
        SimpleNamespace(
            downloadAsSig=SimpleNamespace(
                emit=lambda path: emitted.append(path),
            ),
        ),
    )

    FileToolBar.onSaveAs(toolbar)

    assert calls[0][2] == os.path.join(r'C:\Downloads', '头像.jpg')
    assert emitted == [r'C:\Downloads\头像.jpg']


def test_download_as_uses_requested_destination_for_file(monkeypatch, tmp_path):
    interface = BrowseInterface.__new__(BrowseInterface)
    remote_path = '/docs/readme.txt'
    requested = tmp_path / 'custom.txt'
    created = []
    runs = []

    monkeypatch.setattr(interface, 'selectedPath', lambda: remote_path)
    monkeypatch.setattr(interface, 'tr', lambda key, *args: key)
    monkeypatch.setattr(
        'app.view.browse_interface.netdiskService.isFile',
        lambda path: True,
    )
    monkeypatch.setattr(
        'app.view.browse_interface.netdiskService.getRepo',
        lambda: 'owner/repo',
    )
    monkeypatch.setattr(
        'app.view.browse_interface.netdiskService.getBranch',
        lambda: 'main',
    )
    monkeypatch.setattr(
        'app.view.browse_interface.netdiskService.getContent',
        lambda path: {':size': 123},
    )
    monkeypatch.setattr(
        'app.view.browse_interface.transferTaskService.create',
        lambda *args, **kwargs: created.append(args) or object(),
    )
    monkeypatch.setattr(
        interface,
        '_runTransfer',
        lambda *args, **kwargs: runs.append(args),
    )

    BrowseInterface.downloadSelectedAs(interface, str(requested))

    assert created[0][3] == str(requested)
    assert runs


