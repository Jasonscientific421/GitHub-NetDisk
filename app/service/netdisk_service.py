# coding: utf-8
"""GitHub Release backed virtual file system.

``netdisk.json`` is deliberately small: folders are dictionaries and files are
dictionaries whose keys start with ``:``.  File bytes live in a dedicated
GitHub Release, which makes repository clones stay lightweight.
"""
import hashlib
import json
import mimetypes
import os
import posixpath
import re
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from enum import Enum
from json import dumps, loads
from pathlib import Path
from threading import RLock
from time import monotonic, sleep
from typing import Callable, List, Optional, Union
from urllib.parse import urlsplit

import requests
from PyQt5.QtCore import QLocale, pyqtProperty
from github import GithubException, UnknownObjectException

from .aria2_download_service import aria2DownloadService
from .auth_service import authService
from ..common.config import cfg
from ..common.event_logger import (
    exceptionDetail,
    logChanged,
    logFailed,
    logStarted,
    logSucceeded,
)
from ..common.transfer_utils import isTransferCancelledError
from .github_service import (
    getFastestGithubMirror,
    getRepo,
    getRepoBranches,
    githubProxyUrl,
    hasWriteAccess,
    releaseAssetName,
)


SCHEMA_VERSION = 1
# GitHub currently accepts release assets up to 2 GiB.  Leave headroom for
# proxies and GitHub Enterprise installations with slightly smaller limits.
MAX_ASSET_SIZE = 1900 * 1024 * 1024


class _TransferCancelled(Exception):
    """Raised internally when the user cancels a transfer mid-operation."""



# Files that fit in one Release asset stay intact so their direct download
# link remains available. Only files above GitHub's asset limit are split.
UPLOAD_WORKERS = 4
UPLOAD_RETRIES = 3
MAX_RELEASE_ASSETS = 1000

netdisk_json_example = {
    "version": SCHEMA_VERSION,
    "files": {
        "example_folder": {
            "a_file.txt": {
                ":file": "release-tag",
                ":assets": ["a_file.txt"],
                ":hash": "sha256 hex digest",
                ":size": 2097152,
            }
        }
    },
}


def createUploadResumeData(path: str, tag: str = None) -> dict:
    """Create the stable checkpoint metadata persisted with an upload task."""
    source = os.path.abspath(path)
    stat = os.stat(source)
    return {
        'releaseTag': tag or f'netdisk-{uuid.uuid4().hex}',
        'sourceSize': stat.st_size,
        'sourceMtimeNs': stat.st_mtime_ns,
        'partSize': MAX_ASSET_SIZE,
    }


