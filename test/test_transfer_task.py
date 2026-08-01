# coding: utf-8
from datetime import datetime, timedelta
import json

from app.service.transfer_task_service import (
    TransferDirection,
    TransferStatus,
    TransferTask,
    TransferTaskService,
)
from app.view.task_interface import TaskInterface, TransferTaskView


def test_transfer_task_lifecycle():
    manager = TransferTaskService()
    started = []
    manager.taskStarted.connect(started.append)
    task = manager.create(
        TransferDirection.DOWNLOAD,
        'report.pdf',
        '/remote/report.pdf',
        '/tmp/report.pdf',
        100,
        'owner/repository',
        'main',
    )
    assert task.status == TransferStatus.PENDING
    assert task.progress == 0
    assert task.started_at is None
    assert task.repository == 'owner/repository'
    assert task.branch == 'main'

    manager.start(task)
    assert task.started_at is not None
    first_started_at = task.started_at
    manager.start(task)
    assert task.started_at == first_started_at
    assert started == [task]
    manager.updateProgress(task, 40, 100)
    assert task.status == TransferStatus.RUNNING
    assert task.progress == 0.4

    manager.finish(task)
    assert task.status == TransferStatus.SUCCESS
    assert task.progress == 1
    assert task.finished_at is not None

    assert manager.remove(task.id)
    assert manager.tasks() == []


def test_clear_history_preserves_active_tasks():
    manager = TransferTaskService()
    active = manager.create(TransferDirection.UPLOAD, 'active.txt', 'a', 'b', 1)
    failed = manager.create(TransferDirection.DOWNLOAD, 'failed.txt', 'a', 'b', 1)
    manager.start(active)
    manager.fail(failed, 'network error')

    manager.clearFinished()
    assert manager.tasks() == [active]
    assert active.status == TransferStatus.RUNNING


def test_clear_history_preserves_paused_tasks():
    manager = TransferTaskService()
    paused = manager.create(TransferDirection.UPLOAD, 'paused.txt', 'a', 'b', 1)
    failed = manager.create(TransferDirection.DOWNLOAD, 'failed.txt', 'a', 'b', 1)
    manager.start(paused)
    manager.pauseTask(paused)
    manager.fail(paused, RuntimeError('transfer cancelled'))
    manager.fail(failed, 'network error')

    manager.clearFinished()

    assert manager.tasks() == [paused]
    assert paused.is_paused_result


def test_transfer_speed_uses_rolling_window_and_stall_timeout():
    manager = TransferTaskService()
    task = manager.create(
        TransferDirection.DOWNLOAD, 'speed.bin', 'a', 'b', 1000)
    task.status = TransferStatus.RUNNING
    task.resetSpeed(10.0)

    assert task.recordProgress(100, 10.5) == 200
    assert task.recordProgress(300, 11.5) == 200
    assert task.currentSpeed(12.6) == 0

    manager.finish(task)
    assert task.speed == 0
    assert task.currentSpeed(12.7) == 0


def test_transfer_stage_is_updated_and_cleared_on_completion():
    manager = TransferTaskService()
    task = manager.create(
        TransferDirection.UPLOAD, 'large.bin', 'a', 'b', 1000)
    manager.start(task)

    manager.updateStage(
        task, 'TaskInterface.UploadingParts', (2, 4))
    assert task.stage_key == 'TaskInterface.UploadingParts'
    assert task.stage_args == (2, 4)

    manager.finish(task)
    assert task.stage_key == ''
    assert task.stage_args == ()


def test_tasks_are_sorted_from_late_to_early_start_time():
    manager = TransferTaskService()
    later = manager.create(TransferDirection.DOWNLOAD, 'later.txt', 'a', 'b', 1)
    earlier = manager.create(TransferDirection.UPLOAD, 'earlier.txt', 'a', 'b', 1)
    base = datetime.now()
    later.started_at = base + timedelta(seconds=1)
    earlier.started_at = base

    assert manager.tasks() == [later, earlier]


