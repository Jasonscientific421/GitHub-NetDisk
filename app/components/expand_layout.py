# coding: utf-8
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import ExpandLayout

class ExpandLayout(ExpandLayout):

    def __init__(self, parent = None):
        super().__init__(parent)

    def removeWidget(self, widget: QWidget):
        if widget not in self.__widgets:
            return

        self.__widgets.remove(widget)
        widget.removeEventFilter(self)

    def removeItem(self, item):
        self.__items.remove(item)