def sourceMatchesResumeData(path: str, resume_data: dict) -> bool:
    """Return whether a source still matches its persisted upload identity."""
    try:
        stat = os.stat(path)
        return (
            stat.st_size == int(resume_data['sourceSize'])
            and stat.st_mtime_ns == int(resume_data['sourceMtimeNs'])
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False


class _ProgressFile:
    """Read one file segment and report progress at most every 100ms."""

    def __init__(self, path, callback, offset=0, length=None):
        self._file = open(path, 'rb')
        self._offset = max(0, int(offset or 0))
        available = max(0, os.path.getsize(path) - self._offset)
        self._size = available if length is None else min(available, max(0, int(length)))
        self._callback = callback
        self._transferred = 0
        self._last_report = 0.0
        self._file.seek(self._offset)

    def __len__(self):
        return self._size

    def __getattr__(self, name):
        return getattr(self._file, name)

    def read(self, size=-1):
        remaining = self._size - self._transferred
        if remaining <= 0:
            data = b''
        else:
            read_size = remaining if size is None or size < 0 else min(size, remaining)
            data = self._file.read(read_size)
            if not data:
                raise IOError('Unexpected end of file while streaming upload.')
        self._transferred += len(data)
        now = monotonic()
        if (now - self._last_report >= 0.1
                or not data
                or self._transferred >= self._size):
            self._last_report = now
            self._callback(self._transferred)
        return data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._file.close()


class _UploadProgress:
    """Thread-safe aggregation for several parallel asset uploads."""

    def __init__(self, lengths, completed, callback):
        self._lengths = tuple(lengths)
        self._current = {
            index: (length if index in completed else 0)
            for index, length in enumerate(self._lengths)
        }
        self._callback = callback
        self._lock = RLock()

    def report(self):
        with self._lock:
            current = sum(self._current.values())
            if self._callback:
                self._callback(current, sum(self._lengths))

    def update(self, index, current):
        with self._lock:
            # Keep aggregate progress monotonic if an individual request is
            # retried from its beginning.
            bounded = min(self._lengths[index], max(0, int(current or 0)))
            self._current[index] = max(self._current[index], bounded)
            if self._callback:
                self._callback(sum(self._current.values()), sum(self._lengths))


def sanitizedDownloadError(error) -> str:
    """Remove URL user information before logging or showing an error."""
    return re.sub(
        r'(https?://)[^/@\s]+:[^/@\s]+@',
        r'\1***:***@',
        str(error),
    )


class NetdiskItemType(Enum):
    FOLDER = 1
    FILE = 0


class NetdiskService:
    """A virtual disk stored in a GitHub repository and its Release assets."""

    def __init__(self, repo: str = None, branch: str = None):
        self._repo = None
        self._branch = None
        self._content = None
        self._cwd = "/"
        if branch and not repo:
            raise ValueError("You should set a repo first.")
        if repo:
            logStarted('Log.Action.Repository', repo)
            self._repo = getRepo(repo, authService.accessToken())
            if not self._repo:
                logFailed('Log.Action.Repository', repo)
                raise ValueError("Failed to open repository.")
            self._branch = branch or self._repo.default_branch
            self.forceReload(create_if_missing=False)
            logSucceeded('Log.Action.Repository', self._repo.full_name)

    @staticmethod
    def _validate_content(content: dict) -> dict:
        if not isinstance(content, dict) or content.get("version") != SCHEMA_VERSION:
            version = content.get("version") if isinstance(content, dict) else None
            raise ValueError(f"Unsupported netdisk.json version: {version!r}")
        if not isinstance(content.get("files"), dict):
            raise ValueError("Invalid netdisk.json: `files` must be an object.")
        return content

    def forceReload(self, create_if_missing: bool = True):
        """Reload ``netdisk.json`` from the selected branch."""
        self._require_repo()
        logStarted('Log.Action.NetdiskIndex', f'{self._repo.full_name}@{self._branch}')
        try:
            raw = self._repo.get_contents("netdisk.json", ref=self._branch)
            self._content = self._validate_content(loads(raw.decoded_content.decode("utf-8")))
        except UnknownObjectException:
            if not create_if_missing:
                logFailed('Log.Action.NetdiskIndex', f'{self._repo.full_name}@{self._branch}')
                raise ValueError(
                    "This repository is not a GitHub-NetDisk repository (netdisk.json is missing)."
                )
            self._content = {"version": SCHEMA_VERSION, "files": {}}
            self._repo.create_file(
                "netdisk.json",
                "Initialize GitHub-NetDisk",
                dumps(self._content, ensure_ascii=False, indent=2),
                branch=self._branch,
            )
        self._cwd = "/"
        logSucceeded('Log.Action.NetdiskIndex', f'{self._repo.full_name}@{self._branch}')

    def _require_repo(self):
        if not self._repo:
            raise RuntimeError("Please set a repository first.")

    def _normalize(self, path: str) -> str:
        self._require_repo()
        path = str(path or ".").replace("\\", "/")
        base = "/" if path.startswith("/") else self._cwd
        normalized = posixpath.normpath(posixpath.join(base, path))
        if not normalized.startswith("/"):
            normalized = "/" + normalized
        if any(part.startswith(":") for part in normalized.strip("/").split("/") if part):
            raise ValueError("File and folder names cannot start with ':'.")
        return normalized

    def getcwd(self) -> str:
        self._require_repo()
        return self._cwd

    def chdir(self, path: str):
        path = self._normalize(path)
        if not self.isDir(path):
            raise NotADirectoryError(path)
        self._cwd = path
        logChanged('Log.Action.Folder', path, level='debug')

    def abspath(self, path: str) -> str:
        """Return an absolute virtual path without changing the current directory."""
        return self._normalize(path)

    def join(self, path1: str, *paths: str) -> str:
        self._require_repo()
        value = str(path1 or "/")
        for path in paths:
            value = posixpath.join(value, str(path))
        return self._normalize(value)

    def _parent_and_name(self, path: str):
        absolute = self._normalize(path)
        if absolute == "/":
            raise ValueError("The root folder cannot be modified.")
        return posixpath.dirname(absolute) or "/", posixpath.basename(absolute)

    def getContent(self, path=None):
        """Return the metadata object, or the node at ``path``.

        ``None`` keeps compatibility with the original API and returns the full
        document.  Passing ``/`` returns the root folder's children.
        """
        self._require_repo()
        if path is None:
            return self._content
        node = self._content["files"]
        for part in self._normalize(path).strip("/").split("/"):
            if part:
                node = node[part]
        return node

    def exists(self, path: str) -> bool:
        try:
            self.getContent(path)
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def mkdir(self, path: str, push: bool = True):
        """Create ``path`` and missing parents."""
        self._require_write()
        absolute = self._normalize(path)
        logStarted('Log.Action.CreateFolder', absolute)
        node = self._content["files"]
        changed = False
        for part in absolute.strip("/").split("/"):
            if not part:
                continue
            child = node.get(part)
            if child is None:
                child = {}
                node[part] = child
                changed = True
            if not isinstance(child, dict) or ":file" in child:
                raise NotADirectoryError(absolute)
            node = child
        if changed and push:
            self.pushContent()
        logSucceeded('Log.Action.CreateFolder', absolute)

    def listdir(self, path: str = None):
        path = self._cwd if path is None else path
        node = self.getContent(path)
        if ":file" in node:
            raise NotADirectoryError(path)
        return [key for key in node if not key.startswith(":")]

    def walk(self, top: str = None, onerror: Optional[Callable] = None) -> List[tuple]:
        top = self._normalize(self._cwd if top is None else top)
        result = []
        try:
            dirs, files = [], []
            for name in self.listdir(top):
                (dirs if self.isDir(self.join(top, name)) else files).append(name)
            dirs.sort(key=str.casefold)
            files.sort(key=str.casefold)
            result.append((top, dirs, files))
            for name in dirs:
                result.extend(self.walk(self.join(top, name), onerror))
        except Exception as error:
            if onerror:
                onerror(error)
            else:
                raise
        return result

    def getItemType(self, path: str) -> NetdiskItemType:
        node = self.getContent(path)
        return NetdiskItemType.FILE if ":file" in node else NetdiskItemType.FOLDER

    def isDir(self, path: str) -> bool:
        return self.getItemType(path) == NetdiskItemType.FOLDER

    def isFile(self, path: str) -> bool:
        return self.getItemType(path) == NetdiskItemType.FILE

    def copy(self, oldPath: str, newPath: str, push: bool = True):
        self._require_write()
        old_path = self._normalize(oldPath)
        logStarted('Log.Action.Copy', f'{old_path} -> {self._normalize(newPath)}')
        new_parent, new_name = self._parent_and_name(newPath)
        if not self.exists(old_path):
            raise FileNotFoundError(old_path)
        if self.exists(newPath):
            raise FileExistsError(self._normalize(newPath))
        parent = self.getContent(new_parent)
        if ":file" in parent:
            raise NotADirectoryError(new_parent)
        parent[new_name] = deepcopy(self.getContent(old_path))
        if push:
            self.pushContent()
        logSucceeded('Log.Action.Copy', f'{old_path} -> {self._normalize(newPath)}')

    def move(self, oldPath: str, newPath: str):
        self._require_write()
        old_path = self._normalize(oldPath)
        new_path = self._normalize(newPath)
        logStarted('Log.Action.Move', f'{old_path} -> {new_path}')
        if self.isDir(old_path) and new_path.startswith(old_path.rstrip("/") + "/"):
            raise ValueError("A folder cannot be moved into itself.")
        old_parent, old_name = self._parent_and_name(old_path)
        new_parent, new_name = self._parent_and_name(new_path)
        if self.exists(new_path):
            raise FileExistsError(new_path)
        target = self.getContent(new_parent)
        target[new_name] = deepcopy(self.getContent(old_path))
        del self.getContent(old_parent)[old_name]
        self.pushContent()
        logSucceeded('Log.Action.Move', f'{old_path} -> {new_path}')

    def rename(self, oldPath: str, newPath: str):
        old_path = self._normalize(oldPath)
        new_path = self._normalize(newPath)
        if posixpath.dirname(old_path) != posixpath.dirname(new_path):
            raise ValueError("rename() cannot move an item to another folder.")
        logStarted('Log.Action.Rename', f'{old_path} -> {new_path}')
        self.move(old_path, new_path)
        logSucceeded('Log.Action.Rename', f'{old_path} -> {new_path}')

    def remove(self, path: str, delete_release: bool = True):
        """Remove a file/folder and releases referenced only by that subtree."""
        self._require_write()
        absolute = self._normalize(path)
        logStarted('Log.Action.Delete', absolute)
        parent, name = self._parent_and_name(absolute)
        node = self.getContent(absolute)
        tags = self._collect_release_tags(node)
        del self.getContent(parent)[name]
        self.pushContent()
        if delete_release:
            remaining_tags = self._collect_release_tags(
                self._content.get('files', {}))
            cleanup_errors = []
            for tag in sorted(tags - remaining_tags):
                try:
                    self._deleteReleaseAndTag(tag)
                except Exception as error:
                    cleanup_errors.append(f'{tag}: {error}')
            if cleanup_errors:
                raise RuntimeError(
                    'File metadata was deleted, but its GitHub Release or '
                    'tag could not be deleted: ' + '; '.join(cleanup_errors))
        logSucceeded('Log.Action.Delete', absolute)

    def _deleteReleaseAndTag(self, tag):
        """Delete both the GitHub Release object and its Git tag reference."""
        errors = []
        try:
            self._repo.get_release(tag).delete_release()
        except UnknownObjectException:
            pass
        except Exception as error:
            errors.append(f'Release: {error}')

        try:
            self._repo.get_git_ref(f'tags/{tag}').delete()
        except UnknownObjectException:
            # GitHub may already have removed the tag, or a release may have
            # been created from a tag that was deleted separately.
            pass
        except Exception as error:
            errors.append(f'tag: {error}')

        if errors:
            raise RuntimeError(', '.join(errors))

    @staticmethod
    def _collect_release_tags(node: dict) -> set:
        if ":file" in node:
            return {node[":file"]} if node[":file"] else set()
        tags = set()
        for key, value in node.items():
            if not key.startswith(":") and isinstance(value, dict):
                tags.update(NetdiskService._collect_release_tags(value))
        return tags

    def getDownloadLink(self, path: str, status: Callable = None) -> Union[str, List[str]]:
        path = self._normalize(path)
        if status:
            status('TaskInterface.ResolvingDownloadLink', ())
        logStarted('Log.Action.DownloadLink', path, level='debug')
        if not self.isFile(path):
            raise IsADirectoryError(path)
        metadata = self.getContent(path)
        release = self._repo.get_release(metadata[":file"])
        assets = list(release.get_assets())
        expected = metadata.get(":assets") or []
        if expected:
            order = {name: index for index, name in enumerate(expected)}
            assets.sort(key=lambda asset: order.get(asset.name, len(order)))
        if getattr(self._repo, 'private', False):
            repository = self._repo.full_name
            urls = [
                f'https://api.github.com/repos/{repository}/releases/assets/{asset.id}'
                for asset in assets
            ]
        else:
            urls = [asset.browser_download_url for asset in assets]
            if urls:
                if status:
                    status('TaskInterface.TestingDownloadMirror', ())
                mirror = getFastestGithubMirror(urls[0])
                if mirror:
                    urls = [githubProxyUrl(url, mirror) for url in urls]
        if not urls:
            logFailed('Log.Action.DownloadLink', path)
            raise FileNotFoundError(f"Release {metadata[':file']!r} contains no assets.")
        logSucceeded('Log.Action.DownloadLink', f'{path}: {len(urls)}', level='debug')
        return urls[0] if len(urls) == 1 else urls

    def downloadFile(self, path: str, destination: str,
                     progress: Callable = None, status: Callable = None,
                     resume_bytes: int = 0, cancel_event=None) -> str:
        """Download and reassemble a virtual file, returning its local path.

        ``resume_bytes`` is used on retry to keep the partial ``.part`` file.
        ``cancel_event`` (``threading.Event``) is checked periodically; when
        set the download is aborted while preserving the partial file.
        """
        def report_status(key, *args):
            if status:
                status(key, args)

        received_data = False

        def report_progress(current, total):
            nonlocal received_data
            if cancel_event and cancel_event.is_set():
                raise _TransferCancelled()
            if current > 0 and not received_data:
                received_data = True
                report_status('TaskInterface.DownloadingFile')
            elif current <= 0 and not received_data:
                report_status('TaskInterface.WaitingForDownloadData')
            if progress:
                progress(current, total)

        metadata = self.getContent(path)
        logStarted('Log.Action.FileDownload', f'{path} -> {destination}')
        links = self.getDownloadLink(path, status=status)
        links = [links] if isinstance(links, str) else links
        destination = os.path.abspath(destination)
        if os.path.isdir(destination):
            destination = os.path.join(destination, posixpath.basename(self._normalize(path)))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        temp_path = destination + ".part"
        token = authService.accessToken()
        uses_asset_api = any(
            link.startswith('https://api.github.com/repos/')
            for link in links
        )
        headers = {}
        if uses_asset_api:
            headers = {
                'Accept': 'application/octet-stream',
                'X-GitHub-Api-Version': '2022-11-28',
            }
            if token:
                headers['Authorization'] = f'Bearer {token}'
        try:
            if cfg.get(cfg.aria2Enabled):
                try:
                    report_status('TaskInterface.StartingAria2')
                    aria2DownloadService.download(
                        links,
                        temp_path,
                        total=metadata.get(':size', 0),
                        progress=report_progress,
                        headers=headers,
                        status=status,
                        cancel_event=cancel_event,
                    )
                except _TransferCancelled:
                    raise
                except Exception as error:
                    if (cancel_event and cancel_event.is_set()
                            or isTransferCancelledError(error)):
                        raise _TransferCancelled()
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    received_data = False
                    logFailed('Log.Action.Aria2Download', error)
                    logChanged(
                        'Log.Action.Aria2Download',
                        f'{type(error).__name__} -> requests',
                        level='warning',
                    )
                    report_status('TaskInterface.FallingBackToRequests')
                    self._downloadWithRequests(
                        links,
                        temp_path,
                        metadata.get(':size', 0),
                        report_progress,
                        headers,
                        cancel_event,
                    )
            else:
                logChanged(
                    'Log.Action.Aria2Download',
                    'requests',
                    level='debug',
                )
                report_status('TaskInterface.WaitingForDownloadData')
                self._downloadWithRequests(
                    links,
                    temp_path,
                    metadata.get(':size', 0),
                    report_progress,
                    headers,
                    cancel_event,
                )
            report_status('TaskInterface.VerifyingDownload')
            expected_hash = metadata.get(":hash")
            if expected_hash and self._sha256(temp_path) != expected_hash:
                raise IOError("Downloaded file checksum does not match netdisk.json.")
            os.replace(temp_path, destination)
            logSucceeded('Log.Action.FileDownload', f'{path} -> {destination}')
            return destination
        except _TransferCancelled:
            # Keep the partial file for later resume.
            raise
        except Exception as error:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            safe_error = sanitizedDownloadError(error)
            logFailed(
                'Log.Action.FileDownload',
                sanitizedDownloadError(exceptionDetail(error, path)),
            )
            raise RuntimeError(safe_error) from error

    @staticmethod
    def _downloadWithRequests(links, destination, total, progress, headers,
                              cancel_event=None):
        downloaded = 0
        with open(destination, 'wb') as output:
            for link in links:
                for attempt in range(3):
                    if cancel_event and cancel_event.is_set():
                        raise _TransferCancelled()
                    part_start = output.tell()
                    try:
                        request_headers = (
                            {} if urlsplit(link).username
                            else dict(headers or {}))
                        with requests.get(
                            link,
                            headers=request_headers,
                            stream=True,
                            timeout=(15, 60),
                        ) as response:
                            response.raise_for_status()
                            if progress and downloaded == 0:
                                progress(0, total)
                            for chunk in response.iter_content(256 * 1024):
                                if cancel_event and cancel_event.is_set():
                                    raise _TransferCancelled()
                                if chunk:
                                    output.write(chunk)
                                    downloaded += len(chunk)
                                    if progress:
                                        progress(downloaded, total)
                        break  # success — move to next link
                    except _TransferCancelled:
                        raise
                    except Exception:
                        output.seek(part_start)
                        output.truncate()
                        downloaded = part_start
                        if attempt == 2:
                            raise
                        sleep(2 ** attempt)

    def getSize(self, path: str) -> str:
        if not self.isFile(path):
            raise IsADirectoryError(path)
        size = int(self.getContent(path).get(":size", 0))
        return QLocale().formattedDataSize(size)

    def uploadFile(self, srcPath: str, dstPath: str, tag: str = None,
                   progress: Callable = None, resumeData: dict = None,
                   status: Callable = None):
        """Upload a file using parallel, restart-resumable Release assets.

        GitHub cannot continue a partially received Release asset.  Instead,
        large files use deterministic assets and an interrupted upload skips
        assets that GitHub already has with the expected size.
        """
        self._require_write()
        def report_status(key, *args):
            if status:
                status(key, args)

        report_status('TaskInterface.PreparingUpload')
        source = os.path.abspath(srcPath)
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        resume_data = dict(resumeData or {})
        if resume_data and not sourceMatchesResumeData(source, resume_data):
            raise ValueError('The source file changed after this upload task was created.')
        destination = self._normalize(dstPath)
        logStarted('Log.Action.FileUpload', f'{source} -> {destination}')
        if self.exists(destination):
            metadata = self.getContent(destination)
            expected_tag = resume_data.get('releaseTag') or tag
            if (resume_data and metadata.get(':file') == expected_tag
                    and int(metadata.get(':size', -1)) == os.path.getsize(source)):
                if progress:
                    progress(os.path.getsize(source), os.path.getsize(source))
                logSucceeded('Log.Action.FileUpload', f'{source} -> {destination}')
                return
            raise FileExistsError(destination)
        parent, name = self._parent_and_name(destination)
        self.mkdir(parent, push=False)
        tag = resume_data.get('releaseTag') or tag or f"netdisk-{uuid.uuid4().hex}"
        try:
            release = self._repo.get_release(tag)
        except UnknownObjectException:
            release = self._repo.create_git_release(
                tag=tag,
                name=tag,
                message="GitHub-NetDisk file asset",
                draft=False,
                prerelease=True,
                make_latest="false",
            )

        try:
            size = os.path.getsize(source)
            plan = self._uploadPlan(
                name, size, resume_data.get('partSize', MAX_ASSET_SIZE))
            report_status('TaskInterface.CheckingUploadAssets')
            completed = self._completedUploadParts(release, plan)
            upload_progress = _UploadProgress(
                [part[2] for part in plan], completed, progress)
            upload_progress.report()
            if len(plan) == 1:
                report_status('TaskInterface.UploadingSingleAsset')
            else:
                report_status(
                    'TaskInterface.UploadingParts', len(completed), len(plan))

            # Hashing overlaps the network transfer instead of adding a full
            # serial pass over the file after the upload has finished.
            workers = min(UPLOAD_WORKERS, max(1, len(plan) - len(completed)))
            with ThreadPoolExecutor(max_workers=workers + 1) as executor:
                hash_future = executor.submit(self._sha256, source)
                futures = {
                    executor.submit(
                        self._uploadPartWithRetry,
                        release,
                        source,
                        part_name,
                        offset,
                        length,
                        lambda current, index=index:
                            upload_progress.update(index, current),
                    ): index
                    for index, (part_name, offset, length) in enumerate(plan)
                    if index not in completed
                }
                try:
                    for future in as_completed(futures):
                        future.result()
                        completed.add(futures[future])
                        if len(plan) > 1:
                            report_status(
                                'TaskInterface.UploadingParts',
                                len(completed),
                                len(plan),
                            )
                except Exception:
                    for future in futures:
                        future.cancel()
                    raise
                report_status('TaskInterface.VerifyingUpload')
                checksum = hash_future.result()

            if resume_data and not sourceMatchesResumeData(source, resume_data):
                raise ValueError('The source file changed while it was being uploaded.')

            asset_names = [part[0] for part in plan]
            self.getContent(parent)[name] = {
                ":file": tag,
                ":assets": asset_names,
                ":hash": checksum,
                ":size": size,
            }
            report_status('TaskInterface.UpdatingNetdiskIndex')
            self.pushContent()
            logSucceeded('Log.Action.FileUpload', f'{source} -> {destination}')
        except Exception as error:
            if not resume_data:
                try:
                    release.delete_release()
                except Exception as cleanup_error:
                    logFailed(
                        'Log.Action.FileUpload',
                        exceptionDetail(cleanup_error, tag),
                        level='warning',
                    )
            logFailed(
                'Log.Action.FileUpload',
                exceptionDetail(error, source),
            )
            raise

    @staticmethod
    def _uploadPlan(name, size, part_size=None):
        """Return deterministic ``(asset name, offset, length)`` entries."""
        name = releaseAssetName(name)
        size = max(0, int(size))
        part_size = max(1, min(
            int(part_size or MAX_ASSET_SIZE), MAX_ASSET_SIZE))
        if size <= part_size:
            return [(name, 0, size)]
        # Splitting is only used when GitHub cannot accept the file as one
        # asset; this preserves direct-link support for every eligible file.
        if size > part_size * MAX_RELEASE_ASSETS:
            part_size = (size + MAX_RELEASE_ASSETS - 1) // MAX_RELEASE_ASSETS
        if part_size > MAX_ASSET_SIZE:
            raise ValueError('File is too large for one GitHub Release.')
        return [
            (
                f'{name}.part{index + 1:04d}',
                offset,
                min(part_size, size - offset),
            )
            for index, offset in enumerate(range(0, size, part_size))
        ]

    @staticmethod
    def _completedUploadParts(release, plan):
        """Find valid assets and delete conflicting same-name assets."""
        if not hasattr(release, 'get_assets'):
            return set()
        assets = {asset.name: asset for asset in release.get_assets()}
        completed = set()
        for index, (name, _offset, length) in enumerate(plan):
            asset = assets.get(name)
            if not asset:
                continue
            if int(getattr(asset, 'size', -1)) == length:
                completed.add(index)
            else:
                asset.delete_asset()
        return completed

    @classmethod
    def _uploadPartWithRetry(cls, release, path, name, offset, length, progress):
        last_error = None
        for attempt in range(UPLOAD_RETRIES):
            try:
                cls._uploadAsset(release, path, name, offset, length, progress)
                return
            except Exception as error:
                last_error = error
                # A connection may fail after GitHub has accepted the asset.
                # Re-querying prevents an unnecessary full retransmission.
                try:
                    if any(
                        asset.name == name and int(asset.size) == length
                        for asset in release.get_assets()
                    ):
                        progress(length)
                        return
                except Exception:
                    pass
                if attempt + 1 < UPLOAD_RETRIES:
                    sleep(0.5 * (2 ** attempt))
        raise last_error

    @staticmethod
    def _uploadAsset(release, path, name, offset, length, progress):
        """Upload one Release asset with streaming progress when supported."""
        # Small fake/backward-compatible release implementations may only
        # expose PyGithub's public helper.
        if not getattr(release, 'upload_url', None):
            upload_path = path
            temporary = None
            if offset or length != os.path.getsize(path):
                temporary = tempfile.NamedTemporaryFile(
                    prefix='github-netdisk-', delete=False)
                upload_path = temporary.name
                try:
                    with temporary, open(path, 'rb') as source:
                        source.seek(offset)
                        remaining = length
                        while remaining:
                            chunk = source.read(min(8 * 1024 * 1024, remaining))
                            if not chunk:
                                raise IOError('Unexpected end of file while preparing upload.')
                            temporary.write(chunk)
                            remaining -= len(chunk)
                except Exception:
                    try:
                        os.remove(upload_path)
                    except OSError:
                        pass
                    raise
            try:
                release.upload_asset(upload_path, name=name)
            finally:
                if temporary:
                    try:
                        os.remove(upload_path)
                    except OSError:
                        pass
            if progress:
                progress(length)
            return

        headers = {
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'Content-Type': (
                mimetypes.guess_type(name)[0]
                or 'application/octet-stream'),
            'Content-Length': str(length),
        }
        token = authService.accessToken()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        callback = progress or (lambda _current: None)
        with _ProgressFile(path, callback, offset, length) as stream:
            response = requests.post(
                release.upload_url.split('{?')[0],
                params={'name': name},
                headers=headers,
                data=stream,
                timeout=(15, 300),
            )
        response.raise_for_status()

    @staticmethod
    def _sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def pushContent(self):
        self._require_write()
        logStarted('Log.Action.NetdiskIndex', f'{self.repo}@{self._branch}', level='debug')
        remote = self._repo.get_contents("netdisk.json", ref=self._branch)
        self._repo.update_file(
            "netdisk.json",
            "Update GitHub-NetDisk index",
            json.dumps(self._content, ensure_ascii=False, indent=2),
            remote.sha,
            branch=self._branch,
        )
        logSucceeded('Log.Action.NetdiskIndex', f'{self.repo}@{self._branch}', level='debug')

    def _require_write(self):
        self._require_repo()
        if not hasWriteAccess(self.repo, authService.accessToken()):
            logFailed('Log.Action.Repository', self.repo)
            raise PermissionError("The current GitHub account does not have write access to this repository.")

    def setRepo(self, repo: str) -> None:
        if not isinstance(repo, str):
            raise TypeError(f"repo: {type(repo)}")
        if self.getRepo() == repo:
            return
        target = getRepo(repo.strip(), authService.accessToken())
        if not target:
            raise ValueError("Failed to open repository.")
        previous = (self._repo, self._branch, self._content, self._cwd)
        try:
            self._repo = target
            self._branch = target.default_branch
            self.forceReload(create_if_missing=False)
        except BaseException:
            self._repo, self._branch, self._content, self._cwd = previous
            raise
        logChanged('Log.Action.Repository', target.full_name, level='debug')

    def getRepo(self) -> str:
        return self._repo.full_name if self._repo else ""

    repo = pyqtProperty(str, getRepo, setRepo)

    def setBranch(self, branch: str) -> None:
        self._require_repo()
        if not isinstance(branch, str):
            raise TypeError(f"branch: {type(branch)}")
        if self._branch == branch and self._content is not None:
            return
        logStarted('Log.Action.Branch', branch)
        if branch not in getRepoBranches(self._repo.full_name, authService.accessToken()):
            raise ValueError(f"Branch not found: {branch}")
        self._branch = branch
        self.forceReload(create_if_missing=False)
        logChanged('Log.Action.Branch', branch)

    def getBranch(self) -> str:
        return self._branch or ""

    branch = pyqtProperty(str, getBranch, setBranch)


netdiskService = NetdiskService()