def test_transfer_tasks_are_restored_from_disk(tmp_path):
    storage = tmp_path / 'transfer_tasks.json'
    manager = TransferTaskService(storage_path=storage)
    task = manager.create(
        TransferDirection.DOWNLOAD,
        'archive.zip',
        '/archive.zip',
        '/tmp/archive.zip',
        100,
        'owner/archive',
        'release',
    )
    manager.start(task)
    manager.updateProgress(task, 40, 100)
    manager.save()

    assert json.loads(storage.read_text(encoding='utf-8'))['version'] == 1

    restored = TransferTaskService(storage_path=storage).tasks()
    assert len(restored) == 1
    assert restored[0].file_name == 'archive.zip'
    assert restored[0].transferred == 40
    assert restored[0].repository == 'owner/archive'
    assert restored[0].branch == 'release'
    assert restored[0].status == TransferStatus.FAILED
    assert restored[0].error_key == 'TaskInterface.Interrupted'
    assert restored[0].started_at is not None
    assert restored[0].finished_at is not None


def test_removing_transfer_task_updates_persistent_history(tmp_path):
    storage = tmp_path / 'transfer_tasks.json'
    manager = TransferTaskService(storage_path=storage)
    task = manager.create(
        TransferDirection.UPLOAD,
        'report.txt',
        '/tmp/report.txt',
        '/report.txt',
        10,
    )
    manager.start(task)
    manager.finish(task)
    restored = TransferTaskService(storage_path=storage).tasks()
    assert len(restored) == 1
    assert restored[0].status == TransferStatus.SUCCESS
    assert restored[0].finished_at is not None
    assert manager.remove(task.id)

    assert TransferTaskService(storage_path=storage).tasks() == []


def test_resumable_upload_metadata_is_restored_and_can_restart(tmp_path):
    storage = tmp_path / 'transfer_tasks.json'
    source = tmp_path / 'video.mp4'
    source.write_bytes(b'video')
    resume_data = {
        'releaseTag': 'netdisk-resume',
        'sourceSize': 5,
        'sourceMtimeNs': source.stat().st_mtime_ns,
        'partSize': 100,
    }
    manager = TransferTaskService(storage_path=storage)
    task = manager.create(
        TransferDirection.UPLOAD,
        source.name,
        str(source),
        '/video.mp4',
        5,
        'owner/repo',
        'main',
        resume_data,
    )
    manager.start(task)
    manager.updateProgress(task, 3, 5)
    manager.save()

    restored_manager = TransferTaskService(storage_path=storage)
    restored = restored_manager.tasks()[0]
    assert restored.resume_data == resume_data
    assert restored.can_resume
    assert restored_manager.restart(restored)
    assert restored.status == TransferStatus.RUNNING
    assert restored.transferred == 0
    assert restored.error_key == ''
    assert restored.finished_at is None


def test_task_interface_prefers_newest_active_direction():
    manager = TransferTaskService()
    older_upload = manager.create(
        TransferDirection.UPLOAD, 'old.txt', 'a', 'b', 1)
    newer_download = manager.create(
        TransferDirection.DOWNLOAD, 'new.txt', 'a', 'b', 1)
    base = datetime.now()
    older_upload.created_at = base
    newer_download.created_at = base + timedelta(seconds=1)

    assert TaskInterface.preferredRouteKey(manager.tasks()) == 'downloadingTasks'

    manager.finish(older_upload)
    manager.finish(newer_download)
    assert TaskInterface.preferredRouteKey(manager.tasks()) == 'completedTasks'


def test_task_interface_routes_paused_tasks_to_transfer_direction():
    download = TransferTask(
        TransferDirection.DOWNLOAD,
        'paused.bin',
        '/paused.bin',
        '/tmp/paused.bin',
        100,
    )
    upload = TransferTask(
        TransferDirection.UPLOAD,
        'paused.txt',
        '/tmp/paused.txt',
        '/paused.txt',
        100,
    )
    for task in (download, upload):
        task.status = TransferStatus.FAILED
        task.error_key = 'TaskInterface.Paused'

    assert TaskInterface.preferredRouteKey([download]) == 'downloadingTasks'
    assert TaskInterface.preferredRouteKey([upload]) == 'uploadingTasks'


