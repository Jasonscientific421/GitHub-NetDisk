# coding: utf-8
# Note that this file was written by DeepSeek.
from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation

from qfluentwidgets import TransitionStackedWidget


class HorizontalSlideStackedWidget(TransitionStackedWidget):
    """ StackedWidget with horizontal slide transition animation """

    def _setUpTransitionAnimation(self, nextIndex: int, duration: int, isBack: bool):
        """
        Setup the horizontal slide animation.

        Parameters
        ----------
        nextIndex : int
            Index of the target interface.
        duration : int
            Animation duration in milliseconds. If None, default values are used.
        isBack : bool
            Whether this is a backward navigation.
            - True: current interface slides right; the new interface enters from the left.
            - False: current interface slides left; the new interface enters from the right.
        """
        # Default durations
        slideInDuration = duration or 300
        slideOutDuration = 150
        fadeOutDuration = 150
        fadeInDuration = slideInDuration

        # Easing curves
        outCurve = QEasingCurve.OutCubic
        inCurve = QEasingCurve.OutCubic

        currentWidget = self.currentWidget()
        nextWidget = self.widget(nextIndex)
        offset = self.width()  # Slide distance equals the widget width

        # Animate out the current interface
        if currentWidget is not None:
            self._renderSnapshot(currentWidget, self._currentSnapshot)
            currentWidget.hide()

            # Slide out animation
            startPos = QPoint(0, 0)
            endPos = QPoint(offset if isBack else -offset, 0)
            slideOutAni = QPropertyAnimation(self._currentSnapshot, b'pos', self)
            slideOutAni.setDuration(slideOutDuration)
            slideOutAni.setStartValue(startPos)
            slideOutAni.setEndValue(endPos)
            slideOutAni.setEasingCurve(outCurve)
            self._aniGroup.addAnimation(slideOutAni)

            # Fade out animation
            fadeOutAni = QPropertyAnimation(
                self._currentSnapshot.graphicsEffect(), b'opacity', self
            )
            fadeOutAni.setDuration(fadeOutDuration)
            fadeOutAni.setStartValue(1.0)
            fadeOutAni.setEndValue(0.0)
            fadeOutAni.setEasingCurve(outCurve)
            self._aniGroup.addAnimation(fadeOutAni)

        # Animate in the next interface
        self._renderSnapshot(nextWidget, self._nextSnapshot)
        nextWidget.hide()

        # Set initial position off-screen
        startPos = QPoint(-offset if isBack else offset, 0)
        endPos = QPoint(0, 0)
        self._nextSnapshot.move(startPos)

        slideInAni = QPropertyAnimation(self._nextSnapshot, b'pos', self)
        slideInAni.setDuration(slideInDuration)
        slideInAni.setStartValue(startPos)
        slideInAni.setEndValue(endPos)
        slideInAni.setEasingCurve(inCurve)
        self._aniGroup.addAnimation(slideInAni)

        fadeInAni = QPropertyAnimation(
            self._nextSnapshot.graphicsEffect(), b'opacity', self
        )
        fadeInAni.setDuration(fadeInDuration)
        fadeInAni.setStartValue(0.0)
        fadeInAni.setEndValue(1.0)
        fadeInAni.setEasingCurve(inCurve)
        self._aniGroup.addAnimation(fadeInAni)
