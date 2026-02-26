# -*- coding: utf-8 -*-
"""
PySide compatibility layer.
Auto-detects PySide2 (Maya 2022-2024) or PySide6 (Maya 2025+).
"""

try:
    from PySide6 import QtCore, QtWidgets, QtGui
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui
    PYSIDE_VERSION = 2

# Re-export for unified access
Signal = QtCore.Signal
Slot = QtCore.Slot
QThread = QtCore.QThread
QTimer = QtCore.QTimer
Qt = QtCore.Qt
QObject = QtCore.QObject

__all__ = [
    "QtCore", "QtWidgets", "QtGui",
    "Signal", "Slot", "QThread", "QTimer", "Qt", "QObject",
    "PYSIDE_VERSION",
]
