# coding: utf-8
import sys
sys.path.append('..')
import pytest
from app.common.utils import (
    getFileTypeName,
    getUniqueFilePath,
    unwrapFutureError,
)

@pytest.mark.parametrize('filePath', [
    'file.txt',
    'file.py',
    'file.md',
    'file',
])
def test_getFileTypeName(filePath: str):
    # Friendly MIME descriptions are supplied by the operating system and are
    # therefore localized (for example "文本文档" on Chinese Windows and
    # "text/plain" on macOS).  The portable contract is a non-empty label.
    value = getFileTypeName(filePath)
    assert isinstance(value, str)
    assert value.strip()


def test_getUniqueFilePath_adds_incrementing_suffix(tmp_path):
    original = tmp_path / 'report.pdf'
    original.touch()
    (tmp_path / 'report (1).pdf').touch()

    assert getUniqueFilePath(original) == str(tmp_path / 'report (2).pdf')


def test_getUniqueFilePath_respects_reserved_downloads(tmp_path):
    original = tmp_path / 'archive.tar.gz'

    assert getUniqueFilePath(original, [original]) == str(
        tmp_path / 'archive.tar (1).gz')


def test_unwrap_future_error_returns_original_exception():
    original = ValueError('repository unavailable')

    class Wrapper:
        def __init__(self, value):
            self.original = value

    assert unwrapFutureError(Wrapper(Wrapper(original))) is original
