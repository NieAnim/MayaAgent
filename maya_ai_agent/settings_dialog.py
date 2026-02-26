# -*- coding: utf-8 -*-
"""
Settings dialog - backward compatibility wrapper.
The actual settings UI has moved to settings_widget.py (inline panel).
This module is kept so any existing imports still work.
"""

from .qt_compat import QtWidgets
from .settings_widget import SettingsWidget, PRESETS  # noqa: F401


class SettingsDialog(QtWidgets.QDialog):
    """Legacy modal dialog wrapper around SettingsWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Maya AI Agent - 设置")
        self.setMinimumWidth(540)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._widget = SettingsWidget()
        layout.addWidget(self._widget)
