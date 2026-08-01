# coding: utf-8
"""Persistent transfer model shared by the browse and task interfaces."""
import json
from pathlib import Path
from threading import Event, RLock
from time import monotonic
from datetime import datetime
from enum import Enum
from uuid import uuid4

from PyQt5.QtCore import QObject, pyqtSignal

from ..common.event_logger import (
    exceptionDetail,
    logAction,
    logCancelled,
    logChanged,
    logFailed,
    logProgress,
    logStarted,
    logSucceeded,
)
from ..common.setting import TRANSFER_TASK_FILE
from ..common.translator import translate
from ..common.transfer_utils import isTransferCancelledError


class TransferDirection(Enum):
    DOWNLOAD = 'download'
    UPLOAD = 'upload'


class TransferStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'


class TransferTask:
    """Mutable transfer state; updates are announced by ``TransferTaskService``."""

    def __init__(self, direction, file_name, source, destination, total=0,
                 repository='', branch='', resume_data=None):
        self.id = uuid4().hex
        self.direction = direction
        self.file_name = file_name
        self.source = source
        self.destination = destination
        self.repository = str(repository or '')
        self.branch = str(branch or '')
        self.resume_data = dict(resume_data or {})
        self.total = max(0, int(total or 0))
        self.transferred = 0
        self.status = TransferStatus.PENDING
        self.error = ''
        self.error_key = ''
        self.stage_key = ''
        self.stage_args = ()
        self.created_at = datetime.now()
        self.started_at = None
        self.finished_at = None
        self.stop_reason = ''
        self._last_logged_percent = -10
        self._speed_samples = ()
        self.speed = 0.0
        self._cancel_event = Event()

    @property
    def progress(self):
        if self.total <= 0:
            return None
        return min(1.0, self.transferred / self.total)

    @property
    def is_active(self):
        return self.status in (TransferStatus.PENDING, TransferStatus.RUNNING)

    @property
    def can_resume(self):
        """Whether an interrupted transfer can be continued."""
        if self.status != TransferStatus.FAILED:
            return False
        if self.is_paused_result:
            return True
        if self.direction == TransferDirection.UPLOAD:
            return (
                bool(self.resume_data.get('releaseTag'))
                and Path(self.source).is_file()
            )
        # DOWNLOAD: can resume if the partial file still exists.
        return Path(self.destination + '.part').is_file()

    @property
    def is_cancelled(self):
        return self._cancel_event.is_set()

    @property
    def is_cancelled_result(self):
        return (
            self.status == TransferStatus.FAILED
            and self.error_key == 'TaskInterface.Cancelled'
        )

    @property
    def is_paused_result(self):
        return (
            self.status == TransferStatus.FAILED
            and self.error_key == 'TaskInterface.Paused'
        )

    def cancel(self):
        """Signal the running transfer to stop at its next opportunity."""
        self.stop_reason = 'cancelled'
        self._cancel_event.set()

    def pause(self):
        """Signal the running transfer to pause at its next opportunity."""
        self.stop_reason = 'paused'
        self._cancel_event.set()

    def resetCancel(self):
        """Clear the cancellation flag before retrying."""
        self._cancel_event.clear()
        self.stop_reason = ''

    @property
    def sort_time(self):
        """Actual start time, falling back to creation time while pending."""
        return self.started_at or self.created_at

    def resetSpeed(self, timestamp=None):
        """Reset transient speed sampling when a transfer starts or stops."""
        now = monotonic() if timestamp is None else float(timestamp)
        self._speed_samples = ((now, self.transferred),)
        self.speed = 0.0

    def recordProgress(self, transferred, timestamp=None):
        """Record a progress sample and return the smoothed bytes/second."""
        now = monotonic() if timestamp is None else float(timestamp)
        transferred = max(0, int(transferred or 0))
        samples = list(self._speed_samples)
        if samples and transferred < samples[-1][1]:
            samples = []
        samples.append((now, transferred))
        cutoff = now - 2.0
        samples = [sample for sample in samples if sample[0] >= cutoff]
        self._speed_samples = tuple(samples)
        self.speed = self.currentSpeed(now)
        return self.speed

    def currentSpeed(self, timestamp=None):
        """Return a rolling transfer rate, dropping to zero after a stall."""
        if self.status != TransferStatus.RUNNING:
            return 0.0
        samples = self._speed_samples
        if len(samples) < 2:
            return 0.0
        now = monotonic() if timestamp is None else float(timestamp)
        if now - samples[-1][0] > 1.0:
            return 0.0
        elapsed = samples[-1][0] - samples[0][0]
        if elapsed <= 0:
            return 0.0
        return max(0.0, (samples[-1][1] - samples[0][1]) / elapsed)

    @staticmethod
    def _serialize_time(value):
        return value.isoformat() if value else None

    @staticmethod
    def _deserialize_time(value):
        return datetime.fromisoformat(value) if value else None

    def to_record(self):
        return {
            'id': self.id,
            'direction': self.direction.value,
            'fileName': self.file_name,
            'source': self.source,
            'destination': self.destination,
            'repository': self.repository,
            'branch': self.branch,
            'resumeData': self.resume_data,
            'total': self.total,
            'transferred': self.transferred,
            'status': self.status.value,
            'error': self.error,
            'errorKey': self.error_key,
            'stopReason': self.stop_reason,
            'createdAt': self._serialize_time(self.created_at),
            'startedAt': self._serialize_time(self.started_at),
            'finishedAt': self._serialize_time(self.finished_at),
        }

    @classmethod
    def from_record(cls, record):
        task = cls(
            TransferDirection(record['direction']),
            str(record.get('fileName', '')),
            str(record.get('source', '')),
            str(record.get('destination', '')),
            record.get('total', 0),
            record.get('repository', ''),
            record.get('branch', ''),
            record.get('resumeData', {}),
        )
        task.id = str(record.get('id') or uuid4().hex)
        task.transferred = max(0, int(record.get('transferred', 0) or 0))
        task.status = TransferStatus(record.get('status', TransferStatus.FAILED.value))
        task.error = str(record.get('error', ''))
        task.error_key = str(record.get('errorKey', ''))
        task.stop_reason = str(record.get('stopReason', ''))
        task.created_at = cls._deserialize_time(record.get('createdAt')) or datetime.now()
        task.started_at = cls._deserialize_time(record.get('startedAt'))
        task.finished_at = cls._deserialize_time(record.get('finishedAt'))
        return task


