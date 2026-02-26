# -*- coding: utf-8 -*-
"""
Action Executor - Safely executes AI tool calls on the Maya main thread.

Responsibilities:
    1. Receive tool_calls from the LLM response
    2. Map function names to registered tool functions
    3. Execute via maya.utils.executeDeferred (main thread safety)
    4. Wrap every execution in cmds.undoInfo chunks
    5. Return results for the tool_calls conversation loop
"""

import json
import traceback
import maya.cmds as cmds
import maya.utils

from .qt_compat import Signal, QObject
from .tool_registry import registry


class ActionExecutor(QObject):
    """
    Executes tool calls safely on the Maya main thread.
    Emits signals with execution results.
    """

    # Signal: (tool_call_id, function_name, result_dict)
    execution_finished = Signal(str, str, str)
    # Signal: error message
    execution_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def execute_tool_calls(self, tool_calls_json):
        """
        Parse and execute a list of tool calls from the LLM.

        Args:
            tool_calls_json (str): JSON string of the tool_calls array.
        """
        try:
            tool_calls = json.loads(tool_calls_json)
        except json.JSONDecodeError as e:
            self.execution_error.emit("tool_calls JSON 解析失败: {}".format(e))
            return

        for tc in tool_calls:
            call_id = tc.get("id", "unknown")
            func_info = tc.get("function", {})
            func_name = func_info.get("name", "")
            args_str = func_info.get("arguments", "{}")

            # Parse arguments
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}

            # Validate tool exists
            if not registry.has_tool(func_name):
                result = {
                    "success": False,
                    "message": "未知工具: {}".format(func_name),
                }
                self.execution_finished.emit(
                    call_id, func_name, json.dumps(result, ensure_ascii=False)
                )
                continue

            # Execute on main thread via executeDeferred
            # We use a closure to capture the current loop variables
            self._deferred_execute(call_id, func_name, args)

    def _deferred_execute(self, call_id, func_name, args):
        """Schedule execution on Maya's main thread."""
        def _do_execute():
            self._execute_single(call_id, func_name, args)

        maya.utils.executeDeferred(_do_execute)

    def _execute_single(self, call_id, func_name, args):
        """
        Execute a single tool call with undo chunk protection.
        This runs on the MAIN THREAD.
        """
        func = registry.get_func(func_name)
        if func is None:
            result = {"success": False, "message": "工具函数未找到: {}".format(func_name)}
            self.execution_finished.emit(
                call_id, func_name, json.dumps(result, ensure_ascii=False)
            )
            return

        chunk_name = "AIAgent_{}".format(func_name)
        cmds.undoInfo(openChunk=True, chunkName=chunk_name)
        try:
            result = func(**args)
            if not isinstance(result, dict):
                result = {"success": True, "message": str(result)}
        except Exception:
            result = {
                "success": False,
                "message": "执行出错:\n{}".format(traceback.format_exc()),
            }
        finally:
            cmds.undoInfo(closeChunk=True)

        self.execution_finished.emit(
            call_id, func_name, json.dumps(result, ensure_ascii=False)
        )
