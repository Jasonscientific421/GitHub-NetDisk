# coding: utf-8
"""Tooltip helpers shared by interactive and temporarily disabled controls."""
from qfluentwidgets.components.material import AcrylicToolTipFilter


class DisabledFriendlyAcrylicToolTipFilter(AcrylicToolTipFilter):
    """Allow Acrylic tooltips to explain controls while they are disabled."""

    def _canShowToolTip(self):
        parent = self.parent()
        return parent.isWidgetType() and bool(parent.toolTip())