class TransferTaskService(QObject):
    taskAdded = pyqtSignal(object)
    taskStarted = pyqtSignal(object)
    taskUpdated = pyqtSignal(object)
    taskRemoved = pyqtSignal(str)
    tasksCleared = pyqtSignal()

    def __init__(self, parent=None, storage_path=None):
        super().__init__(parent)
        self._tasks = []
        self._storage_path = Path(storage_path) if storage_path else None
        self._persist_lock = RLock()
        self._last_persist_at = 0.0
        self._load()

    @staticmethod
    def _description(task):
        direction_key = (
            'TaskInterface.Upload'
            if task.direction == TransferDirection.UPLOAD
            else 'TaskInterface.Download'
        )
        unknown = translate('TaskInterface.UnknownRepositoryContext')
        context = translate(
            'TaskInterface.RepositoryBranch',
            (task.repository or unknown, task.branch or unknown),
        )
        return f'{translate(direction_key)}: {task.file_name} ({context})'

    def tasks(self):
        return sorted(
            self._tasks,
            key=lambda task: (task.sort_time, task.created_at, task.id),
            reverse=True,
        )

    def create(self, direction, file_name, source, destination, total=0,
               repository='', branch='', resume_data=None):
        if not isinstance(direction, TransferDirection):
            direction = TransferDirection(direction)
        task = TransferTask(
            direction,
            file_name,
            source,
            destination,
            total,
            repository,
            branch,
            resume_data,
        )
        self._tasks.insert(0, task)
        logAction('Log.Action.Task', self._description(task))
        self._persist(force=True)
        self.taskAdded.emit(task)
        return task

    def start(self, task):
        first_start = task.started_at is None
        if first_start:
            task.started_at = datetime.now()
        task.status = TransferStatus.RUNNING
        task.stage_key = ''
        task.stage_args = ()
        task.resetSpeed()
        logStarted('Log.Action.Task', self._description(task))
        self._persist(force=True)
        self.taskUpdated.emit(task)
        if first_start:
            self.taskStarted.emit(task)

    def restart(self, task):
        """Restart a resumable failed transfer while keeping its identity."""
        if not task.can_resume:
            return False
        if task.direction == TransferDirection.DOWNLOAD:
            # Preserve partial-download byte count for resume progress.
            part_path = Path(task.destination + '.part')
            if part_path.is_file():
                task.transferred = part_path.stat().st_size
            else:
                task.transferred = 0
        else:
            # Upload resume progress is recalculated from completed Release assets.
            task.transferred = 0
        task.status = TransferStatus.RUNNING
        task.error = ''
        task.error_key = ''
        task.stage_key = ''
        task.stage_args = ()
        task.started_at = datetime.now()
        task.finished_at = None
        task._last_logged_percent = -10
        task.resetSpeed()
        task.resetCancel()
        logStarted('Log.Action.Task', self._description(task))
        self._persist(force=True)
        self.taskUpdated.emit(task)
        self.taskStarted.emit(task)
        return True

    def cancelTask(self, task):
        """Request cancellation of an active transfer."""
        if not task.is_active:
            return
        task.cancel()
        # Update the stage so the UI reflects the pending cancellation.
        task.stage_key = 'TaskInterface.Cancelling'
        task.stage_args = ()
        self.taskUpdated.emit(task)

    def pauseTask(self, task):
        """Request pausing of an active transfer."""
        if not task.is_active:
            return
        task.pause()
        task.stage_key = 'TaskInterface.Pausing'
        task.stage_args = ()
        self.taskUpdated.emit(task)

    def updateStage(self, task, key, args=()):
        """Update the human-readable phase shown for an active transfer."""
        if not task.is_active:
            return
        task.stage_key = str(key or '')
        task.stage_args = tuple(args or ())
        self.taskUpdated.emit(task)

    def updateProgress(self, task, transferred, total=0):
        task.transferred = max(0, int(transferred or 0))
        if total:
            task.total = max(0, int(total))
        task.status = TransferStatus.RUNNING
        task.recordProgress(task.transferred)
        if task.total:
            percent = min(100, int(task.transferred * 100 / task.total))
            bucket = (percent // 10) * 10
            if bucket > task._last_logged_percent:
                task._last_logged_percent = bucket
                logProgress(
                    'Log.Action.TaskProgress',
                    f'{self._description(task)}: {bucket}%',
                )
        self._persist()
        self.taskUpdated.emit(task)

    def finish(self, task, destination=None):
        if destination:
            task.destination = destination
        if task.total:
            task.transferred = task.total
        task.status = TransferStatus.SUCCESS
        task.speed = 0.0
        task._speed_samples = ()
        task.error = ''
        task.error_key = ''
        task.stage_key = ''
        task.stage_args = ()
        task.finished_at = datetime.now()
        logSucceeded('Log.Action.Task', self._description(task))
        self._persist(force=True)
        self.taskUpdated.emit(task)

    def fail(self, task, error):
        cancelled = isTransferCancelledError(error)
        task.status = TransferStatus.FAILED
        task.speed = 0.0
        task._speed_samples = ()
        task.error = str(error)
        task.error_key = ''
        task.stage_key = ''
        task.stage_args = ()
        task.finished_at = datetime.now()
        # Detect user-requested cancellation so the UI can offer resume.
        if cancelled:
            task.error = ''
            task.error_key = (
                'TaskInterface.Paused'
                if task.stop_reason == 'paused'
                else 'TaskInterface.Cancelled'
            )
        if cancelled:
            logCancelled('Log.Action.Task', self._description(task))
        else:
            logFailed(
                'Log.Action.Task',
                exceptionDetail(error, self._description(task)),
            )
        self._persist(force=True)
        self.taskUpdated.emit(task)

    def remove(self, task_id):
        for task in self._tasks:
            if task.id == task_id and not task.is_active:
                self._tasks.remove(task)
                logAction('Log.Action.Delete', self._description(task))
                self._persist(force=True)
                self.taskRemoved.emit(task_id)
                return True
        return False

    def clearFinished(self):
        removed = [
            task.id for task in self._tasks
            if not task.is_active and not task.is_paused_result
        ]
        self._tasks = [
            task for task in self._tasks
            if task.is_active or task.is_paused_result
        ]
        for task_id in removed:
            self.taskRemoved.emit(task_id)
        if removed:
            logAction('Log.Action.TaskHistory', str(len(removed)))
            self._persist(force=True)
            self.tasksCleared.emit()

    def save(self):
        self._persist(force=True)

    def _load(self):
        if not self._storage_path or not self._storage_path.exists():
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding='utf-8'))
            records = payload.get('tasks', []) if isinstance(payload, dict) else payload
            interrupted = False
            for record in records:
                try:
                    task = TransferTask.from_record(record)
                except (KeyError, TypeError, ValueError) as error:
                    logFailed(
                        'Log.Action.TaskPersistence',
                        exceptionDetail(error, repr(record)),
                        level='warning',
                    )
                    continue
                if task.is_active:
                    task.status = TransferStatus.FAILED
                    task.error = ''
                    task.error_key = 'TaskInterface.Interrupted'
                    task.finished_at = datetime.now()
                    interrupted = True
                self._tasks.append(task)
            if interrupted:
                self._persist(force=True)
        except Exception as error:
            logFailed('Log.Action.TaskPersistence', error)

    def _persist(self, force=False):
        if not self._storage_path:
            return
        now = monotonic()
        if not force and now - self._last_persist_at < 0.5:
            return
        with self._persist_lock:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    'version': 1,
                    'tasks': [task.to_record() for task in self.tasks()],
                }
                temp_path = self._storage_path.with_name(
                    f'{self._storage_path.name}.tmp')
                temp_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                temp_path.replace(self._storage_path)
                self._last_persist_at = now
                if force:
                    logChanged(
                        'Log.Action.TaskPersistence',
                        str(len(self._tasks)),
                        level='debug',
                    )
            except Exception as error:
                logFailed('Log.Action.TaskPersistence', error)


transferTaskService = TransferTaskService(storage_path=TRANSFER_TASK_FILE)
