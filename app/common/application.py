# coding:utf-8
import sys
from typing import List
from loguru import logger

from PyQt5.QtCore import QEvent, QIODevice, QSharedMemory, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication

from .config import cfg

from .signal_bus import signalBus
from .translator import JsonTranslator, JsonTranslatorManager, translate

class SingletonApplication(QApplication):
    """ Singleton application """

    messageSig = pyqtSignal(object)

    @staticmethod
    def hasRunningInstance(key: str) -> bool:
        memory = QSharedMemory(key)
        try:
            return memory.attach()
        finally:
            if memory.isAttached():
                memory.detach()

    def __init__(self, argv: List[str], key: str):
        super().__init__(argv)

        # initialize json translator
        locale = cfg.get(cfg.language)
        jsonTranslator = JsonTranslator(locale, ':/app/lang')
        JsonTranslatorManager(jsonTranslator)

        self.key = key
        self.timeout = 1000
        self.server = QLocalServer(self)

        # cleanup (only needed for unix)
        QSharedMemory(key).attach()
        self.memory = QSharedMemory(self)
        self.memory.setKey(key)

        if self.memory.attach():
            self.isRunning = True
            logger.info(translate('Log.App.AppInstance.Detected'))

            msg = " ".join(argv[1:]) if len(argv) > 1 else 'show'
            if self.sendMessage(msg):
                logger.info(translate('Log.App.AppMessage.Sent', msg))
                sys.exit()

            logger.warning(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), 'stale singleton lock'),
            ))
            self.memory.detach()
            self.isRunning = False

        self.isRunning = False
        if not self.memory.create(1):
            logger.error(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), self.memory.errorString()),
            ))
            raise RuntimeError(self.memory.errorString())

        self.server.newConnection.connect(self.__onNewConnection)
        QLocalServer.removeServer(key)
        self.server.listen(key)

    def __onNewConnection(self):
        socket = self.server.nextPendingConnection()
        if socket.waitForReadyRead(self.timeout):
            message = socket.readAll().data().decode('utf-8')
            logger.debug(translate(
                'Log.Event.Received',
                (translate('Log.Action.Application'), message),
            ))
            signalBus.appMessageSig.emit(message)
            socket.disconnectFromServer()

    def sendMessage(self, message: str):
        """ send message to another application """
        if not self.isRunning:
            return

        # connect to another application
        socket = QLocalSocket(self)
        socket.connectToServer(self.key, QIODevice.WriteOnly)
        if not socket.waitForConnected(self.timeout):
            logger.error(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), socket.errorString()),
            ))
            return False

        # send message
        socket.write(message.encode("utf-8"))
        if not socket.waitForBytesWritten(self.timeout):
            logger.error(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), socket.errorString()),
            ))
            return False

        socket.disconnectFromServer()
        return True

    def event(self, event):
        """Forward macOS URL/file-open events to the active main window."""
        if event.type() == QEvent.FileOpen:
            value = event.url().toString() if not event.url().isEmpty() else event.file()
            if value:
                signalBus.appMessageSig.emit(value)
                return True
        return super().event(event)
