# coding:utf-8
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QColor
from qfluentwidgets import BodyLabel, ThemeColor, qconfig


class ThemedRichBodyLabel(BodyLabel):
    """Rich text label whose links mirror HyperlinkLabel's themed color."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rawText = ''
        qconfig.themeChanged.connect(self.refreshLinkColor)
        qconfig.themeColorChanged.connect(self.refreshLinkColor)

    def setText(self, text: str):
        self._rawText = text
        self.refreshLinkColor()

    def refreshLinkColor(self):
        color = ThemeColor.PRIMARY.color().name(QColor.HexRgb)
        html = self._rawText.replace(
            '<a ',
            f'<a style="color: {color}; text-decoration: none;" ',
        )
        super().setText(html)

    def event(self, event):
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self.refreshLinkColor()
        return super().event(event)