def test_paused_download_can_resume_without_partial_file(tmp_path):
    manager = TransferTaskService()
    task = manager.create(
        TransferDirection.DOWNLOAD,
        'paused.bin',
        '/paused.bin',
        str(tmp_path / 'paused.bin'),
        100,
    )
    manager.start(task)
    manager.updateProgress(task, 40, 100)
    manager.pauseTask(task)
    manager.fail(task, RuntimeError('transfer cancelled'))

    assert task.can_resume
    assert manager.restart(task)
    assert task.status == TransferStatus.RUNNING
    assert task.transferred == 0


def test_paused_task_views_accept_only_direction_views():
    download = TransferTask(
        TransferDirection.DOWNLOAD,
        'paused.bin',
        '/paused.bin',
        '/tmp/paused.bin',
        100,
    )
    download.status = TransferStatus.FAILED
    download.error_key = 'TaskInterface.Paused'

    class View:
        accepts = TransferTaskView.accepts

    downloading = View()
    downloading.statuses = (TransferStatus.PENDING, TransferStatus.RUNNING)
    downloading.direction = TransferDirection.DOWNLOAD
    downloading.include_paused = True
    completed = View()
    completed.statuses = (TransferStatus.SUCCESS, TransferStatus.FAILED)
    completed.direction = None
    completed.include_paused = False

    assert downloading.accepts(download)
    assert not completed.accepts(download)


def test_task_interface_logs_only_first_five_initial_tasks(monkeypatch):
    decisions = [
        TaskInterface.shouldLogInitialTask(index)
        for index in range(7)
    ]

    assert decisions == [True, True, True, True, True, False, False]
    assert TaskInterface.initialTaskLogOverflow(7) == 2
    assert TaskInterface.initialTaskLogOverflow(5) == 0


def test_cancelled_task_uses_cancelled_result_state():
    task = TransferTask(
        TransferDirection.DOWNLOAD,
        'movie.mp4',
        '/movie.mp4',
        '/tmp/movie.mp4',
        100,
    )
    task.status = TransferStatus.FAILED
    task.error = ''
    task.error_key = 'TaskInterface.Cancelled'

    assert task.is_cancelled_result


def test_pause_task_requests_pause_stage():
    manager = TransferTaskService()
    task = manager.create(
        TransferDirection.DOWNLOAD,
        'movie.mp4',
        '/movie.mp4',
        '/tmp/movie.mp4',
        100,
    )
    manager.start(task)
    manager.pauseTask(task)

    assert task.is_cancelled
    assert task.stop_reason == 'paused'
    assert task.stage_key == 'TaskInterface.Pausing'


def test_paused_transfer_task_uses_paused_result_state():
    manager = TransferTaskService()
    task = manager.create(
        TransferDirection.DOWNLOAD,
        'movie.mp4',
        '/movie.mp4',
        '/tmp/movie.mp4',
        100,
    )
    manager.start(task)
    manager.pauseTask(task)
    manager.fail(task, RuntimeError('transfer cancelled'))

    assert task.is_paused_result
    assert not task.is_cancelled_result
    assert task.error_key == 'TaskInterface.Paused'


def test_cancelled_transfer_task_logs_cancelled_not_failed(monkeypatch):
    manager = TransferTaskService()
    task = manager.create(
        TransferDirection.DOWNLOAD,
        'movie.mp4',
        '/movie.mp4',
        '/tmp/movie.mp4',
        100,
    )
    failed = []
    cancelled = []
    monkeypatch.setattr(
        'app.service.transfer_task_service.logFailed',
        lambda *args, **kwargs: failed.append(args),
    )
    monkeypatch.setattr(
        'app.service.transfer_task_service.logCancelled',
        lambda *args, **kwargs: cancelled.append(args),
    )

    manager.fail(task, RuntimeError('transfer cancelled'))

    assert task.is_cancelled_result
    assert failed == []
    assert cancelled[0][0] == 'Log.Action.Task'
