# coding: utf-8
"""This file is used to test the functionality of the NetdiskService class.
To test this file, you must install `pytest` module first.
"""
import sys
import os
sys.path.append('..')
import pytest
from app.service.netdisk_service import NetdiskService, NetdiskItemType

pytestmark = pytest.mark.skipif(
    os.environ.get('GITHUB_NETDISK_INTEGRATION') != '1',
    reason='set GITHUB_NETDISK_INTEGRATION=1 to run live GitHub tests',
)

@pytest.mark.parametrize('path', [
    '/',
    '/a_folder',
    '/a_folder/',
    '/a_folder/file1.txt',
    '/a_folder/file2.txt',
    'a_folder',
    'a_folder/',
    'a_folder/file1.txt',
    'a_folder/file2.txt'
])
def test_netdisk_test1_exists(path: str):
    disk = NetdiskService('xiaoshu312/Netdisk', 'test1')
    assert disk.exists(path), f'"{path}" exists test failed!'

@pytest.mark.parametrize('path', [
    '/',
    '/a_folder',
    '/a_folder/',
    'a_folder',
    'a_folder/',
])
def test_netdisk_test1_isdir(path: str):
    disk = NetdiskService('xiaoshu312/Netdisk', 'test1')
    assert disk.getItemType(path) == NetdiskItemType.FOLDER, f'"{path}" isdir test failed!'

@pytest.mark.parametrize('path', [
    '/a_folder/file1.txt',
    '/a_folder/file2.txt',
    'a_folder/file1.txt',
    'a_folder/file2.txt'
])
def test_netdisk_test1_isfile(path: str):
    disk = NetdiskService('xiaoshu312/Netdisk', 'test1')
    assert disk.getItemType(path) == NetdiskItemType.FILE, f'"{path}" isfile test failed!'

def test_netdisk_test1_listdir():
    disk = NetdiskService('xiaoshu312/Netdisk', 'test1')
    assert disk.listdir('/') == ['a_folder'], 'listdir test "/" failed!'
    assert disk.listdir('/a_folder') == ['file1.txt', 'file2.txt'], 'listdir test "/a_folder" failed!'
    assert disk.listdir('a_folder') == ['file1.txt', 'file2.txt'], 'listdir test "a_folder" failed!'


