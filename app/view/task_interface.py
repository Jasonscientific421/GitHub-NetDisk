# coding: utf-8
"""Upload and download task history interface."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    ProgressBar,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SegmentedWidget,
    SubtitleLabel,
    TitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from ..common.style_sheet import StyleSheet
from ..common.event_logger import (
    logAction,
    logChanged,
    logInitialized,
    logReceived,
    logStarted,
    logSucceeded,
)
from ..service.transfer_task_service import (
    TransferDirection,
    TransferStatus,
    transferTaskService,
)
from ..common.translator import translate
from ..common.signal_bus import signalBus
from ..components.transfer_task_card import TransferTaskCard
from ..components.stacked_widget import HorizontalSlideStackedWidget


class TransferTaskView(ScrollArea):
    """Scrollable list for one group of transfer states."""

    def __init__(self, object_name, empty_text, statuses, direction=None,
                 include_paused=False, parent=None):
        super().__init__(parent=parent)
        self.statuses = tuple(statuses)
        self.direction = direction
        self.include_paused = include_paused
        self.cards = {}
        self.scrollWidget = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        self.emptyWidget = QWidget(self.scrollWidget)
        self.emptyLayout = QVBoxLayout(self.emptyWidget)
        self.emptyIcon = IconWidget(FIF.CLOUD, self.emptyWidget)
        self.emptyIcon.setFixedSize(40, 40)
        self.emptyTitle = SubtitleLabel(empty_text, self.emptyWidget)

        self.emptyLayout.setContentsMargins(0, 72, 0, 72)
        self.emptyLayout.setSpacing(12)
        self.emptyLayout.setAlignment(Qt.AlignCenter)
        self.emptyLayout.addWidget(self.emptyIcon, 0, Qt.AlignCenter)
        self.emptyLayout.addWidget(self.emptyTitle, 0, Qt.AlignCenter)

        self.vBoxLayout.setContentsMargins(0, 4, 4, 24)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.vBoxLayout.addWidget(self.emptyWidget)
        self.vBoxLayout.addStretch(1)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName(object_name)
        self.scrollWidget.setObjectName('scrollWidget')
        StyleSheet.FLUENT_INTERFACE.apply(self)

    def accepts(self, task):
        if task.is_paused_result:
            return (
                self.include_paused
                and self.direction is not None
                and task.direction == self.direction
            )
        return (
            task.status in self.statuses
            and (self.direction is None or task.direction == self.direction)
        )

    def addTask(self, task):
        if task.id in self.cards:
            self.cards[task.id].updateTask(task)
            return
        card = TransferTaskCard(task, self.scrollWidget)
        self.cards[task.id] = card
        self.vBoxLayout.insertWidget(self.vBoxLayout.count() - 1, card)
        self._sortCards()
        self._updateEmptyState()

    def updateTask(self, task):
        card = self.cards.get(task.id)
        if card:
            card.updateTask(task)

    def removeTask(self, task_id):
        card = self.cards.pop(task_id, None)
        if card:
            self.vBoxLayout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self._updateEmptyState()

    def _updateEmptyState(self):
        self.emptyWidget.setVisible(not self.cards)

    def _sortCards(self):
        cards = sorted(
            self.cards.values(),
            key=lambda card: (
                card.task.sort_time,
                card.task.created_at,
                card.task.id,
            ),
            reverse=True,
        )
        for card in cards:
            self.vBoxLayout.removeWidget(card)
        for index, card in enumerate(cards, start=1):
            self.vBoxLayout.insertWidget(index, card)


class TaskInterface(QWidget):
    """Live session history for GitHub-NetDisk uploads and downloads."""

    INITIAL_TASK_LOG_LIMIT = 5

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.setObjectName('taskInterface')
        self.vBoxLayout = QVBoxLayout(self)
        self.headerLayout = QHBoxLayout()
        self.titleLayout = QVBoxLayout()
        self.titleLabel = TitleLabel(self.tr('TaskInterface.Task'), self)
        self.summaryLabel = BodyLabel(self)
        self.addTaskButton = PrimaryPushButton(
            FIF.ADD, self.tr('AddTask.Action'), self)
        self.clearButton = PushButton(FIF.DELETE, self.tr('TaskInterface.ClearHistory'), self)
        self.pivot = SegmentedWidget(self)
        self.stackedWidget = HorizontalSlideStackedWidget(self)
        self._taskInfoBars = {}

        active_statuses = (TransferStatus.PENDING, TransferStatus.RUNNING)
        self.downloadingView = TransferTaskView(
            'downloadingTasks',
            self.tr('TaskInterface.EmptyDownloading'),
            active_statuses,
            TransferDirection.DOWNLOAD,
            True,
            self,
        )
        self.uploadingView = TransferTaskView(
            'uploadingTasks',
            self.tr('TaskInterface.EmptyUploading'),
            active_statuses,
            TransferDirection.UPLOAD,
            True,
            self,
        )
        self.completedView = TransferTaskView(
            'completedTasks',
            self.tr('TaskInterface.EmptyCompleted'),
            (TransferStatus.SUCCESS, TransferStatus.FAILED),
            None,
            False,
            self,
        )
        self.views = (self.downloadingView, self.uploadingView, self.completedView)

        self.headerLayout.addLayout(self.titleLayout, 1)
        self.headerLayout.addWidget(self.addTaskButton, 0, Qt.AlignBottom)
        self.headerLayout.addWidget(self.clearButton, 0, Qt.AlignBottom)
        self.titleLayout.addWidget(self.titleLabel)
        self.titleLayout.addWidget(self.summaryLabel)

        self.pivot.addItem('downloadingTasks', self.tr('TaskInterface.Downloading'), icon=FIF.DOWN)
        self.pivot.addItem('uploadingTasks', self.tr('TaskInterface.Uploading'), icon=FIF.UP)
        self.pivot.addItem('completedTasks', self.tr('TaskInterface.Completed'), icon=FIF.COMPLETED)
        self.pivot.setCurrentItem('downloadingTasks')
        for view in self.views:
            self.stackedWidget.addWidget(view)

        self.vBoxLayout.setContentsMargins(36, 42, 32, 24)
        self.vBoxLayout.setSpacing(14)
        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addWidget(self.pivot, 0, Qt.AlignLeft)
        self.vBoxLayout.addWidget(self.stackedWidget, 1)

        self.pivot.currentItemChanged.connect(self._onPivotChanged)
        self.clearButton.clicked.connect(self.clearHistory)
        self.addTaskButton.clicked.connect(
            lambda: signalBus.showAddTaskDialogSig.emit(None))
        transferTaskService.taskAdded.connect(self._onTaskAdded)
        transferTaskService.taskStarted.connect(self._onTaskStarted)
        transferTaskService.taskUpdated.connect(self._onTaskUpdated)
        transferTaskService.taskRemoved.connect(self._onTaskRemoved)

        initial_tasks = transferTaskService.tasks()
        for index, task in enumerate(initial_tasks):
            self._addTask(
                task,
                log_task=self.shouldLogInitialTask(index),
            )
        self._logInitialTaskOverflow(len(initial_tasks))
        self._updateSummary()
        logInitialized('Log.Action.TaskHistory')

    def clearHistory(self):
        logAction('Log.Action.TaskHistory')
        transferTaskService.clearFinished()

    def selectPreferredCategory(self):
        """Select the newest active task direction, or completed history."""
        route_key = self.preferredRouteKey(transferTaskService.tasks())

        if self.pivot.currentRouteKey() == route_key:
            self._switchToView(route_key)
            logChanged('Log.Action.TaskTab', route_key)
        else:
            self.pivot.setCurrentItem(route_key)

    @staticmethod
    def preferredRouteKey(tasks):
        active_tasks = [
            task for task in tasks
            if task.is_active or task.is_paused_result
        ]
        if active_tasks:
            newest = max(
                active_tasks,
                key=lambda task: (task.created_at, task.id),
            )
            route_key = (
                'uploadingTasks'
                if newest.direction == TransferDirection.UPLOAD
                else 'downloadingTasks'
            )
        else:
            route_key = 'completedTasks'
        return route_key

    def _onPivotChanged(self, route_key):
        logChanged('Log.Action.TaskTab', route_key)
        self._switchToView(route_key)

    def _switchToView(self, route_key):
        for view in self.views:
            if view.objectName() == route_key:
                current_index = self.stackedWidget.currentIndex()
                next_index = self.stackedWidget.indexOf(view)
                self.stackedWidget.setCurrentWidget(
                    view,
                    duration=250,
                    isBack=next_index < current_index,
                )
                return

    def _viewForTask(self, task):
        return next(view for view in self.views if view.accepts(task))

    @classmethod
    def shouldLogInitialTask(cls, index):
        return index < cls.INITIAL_TASK_LOG_LIMIT

    @classmethod
    def initialTaskLogOverflow(cls, task_count):
        return max(0, int(task_count or 0) - cls.INITIAL_TASK_LOG_LIMIT)

    def _logInitialTaskOverflow(self, task_count):
        overflow = self.initialTaskLogOverflow(task_count)
        if overflow:
            message = self.tr(
                'Log.Task.InitialTaskLogOverflow',
                (overflow,),
            )
            if message.startswith('TypeError:'):
                message = f'{overflow} more transfer tasks...'
            logReceived(
                'Log.Action.Task',
                message,
            )

    def _onTaskAdded(self, task):
        self._addTask(task)
        self._showTaskAssignedInfoBar(task)

    def _addTask(self, task, log_task=True):
        if log_task:
            logReceived('Log.Action.Task', task.file_name)
        self._viewForTask(task).addTask(task)
        self._updateSummary()

    def _onTaskUpdated(self, task):
        target = self._viewForTask(task)
        for view in self.views:
            if task.id in view.cards and view is not target:
                view.removeTask(task.id)
        target.addTask(task)
        info_bar = self._taskInfoBars.get(task.id)
        if info_bar:
            self._updateInfoBarProgress(info_bar[1], task)
        self._updateSummary()

    def _onTaskStarted(self, task):
        self._viewForTask(task)._sortCards()

    def _onTaskRemoved(self, task_id):
        logReceived('Log.Action.Delete', task_id, level='debug')
        for view in self.views:
            view.removeTask(task_id)
        self._updateSummary()

    def _showTaskAssignedInfoBar(self, task):
        direction_key = (
            'TaskInterface.Upload'
            if task.direction == TransferDirection.UPLOAD
            else 'TaskInterface.Download'
        )
        icon = (
            FIF.UP
            if task.direction == TransferDirection.UPLOAD
            else FIF.DOWN
        )
        info_bar = InfoBar(
            icon,
            self.tr(
                'TaskInterface.TransferAssigned',
                (self.tr(direction_key),),
            ),
            task.file_name,
            orient=Qt.Vertical,
            isClosable=True,
            duration=3000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
        progress_bar = ProgressBar(info_bar, useAni=False)
        progress_bar.setFixedWidth(280)
        info_bar.addWidget(progress_bar)
        self._updateInfoBarProgress(progress_bar, task)
        self._taskInfoBars[task.id] = (info_bar, progress_bar, task.file_name)
        info_bar.closedSignal.connect(
            lambda task_id=task.id: self._onTaskInfoBarClosed(task_id))
        info_bar.show()
        logStarted('Log.Action.TaskInfoBar', task.file_name)

    @staticmethod
    def _updateInfoBarProgress(progress_bar, task):
        if task.total:
            progress_bar.setRange(0, 1000)
            progress_bar.setValue(int((task.progress or 0) * 1000))
        elif task.is_active:
            progress_bar.setRange(0, 0)
        else:
            progress_bar.setRange(0, 1000)
            progress_bar.setValue(
                1000 if task.status == TransferStatus.SUCCESS else 0)

    def _onTaskInfoBarClosed(self, task_id):
        item = self._taskInfoBars.pop(task_id, None)
        if item:
            logSucceeded('Log.Action.TaskInfoBar', item[2])

    def _updateSummary(self):
        tasks = transferTaskService.tasks()
        downloading = sum(
            (task.is_active or task.is_paused_result)
            and task.direction == TransferDirection.DOWNLOAD for task in tasks)
        uploading = sum(
            (task.is_active or task.is_paused_result)
            and task.direction == TransferDirection.UPLOAD for task in tasks)
        completed = sum(
            not task.is_active and not task.is_paused_result for task in tasks)
        self.summaryLabel.setText(
            self.tr('TaskInterface.Summary', (downloading, uploading, completed)))
        self.clearButton.setEnabled(bool(completed))
