# -*- coding: utf-8 -*-
"""
Command Shortcut - Local short-circuit interceptor for high-frequency commands.

Matches user input against a dictionary of common commands and directly invokes
the corresponding tool function, completely bypassing the LLM API call.
This provides "zero-latency" response for routine operations.

The matcher supports:
    - Exact keyword match (e.g. "清零" → zero_out_transforms)
    - Simple regex patterns for parameterized commands
    - Fuzzy alias expansion (multiple phrases map to the same tool)
"""

import re
import json
import maya.cmds as cmds

from .tool_registry import registry


# ---------------------------------------------------------------------------
# Shortcut Dictionary
# ---------------------------------------------------------------------------
# Each entry: regex_pattern → (tool_name, default_kwargs_factory)
#
# The regex_pattern is matched against the ENTIRE user input (case-insensitive).
# kwargs_factory is a callable() → dict that returns default args at match time.
# Groups captured in the regex can be used to build kwargs dynamically.

def _get_selection():
    """Get current Maya selection as a list."""
    return cmds.ls(selection=True, long=True) or []


# Shortcut definitions:  (compiled_regex, tool_name, kwargs_builder)
# kwargs_builder receives the regex match object and returns a kwargs dict.
_SHORTCUT_TABLE = []


def _register_shortcut(pattern, tool_name, kwargs_builder=None):
    """Register a shortcut pattern."""
    compiled = re.compile(pattern, re.IGNORECASE)
    if kwargs_builder is None:
        kwargs_builder = lambda m: {}
    _SHORTCUT_TABLE.append((compiled, tool_name, kwargs_builder))


# --- Zero out transforms ---
_register_shortcut(
    r"^(清零|归零|zero\s*out|reset\s*transform|把.*归零|把.*清零|"
    r"选中.*归零|选中.*清零|帮我.*归零|帮我.*清零|所有.*归零)$",
    "zero_out_transforms",
)

# --- Set keyframe (current frame) ---
_register_shortcut(
    r"^(打帧|打关键帧|set\s*key|key\s*frame|k帧|打key|打个帧|帮我打帧|"
    r"设置关键帧|设关键帧|设个帧|打一帧)$",
    "set_keyframe",
)

# --- Set keyframe at specific frame ---
def _keyframe_at_frame(m):
    frame = int(m.group("frame"))
    return {"frame": frame}

_register_shortcut(
    r"^(?:在|到)?第?\s*(?P<frame>\d+)\s*帧(?:打帧|打关键帧|设置关键帧|打key|k帧|设帧)$",
    "set_keyframe",
    _keyframe_at_frame,
)
_register_shortcut(
    r"^(?:打帧|打关键帧|设置关键帧|打key|k帧|设帧)(?:到|在)?第?\s*(?P<frame>\d+)\s*帧$",
    "set_keyframe",
    _keyframe_at_frame,
)

# --- Create locator ---
_register_shortcut(
    r"^(创建定位器|创建locator|建定位器|加定位器|放定位器|"
    r"帮我.*创建定位器|在.*位置.*定位器)$",
    "create_locator_at_selection",
)

# --- Euler filter ---
_register_shortcut(
    r"^(欧拉.*滤波|euler\s*filter|修复.*万向.*锁|清理.*旋转|"
    r"滤波|欧拉滤波|帮我.*欧拉.*滤波)$",
    "euler_filter",
)

# --- Freeze transformations ---
_register_shortcut(
    r"^(冻结变换|冻结|freeze\s*transform|freeze|冻结选中|帮我冻结)$",
    "freeze_transformations",
)

# --- Center pivot ---
_register_shortcut(
    r"^(居中轴心|居中pivot|center\s*pivot|轴心居中|居中枢轴)$",
    "center_pivot",
)

# --- Delete history ---
_register_shortcut(
    r"^(删除历史|删历史|delete\s*history|清除历史|清除构造历史|删除构造历史)$",
    "delete_history",
)

# --- QA check ---
_register_shortcut(
    r"^(qa检查|检查.*归零|检查.*清零|检查控制器|qa\s*check|"
    r"哪些.*没.*归零|哪些.*没.*清零)$",
    "qa_check_transforms",
)

# --- Delete objects ---
_register_shortcut(
    r"^(删除|delete|删除选中|删掉|删除物体)$",
    "delete_objects",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def try_shortcut(user_input):
    """
    Try to match user input against the shortcut table.

    Args:
        user_input (str): Raw user input text (already stripped).

    Returns:
        dict or None:
            If matched, returns {
                "tool_name": str,
                "kwargs": dict,
                "display_name": str,  # human-readable tool description
                "result": dict,       # tool execution result (populated after exec)
            }
            If no match, returns None.
    """
    text = user_input.strip()
    if not text:
        return None

    # Skip anything that looks like a question or long sentence
    # (shortcuts are for short imperative commands)
    if len(text) > 30:
        return None
    if text.endswith("?") or text.endswith("？"):
        return None

    for pattern, tool_name, kwargs_builder in _SHORTCUT_TABLE:
        m = pattern.match(text)
        if m:
            # Verify the tool is actually registered
            if not registry.has_tool(tool_name):
                continue

            try:
                kwargs = kwargs_builder(m)
            except Exception:
                kwargs = {}

            return {
                "tool_name": tool_name,
                "kwargs": kwargs,
                "matched_input": text,
            }

    return None


def execute_shortcut(shortcut_info):
    """
    Execute a matched shortcut directly (must be called on MAIN THREAD).

    Args:
        shortcut_info (dict): Result from try_shortcut().

    Returns:
        dict: Tool execution result with "success" and "message".
    """
    tool_name = shortcut_info["tool_name"]
    kwargs = shortcut_info["kwargs"]

    func = registry.get_func(tool_name)
    if func is None:
        return {"success": False, "message": "工具未注册: {}".format(tool_name)}

    try:
        result = func(**kwargs)
        if not isinstance(result, dict):
            result = {"success": True, "message": str(result)}
        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "message": "快捷执行出错:\n{}".format(traceback.format_exc()),
        }
