# coding: utf-8
"""Parsing and generation for GitHub-NetDisk application links."""
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from ..service.github_service import releaseAssetName


SCHEME = 'github-netdisk'
WEBSITE_BASE_URL = 'https://github-netdisk.top'


@dataclass(frozen=True)
class NewTaskRequest:
    direction: str
    target_type: str
    uri: str
    filename: str = ''


@dataclass(frozen=True)
class BrowseRepoRequest:
    repo: str
    branch: str = ''


def parse_app_url(value: str):
    """Parse a supported custom-protocol URL into a typed request."""
    parsed = urlsplit(str(value or '').strip())
    if parsed.scheme.lower() != SCHEME:
        return None

    action = parsed.netloc.lower()
    query = parse_qs(parsed.query, keep_blank_values=True)
    if action == 'new-task':
        parts = [part.lower() for part in parsed.path.split('/') if part]
        if len(parts) != 2:
            raise ValueError('A new-task URL requires direction and target type.')
        direction, target_type = parts
        if direction not in ('download', 'upload'):
            raise ValueError('Task direction must be download or upload.')
        if target_type not in ('repo', 'url'):
            raise ValueError('Task target type must be repo or url.')
        uri = (query.get('uri') or [''])[0].strip()
        filename = (query.get('filename') or [''])[0].strip()
        if not uri:
            raise ValueError('Task URI cannot be empty.')
        return NewTaskRequest(direction, target_type, uri, filename)

    if action == 'browse-repo':
        repo = (query.get('repo') or [''])[0].strip().strip('/')
        branch = (query.get('branch') or [''])[0].strip()
        if repo.count('/') != 1:
            raise ValueError('Repository must use the owner/repository format.')
        return BrowseRepoRequest(repo, branch)

    raise ValueError(f'Unsupported GitHub-NetDisk URL action: {action or "/"}')


def split_netdisk_uri(uri: str):
    """Return ``(repository, branch, path)`` from owner/repo@branch/path."""
    value = str(uri or '').strip().lstrip('/')
    if '@' not in value:
        raise ValueError('Netdisk URI must include @branch.')
    repository, remainder = value.split('@', 1)
    if repository.count('/') != 1 or '/' not in remainder:
        raise ValueError('Netdisk URI must include owner/repo@branch/path.')
    branch, path = remainder.split('/', 1)
    if not branch or not path:
        raise ValueError('Netdisk branch and path cannot be empty.')
    return repository, branch, '/' + path.lstrip('/')


def redirect_base_url(locale_name: str = '') -> str:
    """Return the localized website redirect endpoint."""
    locale = str(locale_name or '').lower().replace('-', '_')
    if locale.startswith('zh_cn') or locale.startswith('zh_sg'):
        prefix = '/zh'
    elif locale.startswith(('zh_hk', 'zh_tw', 'zh_mo')):
        prefix = '/zh-hk'
    else:
        prefix = ''
    return f'{WEBSITE_BASE_URL}{prefix}/redirect'


def redirect_link(repository: str, branch: str, path: str, filename: str,
                  release_tag: str, asset_name: str, size: int,
                  locale_name: str = '') -> str:
    """Build the website redirect URL for a virtual file."""
    query = urlencode({
        'repo': repository,
        'branch': branch,
        'path': '/' + str(path or '').lstrip('/'),
        'filename': filename,
        'origin': f'{release_tag}/{asset_name}',
        'size': max(0, int(size or 0)),
    })
    return f'{redirect_base_url(locale_name)}?{query}'


def release_download_link(repository: str, release_tag: str,
                          asset_name: str) -> str:
    """Build GitHub's public browser download URL for one Release asset."""
    repository = repository.strip('/')
    asset_name = releaseAssetName(asset_name)
    return (
        f'https://github.com/{repository}/releases/download/'
        f'{quote(str(release_tag), safe="")}/{quote(str(asset_name), safe="")}'
    )


def default_filename(uri: str, direction: str) -> str:
    """Choose a useful initial filename for the add-task dialog."""
    if direction == 'upload':
        return ''
    try:
        if urlsplit(uri).scheme in ('http', 'https'):
            return PurePosixPath(urlsplit(uri).path).name
        return PurePosixPath(split_netdisk_uri(uri)[2]).name
    except ValueError:
        return ''



