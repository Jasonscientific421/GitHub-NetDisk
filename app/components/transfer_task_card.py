# coding: utf-8
"""Visual representation of one upload or download task."""
from PyQt5.QtCore import QDateTime, QLocale, Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    IconWidget,
    ProgressBar,
    StrongBodyLabel,
    ToolButton,
    ToolTipPosition,
)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.components.material import AcrylicToolTipFilter

from ..service.transfer_task_service import (
    TransferDirection,
    TransferStatus,
    transferTaskService,
)
from ..common.event_logger import logAction, logCancelled
from ..common.signal_bus import signalBus
from ..common.translator import translate
from ..common.utils import getFileTypeIcon, showInFolder


class TransferTaskCard(CardWidget):
    """A responsive card for pending, running, completed and failed transfers."""

    def __init__(self, task, parent=None):
        super().__init__(parent=parent)
        self.task = task
        self.tr = translate
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(136)
        self.setAccessibleName(task.file_name)

        self.hBoxLayout = QHBoxLayout(self)
        self.contentLayout = QVBoxLayout()
        self.titleLayout = QHBoxLayout()
        self.metaLayout = QHBoxLayout()

        self.directionIcon = IconWidget(self)
        self.directionIcon.setFixedSize(22, 22)
        self.fileIcon = IconWidget(getFileTypeIcon(task.file_name), self)
        self.fileIcon.setFixedSize(36, 36)
        self.nameLabel = StrongBodyLabel(task.file_name, self)
        self.nameLabel.setWordWrap(False)
        self.nameLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.nameLabel.setToolTip(task.file_name)
        self.nameLabel.installEventFilter(
            AcrylicToolTipFilter(self.nameLabel, position=ToolTipPosition.TOP))
        self.directionLabel = CaptionLabel(self)
        self.repositoryLabel = CaptionLabel(self)
        self.repositoryLabel.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.repositoryLabel.installEventFilter(
            AcrylicToolTipFilter(
                self.repositoryLabel,
                position=ToolTipPosition.TOP,
            ))
        self.statusLabel = CaptionLabel(self)
        self.startTimeLabel = CaptionLabel(self)
        self.detailLabel = CaptionLabel(self)
        self.speedLabel = CaptionLabel(self)
        self.stageLabel = CaptionLabel(self)
        self.stageLabel.setTextColor('#606060', '#b8b8b8')
        self.stageLabel.setWordWrap(True)
        self.errorLabel = CaptionLabel(self)
        self.errorLabel.setTextColor('#c42b1c', '#ff99a4')
        self.errorLabel.setWordWrap(True)
        self.progressBar = ProgressBar(self, useAni=False)
        self.pauseButton = ToolButton(FIF.PAUSE, self)
        self.cancelButton = ToolButton(FIF.CANCEL_MEDIUM, self)
        self.resumeButton = ToolButton(FIF.PLAY, self)
        self.openButton = ToolButton(FIF.FOLDER, self)
        self.removeButton = ToolButton(FIF.DELETE, self)

        self.pauseButton.setToolTip(self.tr('TaskInterface.PauseTask'))
        self.pauseButton.installEventFilter(
            AcrylicToolTipFilter(self.pauseButton, position=ToolTipPosition.TOP))
        self.pauseButton.setAccessibleName(self.tr('TaskInterface.PauseTask'))
        self.cancelButton.setToolTip(self.tr('TaskInterface.CancelTask'))
        self.cancelButton.installEventFilter(
            AcrylicToolTipFilter(self.cancelButton, position=ToolTipPosition.TOP))
        self.cancelButton.setAccessibleName(self.tr('TaskInterface.CancelTask'))
        self.resumeButton.setToolTip(self.tr('TaskInterface.ResumeTask'))
        self.resumeButton.installEventFilter(
            AcrylicToolTipFilter(self.resumeButton, position=ToolTipPosition.TOP))
        self.resumeButton.setAccessibleName(self.tr('TaskInterface.ResumeTask'))
        self.openButton.setToolTip(self.tr('TaskInterface.ShowInFolder'))
        self.openButton.installEventFilter(
            AcrylicToolTipFilter(self.openButton, position=ToolTipPosition.TOP))
        self.openButton.setAccessibleName(self.tr('TaskInterface.ShowInFolder'))
        self.removeButton.setToolTip(self.tr('TaskInterface.RemoveTask'))
        self.removeButton.installEventFilter(
            AcrylicToolTipFilter(self.removeButton, position=ToolTipPosition.TOP))
        self.removeButton.setAccessibleName(self.tr('TaskInterface.RemoveTask'))

        self.hBoxLayout.setContentsMargins(18, 14, 14, 14)
        self.hBoxLayout.setSpacing(12)
        self.hBoxLayout.addWidget(self.directionIcon, 0, Qt.AlignTop)
        self.hBoxLayout.addWidget(self.fileIcon, 0, Qt.AlignTop)
        self.hBoxLayout.addLayout(self.contentLayout, 1)
        self.hBoxLayout.addWidget(self.pauseButton, 0, Qt.AlignVCenter)
        self.hBoxLayout.addWidget(self.cancelButton, 0, Qt.AlignVCenter)
        self.hBoxLayout.addWidget(self.resumeButton, 0, Qt.AlignVCenter)
        self.hBoxLayout.addWidget(self.openButton, 0, Qt.AlignVCenter)
        self.hBoxLayout.addWidget(self.removeButton, 0, Qt.AlignVCenter)

        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(6)
        self.contentLayout.addWidget(self.repositoryLabel)
        self.contentLayout.addLayout(self.titleLayout)
        self.contentLayout.addLayout(self.metaLayout)
        self.contentLayout.addWidget(self.stageLabel)
        self.contentLayout.addWidget(self.progressBar)
        self.contentLayout.addWidget(self.errorLabel)

        self.titleLayout.setContentsMargins(0, 0, 0, 0)
        self.titleLayout.addWidget(self.nameLabel, 1)
        self.titleLayout.addWidget(self.statusLabel)
        self.metaLayout.setContentsMargins(0, 0, 0, 0)
        self.metaLayout.setSpacing(8)
        self.metaLayout.addWidget(self.directionLabel)
        self.metaLayout.addWidget(self.startTimeLabel)
        self.metaLayout.addWidget(self.detailLabel)
        self.metaLayout.addWidget(self.speedLabel)
        self.metaLayout.addStretch(1)

        self.cancelButton.clicked.connect(
            lambda: signalBus.cancelTaskSig.emit(self.task))
        self.pauseButton.clicked.connect(
            lambda: signalBus.pauseTaskSig.emit(self.task))
        self.resumeButton.clicked.connect(
            lambda: signalBus.resumeTaskSig.emit(self.task))
        self.openButton.clicked.connect(self.showInFolder)
        self.removeButton.clicked.connect(self.removeTask)
        self.liveUpdateTimer = QTimer(self)
        self.liveUpdateTimer.setInterval(100)
        self.liveUpdateTimer.timeout.connect(self._updateLiveDetails)
        self.updateTask(task)

    def updateTask(self, task):
        self.task = task
        direction_key = (
            'TaskInterface.Upload' if task.direction == TransferDirection.UPLOAD
            else 'TaskInterface.Download'
        )
        status_key = {
            TransferStatus.PENDING: 'TaskInterface.Pending',
            TransferStatus.RUNNING: 'TaskInterface.Running',
            TransferStatus.SUCCESS: 'TaskInterface.Success',
            TransferStatus.FAILED: 'TaskInterface.Failed',
        }[task.status]
        if task.is_cancelled_result:
            status_key = 'TaskInterface.Cancelled'
        elif task.is_paused_result:
            status_key = 'TaskInterface.Paused'
        self.directionLabel.setText(self.tr(direction_key))
        self.directionIcon.setIcon(
            FIF.UP if task.direction == TransferDirection.UPLOAD else FIF.DOWN)
        unknown = self.tr('TaskInterface.UnknownRepositoryContext')
        self.repositoryLabel.setText(
            f'{task.repository or unknown}@{task.branch or unknown}')
        self.repositoryLabel.setToolTip(self.repositoryLabel.text())
        self.statusLabel.setText(self.tr(status_key))
        start_time = '--'
        if task.started_at:
            date_time = QDateTime.fromSecsSinceEpoch(int(task.started_at.timestamp()))
            start_time = QLocale().toString(date_time, 'yyyy-MM-dd HH:mm:ss')
        self.startTimeLabel.setText(
            self.tr('TaskInterface.StartTime', (start_time,)))

        if task.total:
            current = QLocale().formattedDataSize(task.transferred)
            total = QLocale().formattedDataSize(task.total)
            self.detailLabel.setText(f'{current} / {total}')
            self.progressBar.setRange(0, 1000)
            self.progressBar.setValue(int((task.progress or 0) * 1000))
        elif task.is_active:
            self.detailLabel.setText(self.tr('TaskInterface.Calculating'))
            self.progressBar.setRange(0, 0)
        else:
            self.detailLabel.clear()
            self.progressBar.setRange(0, 1)
            self.progressBar.setValue(1 if task.status == TransferStatus.SUCCESS else 0)

        self._updateLiveDetails()
        if task.status == TransferStatus.RUNNING:
            if not self.liveUpdateTimer.isActive():
                self.liveUpdateTimer.start()
        else:
            self.liveUpdateTimer.stop()

        error = ''
        if not (task.is_cancelled_result or task.is_paused_result):
            error = self.tr(task.error_key) if task.error_key else task.error
        stage = (
            self.tr(task.stage_key, task.stage_args)
            if task.stage_key and task.is_active else ''
        )
        self.stageLabel.setText(stage)
        self.stageLabel.setVisible(bool(stage))
        self.errorLabel.setText(error)
        self.errorLabel.setVisible(bool(error))
        self.pauseButton.setVisible(task.is_active)
        self.cancelButton.setVisible(task.is_active)
        self.resumeButton.setVisible(task.can_resume)
        self.removeButton.setVisible(not task.is_active)
        path = task.source if task.direction == TransferDirection.UPLOAD else task.destination
        self.openButton.setVisible(task.status == TransferStatus.SUCCESS and bool(path))
        self.setAccessibleDescription(
            f'{self.directionLabel.text()}, {self.repositoryLabel.text()}, '
            f'{self.startTimeLabel.text()}, {self.statusLabel.text()}, '
            f'{self.stageLabel.text()}, {self.speedLabel.text()}'
        )

    def _updateLiveDetails(self):
        speed = self.task.currentSpeed()
        if self.task.status == TransferStatus.RUNNING and speed > 0:
            formatted = QLocale().formattedDataSize(int(speed))
            self.speedLabel.setText(
                self.tr('TaskInterface.Speed', (formatted,)))
        else:
            self.speedLabel.clear()

    def showInFolder(self):
        path = (
            self.task.source
            if self.task.direction == TransferDirection.UPLOAD
            else self.task.destination
        )
        if path:
            logAction('Log.Action.FileOpenLocation', path)
            showInFolder(path)
        else:
            logCancelled('Log.Action.FileOpenLocation', self.task.file_name)

    def removeTask(self):
        logAction('Log.Action.Delete', self.task.file_name)
        transferTaskService.remove(self.task.id)

