# coding: utf-8
from PyQt5.QtCore import QObject, pyqtSignal


class SignalBus(QObject):
    """ Signal bus """

    appMessageSig = pyqtSignal(str)
    dirAheadChanged = pyqtSignal()
    loadFailedSig = pyqtSignal()
    userNameChanged = pyqtSignal(str)
    githubRateLimitSig = pyqtSignal(str)

    # Quick Access
    addCardToQuickAccess = pyqtSignal(str)
    quickAccessChanged = pyqtSignal()
    browseRepo = pyqtSignal(str)

    # Direct Browse
    createNewFolderSig = pyqtSignal()
    uploadFilesSig = pyqtSignal(list)
    downloadSig = pyqtSignal()
    downloadAsSig = pyqtSignal(str)
    renameSig = pyqtSignal()
    deleteSig = pyqtSignal()
    refreshSig = pyqtSignal()
    showAddTaskDialogSig = pyqtSignal(object)
    newTaskRequestedSig = pyqtSignal(object)
    resumeTaskSig = pyqtSignal(object)
    pauseTaskSig = pyqtSignal(object)
    cancelTaskSig = pyqtSignal(object)
    copyLinkSig = pyqtSignal(bool)

    # Settings
    checkUpdateSig = pyqtSignal()
    micaEnableChanged = pyqtSignal(bool)
    trayIconDisabledChanged = pyqtSignal(bool)

signalBus = SignalBus()
