# coding: utf-8
from PyQt5.QtCore import QCoreApplication, QMimeData, Qt, QUrl
from PyQt5.QtGui import QStandardItem

from app.components.netdisk_tree_view import NetdiskTreeModel, NetdiskTreeView

app = QCoreApplication.instance() or QCoreApplication([])


def test_read_only_repository_items_are_not_editable(monkeypatch):
    model = NetdiskTreeModel()
    model.appendRow(QStandardItem('file.txt'))
    index = model.index(0, 0)
    monkeypatch.setattr(model._netdisk, 'getRepo', lambda: 'owner/repository')
    monkeypatch.setattr(
        'app.components.netdisk_tree_view.hasWriteAccess',
        lambda repo, token: False,
    )

    assert not model.flags(index) & Qt.ItemIsEditable


def test_writable_repository_name_items_remain_editable(monkeypatch):
    model = NetdiskTreeModel()
    model.appendRow(QStandardItem('file.txt'))
    index = model.index(0, 0)
    monkeypatch.setattr(model._netdisk, 'getRepo', lambda: 'owner/repository')
    monkeypatch.setattr(
        'app.components.netdisk_tree_view.hasWriteAccess',
        lambda repo, token: True,
    )

    assert model.flags(index) & Qt.ItemIsEditable


def test_tree_drop_extracts_local_files_only(tmp_path):
    file_path = tmp_path / 'upload.txt'
    file_path.write_text('content', encoding='utf-8')
    folder_path = tmp_path / 'folder'
    folder_path.mkdir()
    mime_data = QMimeData()
    mime_data.setUrls([
        QUrl.fromLocalFile(str(file_path)),
        QUrl.fromLocalFile(str(folder_path)),
        QUrl('https://example.com/remote.txt'),
    ])

    assert NetdiskTreeView.localDropFiles(mime_data) == [str(file_path)]


def test_model_reload_fetches_remote_index_before_rebuilding(monkeypatch):
    model = NetdiskTreeModel()
    calls = []
    monkeypatch.setattr(
        model._netdisk,
        'forceReload',
        lambda create_if_missing: calls.append(
            ('fetch', create_if_missing)),
    )
    monkeypatch.setattr(model, 'forceLoad', lambda: calls.append(('build',)))

    model.reload()

    assert calls == [('fetch', False), ('build',)]
