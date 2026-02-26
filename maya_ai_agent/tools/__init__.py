# -*- coding: utf-8 -*-
"""
Tools package - Auto-imports all tool modules to register them.
"""

import logging
import traceback

log = logging.getLogger("MayaAIAgent.tools")


def _safe_import(module_name):
    """Safely import a tool module, logging errors instead of crashing."""
    try:
        __import__(module_name, globals(), locals(), ["*"])
    except Exception as e:
        log.warning("Failed to import %s: %s", module_name, e)
        log.debug(traceback.format_exc())


# Import all tool modules so their @tool decorators execute and register
_safe_import("maya_ai_agent.tools.maya_tools")
_safe_import("maya_ai_agent.tools.anim_tools")
_safe_import("maya_ai_agent.tools.workflow_tools")
_safe_import("maya_ai_agent.tools.execute_code_tool")
_safe_import("maya_ai_agent.tools.rigging_tools")
_safe_import("maya_ai_agent.tools.export_tools")
_safe_import("maya_ai_agent.tools.mocap_tools")
