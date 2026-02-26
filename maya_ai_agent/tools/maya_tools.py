# -*- coding: utf-8 -*-
"""
Maya Tools - Built-in tool functions for the AI Agent.

All functions here:
    - Operate on Maya scene data via maya.cmds
    - Are designed to be called from the MAIN THREAD via ActionExecutor
    - Return a result dict with "success" (bool) and "message" (str)

IMPORTANT: These functions do NOT manage undo chunks or thread safety themselves.
           That is handled by the ActionExecutor.
"""

import maya.cmds as cmds

from ..tool_registry import tool


# ---------------------------------------------------------------------------
# Tool: zero_out_transforms
# ---------------------------------------------------------------------------

@tool(
    name="zero_out_transforms",
    description=(
        "将指定物体的位移(translate)、旋转(rotate)归零，缩放(scale)设为1。"
        "常用于清零控制器。如果未指定 objects，则对当前选中的物体操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要归零的物体名称列表。如果为空或不传，则使用当前选择。",
            },
        },
        "required": [],
    },
)
def zero_out_transforms(objects=None):
    """Zero out translate/rotate, reset scale to 1."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    results = []
    for obj in objects:
        if not cmds.objExists(obj):
            results.append("{}: 不存在".format(obj))
            continue
        try:
            # Check if attributes are settable (not locked/connected)
            for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
                full_attr = "{}.{}".format(obj, attr)
                if cmds.getAttr(full_attr, settable=True):
                    cmds.setAttr(full_attr, 0)
            for attr in ["sx", "sy", "sz"]:
                full_attr = "{}.{}".format(obj, attr)
                if cmds.getAttr(full_attr, settable=True):
                    cmds.setAttr(full_attr, 1)
            results.append("{}: 已归零".format(obj.rsplit("|", 1)[-1]))
        except Exception as e:
            results.append("{}: 错误 - {}".format(obj.rsplit("|", 1)[-1], str(e)))

    return {
        "success": True,
        "message": "归零操作完成:\n" + "\n".join(results),
    }


# ---------------------------------------------------------------------------
# Tool: create_locator_at_selection
# ---------------------------------------------------------------------------

@tool(
    name="create_locator_at_selection",
    description=(
        "在当前选中物体的位置创建定位器(Locator)。"
        "如果选中了多个物体，将为每个物体各创建一个定位器。"
        "如果没有选中任何物体，将在世界原点创建一个定位器。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name_prefix": {
                "type": "string",
                "description": "定位器名称前缀，默认为 'ai_locator'。",
            },
        },
        "required": [],
    },
)
def create_locator_at_selection(name_prefix="ai_locator"):
    """Create locators at selected objects' positions."""
    sel = cmds.ls(selection=True, long=True) or []
    created = []

    if not sel:
        # Create at origin
        loc = cmds.spaceLocator(name="{}_01".format(name_prefix))[0]
        created.append(loc)
    else:
        for i, obj in enumerate(sel, 1):
            pos = cmds.xform(obj, query=True, worldSpace=True, translation=True)
            rot = cmds.xform(obj, query=True, worldSpace=True, rotation=True)
            loc = cmds.spaceLocator(
                name="{}_{:02d}".format(name_prefix, i)
            )[0]
            cmds.xform(loc, worldSpace=True, translation=pos)
            cmds.xform(loc, worldSpace=True, rotation=rot)
            created.append(loc)

    return {
        "success": True,
        "message": "已创建 {} 个定位器: {}".format(
            len(created), ", ".join(created)
        ),
    }


# ---------------------------------------------------------------------------
# Tool: set_keyframe
# ---------------------------------------------------------------------------

@tool(
    name="set_keyframe",
    description=(
        "为指定物体在指定帧上设置关键帧。"
        "如果未指定 objects，则对当前选中的物体操作。"
        "如果未指定 frame，则在当前帧设置关键帧。"
        "可以通过 attributes 参数指定要打关键帧的属性。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要设置关键帧的物体名称列表。不传则使用当前选择。",
            },
            "frame": {
                "type": "number",
                "description": "要设置关键帧的帧数。不传则使用当前帧。",
            },
            "attributes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "要设置关键帧的属性列表，如 ['translateX', 'rotateY']。"
                    "不传则对所有可 key 属性打帧。"
                ),
            },
        },
        "required": [],
    },
)
def set_keyframe(objects=None, frame=None, attributes=None):
    """Set keyframes on objects."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    kwargs = {}
    if frame is not None:
        kwargs["time"] = frame
    if attributes:
        kwargs["attribute"] = attributes

    keyed = []
    for obj in objects:
        if not cmds.objExists(obj):
            continue
        try:
            cmds.setKeyframe(obj, **kwargs)
            keyed.append(obj.rsplit("|", 1)[-1])
        except Exception as e:
            keyed.append("{}: 错误 - {}".format(obj.rsplit("|", 1)[-1], str(e)))

    frame_str = "帧 {}".format(frame) if frame is not None else "当前帧"
    attr_str = ", ".join(attributes) if attributes else "所有可 key 属性"

    return {
        "success": True,
        "message": "已在{}为 {} 个物体设置关键帧 (属性: {}):\n{}".format(
            frame_str, len(keyed), attr_str, ", ".join(keyed)
        ),
    }
