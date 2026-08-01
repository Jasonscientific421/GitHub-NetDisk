from urllib.parse import parse_qs, urlsplit

import pytest

from app.common.url_scheme import (
    BrowseRepoRequest,
    NewTaskRequest,
    parse_app_url,
    redirect_base_url,
    redirect_link,
    release_download_link,
    split_netdisk_uri,
)


def test_parse_new_task_with_encoded_url():
    value = (
        'github-netdisk://new-task/download/url/'
        '?uri=https%3A%2F%2Fexample.com%3A8443%2Fa%2Fb.zip&filename=b.zip'
    )
    assert parse_app_url(value) == NewTaskRequest(
        'download', 'url', 'https://example.com:8443/a/b.zip', 'b.zip')


def test_parse_browse_repo_and_netdisk_uri():
    assert parse_app_url(
        'github-netdisk://browse-repo/?repo=owner%2Frepo&branch=dev'
    ) == BrowseRepoRequest('owner/repo', 'dev')
    assert split_netdisk_uri('owner/repo@main/path/to/file') == (
        'owner/repo', 'main', '/path/to/file')


def test_rejects_invalid_urls():
    assert parse_app_url('https://example.com') is None
    with pytest.raises(ValueError):
        parse_app_url('github-netdisk://new-task/delete/repo/?uri=x')


def test_generated_links_encode_query_and_asset_names():
    link = redirect_link(
        'owner/repo', 'main', '/a/b.txt', 'new b.txt', 'tag/v1', 'b 1.txt', 42)
    query = parse_qs(urlsplit(link).query)
    assert query == {
        'repo': ['owner/repo'],
        'branch': ['main'],
        'path': ['/a/b.txt'],
        'filename': ['new b.txt'],
        'origin': ['tag/v1/b 1.txt'],
        'size': ['42'],
    }
    assert release_download_link('owner/repo', 'tag/v1', 'b 1.txt').endswith(
        '/tag%2Fv1/b%201.txt')
    assert release_download_link('owner/repo', 'tag/v1', '头像.jpg').endswith(
        '/tag%2Fv1/default.jpg')


def test_redirect_endpoint_follows_application_language():
    assert redirect_base_url('zh_CN').endswith('/zh/redirect')
    assert redirect_base_url('zh-HK').endswith('/zh-hk/redirect')
    assert redirect_base_url('en_US').endswith('.top/redirect')


