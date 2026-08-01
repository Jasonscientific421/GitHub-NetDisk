# coding: utf-8
import sys
import traceback

from PyQt5.QtWidgets import QMessageBox, QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from .translator import translate

def exception_hook(exc_type, value, exc_traceback):
    if not QApplication.instance():
        return sys.__excepthook__(exc_type, value, exc_traceback)

    d = QMessageBox()
    d.setIcon(QMessageBox.Critical)
    d.setWindowTitle(translate('ErrorMessageBox.title'))
    d.setWindowIcon(QIcon(':/app/images/logo.png'))
    d.setText(translate('ErrorMessageBox.text'))
    d.setInformativeText(f'{repr(exc_type)[8:-2]}: {value}')
    d.setDetailedText(''.join(traceback.format_exception(exc_type, value, exc_traceback)))
    d.setStandardButtons(QMessageBox.Abort | QMessageBox.Ignore)
    d.button(QMessageBox.Abort).setText(translate('ErrorMessageBox.Exit'))
    d.button(QMessageBox.Ignore).setText(translate('ErrorMessageBox.Ignore'))
    if d.exec() == QMessageBox.Abort:
        sys.__excepthook__(exc_type, value, exc_traceback)
        sys.exit(-1)
    sys.__excepthook__(exc_type, value, exc_traceback)

sys.excepthook = exception_hook
