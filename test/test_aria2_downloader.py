# coding: utf-8
from pathlib import Path

from app.service.aria2_download_service import Aria2DownloadService


class FakeStdout:
    def __init__(self, lines):
        self.lines = list(lines)

    def readline(self):
        return self.lines.pop(0) if self.lines else ''


class FakeProcess:
    def __init__(self, args, lines=None, returncode=0):
        self.args = args
        self.stdout = FakeStdout(lines or [])
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode if not self.stdout.lines else None

    def terminate(self):
        self.terminated = True


def test_aria2_downloads_and_reassembles_release_assets(monkeypatch, tmp_path):
    downloader = Aria2DownloadService()
    monkeypatch.setattr(downloader, '_ensure_executable', lambda: 'aria2c')
    processes = []

    def popen(args, **_kwargs):
        output_path = Path(args[args.index('--dir') + 1]) / args[args.index('--out') + 1]
        data = b'a' if args[1].endswith('/a') else b'b'
        output_path.write_bytes(data)
        process = FakeProcess(
            args,
            [f'[#123 {len(data)}B/{len(data)}B(100%) CN:1 DL:1KiB ETA:0s]\n'],
        )
        processes.append(process)
        return process

    monkeypatch.setattr('app.service.aria2_download_service.subprocess.Popen', popen)
    destination = tmp_path / 'assembled.part'
    progress = []

    downloader.download(
        ['https://github.com/a', 'https://user:token@mirror.example/b'],
        destination,
        total=2,
        progress=lambda current, total: progress.append((current, total)),
        headers={'Authorization': 'Bearer token'},
    )

    assert destination.read_bytes() == b'ab'
    assert processes[0].args[0] == 'aria2c'
    assert processes[0].args[1] == 'https://github.com/a'
    assert '--split=4' in processes[0].args
    assert '--max-connection-per-server=4' in processes[0].args
    assert '--header' in processes[0].args
    assert 'Authorization: Bearer token' in processes[0].args
    assert '--header' not in processes[1].args
    assert progress[-1] == (2, 2)


def test_aria2_failure_logs_the_exception(monkeypatch, tmp_path):
    downloader = Aria2DownloadService()
    monkeypatch.setattr(downloader, '_ensure_executable', lambda: 'aria2c')
    logged = []
    monkeypatch.setattr(
        'app.service.aria2_download_service.logFailed',
        lambda action, detail: logged.append((action, detail)),
    )

    def popen(args, **_kwargs):
        return FakeProcess(args, [], returncode=2)

    monkeypatch.setattr('app.service.aria2_download_service.subprocess.Popen', popen)

    try:
        downloader.download(
            ['https://example.com/file'],
            tmp_path / 'file.part',
        )
    except OSError:
        pass

    assert logged
    assert logged[0][0] == 'Log.Action.Aria2Download'
    assert isinstance(logged[0][1], OSError)


def test_aria2_cancel_logs_cancelled_not_failed(monkeypatch, tmp_path):
    downloader = Aria2DownloadService()
    monkeypatch.setattr(downloader, '_ensure_executable', lambda: 'aria2c')
    failed = []
    cancelled = []
    monkeypatch.setattr(
        'app.service.aria2_download_service.logFailed',
        lambda *args, **kwargs: failed.append(args),
    )
    monkeypatch.setattr(
        'app.service.aria2_download_service.logCancelled',
        lambda *args, **kwargs: cancelled.append(args),
    )

    def popen(args, **_kwargs):
        return FakeProcess(args, ['[#123 1B/2B(50%) CN:1 DL:1KiB ETA:1s]\n'])

    monkeypatch.setattr('app.service.aria2_download_service.subprocess.Popen', popen)

    try:
        downloader.download(
            ['https://example.com/file'],
            tmp_path / 'file.part',
            progress=lambda *_args: (_ for _ in ()).throw(
                RuntimeError('download cancelled')),
        )
    except RuntimeError:
        pass

    assert failed == []
    assert cancelled == [('Log.Action.Aria2Download',)]

