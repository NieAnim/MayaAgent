# -*- coding: utf-8 -*-
"""
Main entry point for Maya AI Agent.
Provides launch() function to create a dockable chat window in Maya.
"""

import maya.cmds as cmds
import maya.OpenMayaUI as omui

from .qt_compat import QtWidgets, PYSIDE_VERSION

if PYSIDE_VERSION == 6:
    from shiboken6 import wrapInstance
else:
    from shiboken2 import wrapInstance

from .chat_widget import ChatWidget


# Module-level reference to keep the widget alive
_agent_widget = None

WORKSPACE_CONTROL_NAME = "MayaAIAgentWorkspaceControl"
WINDOW_TITLE = "Maya AI Agent"


def get_maya_main_window():
    """Get the Maya main window as a QWidget."""
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr is not None:
        return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)
    return None


def _delete_existing():
    """Delete existing workspace control if it exists."""
    if cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
        cmds.deleteUI(WORKSPACE_CONTROL_NAME, control=True)


def launch():
    """
    Launch the Maya AI Agent dockable window.
    Call this from Maya's script editor or shelf button:

        from maya_ai_agent.main import launch
        launch()

    If the panel already exists, it will be raised/shown instead of recreated.
    """
    global _agent_widget

    # If workspace control already exists, just make it visible and return
    if cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
        # Check if our widget is still alive
        if _agent_widget is not None:
            try:
                _agent_widget.objectName()  # Test if C++ object is alive
                cmds.workspaceControl(WORKSPACE_CONTROL_NAME, e=True, visible=True)
                cmds.workspaceControl(WORKSPACE_CONTROL_NAME, e=True, restore=True)
                return
            except RuntimeError:
                # C++ object was deleted, need to recreate
                _agent_widget = None
        # Widget is gone but control exists — delete and recreate
        _delete_existing()

    # Create the workspace control (dockable panel)
    cmds.workspaceControl(
        WORKSPACE_CONTROL_NAME,
        label=WINDOW_TITLE,
        tabToControl=("AttributeEditor", -1),  # Dock next to Attribute Editor
        initialWidth=420,
        minimumWidth=320,
        initialHeight=600,
        retain=False,
        floating=True,
        uiScript="from maya_ai_agent.main import _restore_ui; _restore_ui()",
    )

    # Build and parent the widget
    # Note: uiScript may also call _restore_ui(), but _restore_ui() has a guard
    _restore_ui()


def _restore_ui():
    """
    Internal callback used by workspaceControl's uiScript
    to restore the widget when Maya re-opens the panel.
    Guards against duplicate creation.
    """
    global _agent_widget

    # Guard: if widget already exists and is alive, skip
    if _agent_widget is not None:
        try:
            _agent_widget.objectName()  # Test if C++ object is alive
            return  # Already created, skip
        except RuntimeError:
            _agent_widget = None

    # Get the workspace control's Qt parent
    control_ptr = omui.MQtUtil.findControl(WORKSPACE_CONTROL_NAME)
    if control_ptr is None:
        return

    control_widget = wrapInstance(int(control_ptr), QtWidgets.QWidget)

    # Create new chat widget
    _agent_widget = ChatWidget(parent=control_widget)

    # Add to the workspace control's layout
    layout = control_widget.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(control_widget)
        layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(_agent_widget)
