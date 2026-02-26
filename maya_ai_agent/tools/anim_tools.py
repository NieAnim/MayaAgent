# -*- coding: utf-8 -*-
"""
Animation Tools - Advanced animation workflow tools for the AI Agent.

Includes:
    - Euler Filter (gimbal lock fix)
    - Mirror Controller Pose
    - Smooth animation curves
"""

import maya.cmds as cmds
import maya.mel as mel

from ..tool_registry import tool


# ---------------------------------------------------------------------------
# Tool: euler_filter
# ---------------------------------------------------------------------------

@tool(
    name="euler_filter",
    description=(
        "对指定物体的旋转动画曲线执行欧拉角滤波(Euler Filter)，"
        "用于修复万向节死锁(Gimbal Lock)导致的旋转翻转问题。"
        "如果未指定 objects，则对当前选中的物体操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要执行欧拉角滤波的物体名称列表。不传则使用当前选择。",
            },
        },
        "required": [],
    },
)
def euler_filter(objects=None):
    """Apply Euler Filter to rotation curves of specified objects."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    filtered = []
    skipped = []
    for obj in objects:
        if not cmds.objExists(obj):
            skipped.append("{}: 不存在".format(obj))
            continue

        short = obj.rsplit("|", 1)[-1]
        # Find rotation animation curves
        rot_attrs = ["rotateX", "rotateY", "rotateZ"]
        anim_curves = []
        for attr in rot_attrs:
            full_attr = "{}.{}".format(obj, attr)
            curves = cmds.listConnections(full_attr, type="animCurve") or []
            anim_curves.extend(curves)

        if not anim_curves:
            skipped.append("{}: 无旋转动画曲线".format(short))
            continue

        # Select the curves and run euler filter
        cmds.select(anim_curves, replace=True)
        try:
            mel.eval("filterCurve")
            filtered.append(short)
        except Exception as e:
            skipped.append("{}: 错误 - {}".format(short, str(e)))

    # Restore selection
    if objects:
        existing = [o for o in objects if cmds.objExists(o)]
        if existing:
            cmds.select(existing, replace=True)

    parts = []
    if filtered:
        parts.append("已滤波: {}".format(", ".join(filtered)))
    if skipped:
        parts.append("跳过: {}".format("; ".join(skipped)))

    return {
        "success": len(filtered) > 0,
        "message": "欧拉角滤波完成。\n" + "\n".join(parts) if parts else "无操作。",
    }


# ---------------------------------------------------------------------------
# Tool: mirror_controller_pose
# ---------------------------------------------------------------------------

@tool(
    name="mirror_controller_pose",
    description=(
        "镜像控制器的 Pose。根据命名规则（如 L_ 对应 R_，_L 对应 _R，Left 对应 Right），"
        "将源侧控制器的位移和旋转值镜像到对侧控制器。"
        "如果未指定 objects，则对当前选中的物体操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要镜像的源侧控制器名称列表。不传则使用当前选择。",
            },
            "mirror_axis": {
                "type": "string",
                "enum": ["x", "y", "z"],
                "description": "镜像轴，默认为 'x'（YZ 平面镜像）。",
            },
        },
        "required": [],
    },
)
def mirror_controller_pose(objects=None, mirror_axis="x"):
    """Mirror controller pose from one side to the other."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    # Mirror naming patterns: (source_pattern, target_pattern)
    mirror_patterns = [
        ("L_", "R_"), ("R_", "L_"),
        ("_L_", "_R_"), ("_R_", "_L_"),
        ("_L", "_R"), ("_R", "_L"),
        ("Left", "Right"), ("Right", "Left"),
        ("left", "right"), ("right", "left"),
        ("_l_", "_r_"), ("_r_", "_l_"),
        ("l_", "r_"), ("r_", "l_"),
    ]

    # Axis flip mapping
    axis_map = {"x": 0, "y": 1, "z": 2}
    flip_idx = axis_map.get(mirror_axis, 0)

    mirrored = []
    skipped = []

    for obj in objects:
        if not cmds.objExists(obj):
            skipped.append("{}: 不存在".format(obj))
            continue

        short = obj.rsplit("|", 1)[-1]

        # Find the mirror target
        target = None
        for src_pat, tgt_pat in mirror_patterns:
            if src_pat in short:
                candidate = short.replace(src_pat, tgt_pat, 1)
                if cmds.objExists(candidate):
                    target = candidate
                    break

        if not target:
            skipped.append("{}: 找不到镜像目标".format(short))
            continue

        try:
            # Get source transform values
            tx = cmds.getAttr("{}.translateX".format(obj))
            ty = cmds.getAttr("{}.translateY".format(obj))
            tz = cmds.getAttr("{}.translateZ".format(obj))
            rx = cmds.getAttr("{}.rotateX".format(obj))
            ry = cmds.getAttr("{}.rotateY".format(obj))
            rz = cmds.getAttr("{}.rotateZ".format(obj))

            translate = [tx, ty, tz]
            rotate = [rx, ry, rz]

            # Flip the mirror axis for translate
            translate[flip_idx] = -translate[flip_idx]

            # Flip the non-mirror axes for rotate
            for i in range(3):
                if i != flip_idx:
                    rotate[i] = -rotate[i]

            # Apply to target (check settable)
            t_attrs = ["translateX", "translateY", "translateZ"]
            r_attrs = ["rotateX", "rotateY", "rotateZ"]

            for attr, val in zip(t_attrs, translate):
                full = "{}.{}".format(target, attr)
                if cmds.getAttr(full, settable=True):
                    cmds.setAttr(full, val)

            for attr, val in zip(r_attrs, rotate):
                full = "{}.{}".format(target, attr)
                if cmds.getAttr(full, settable=True):
                    cmds.setAttr(full, val)

            mirrored.append("{} → {}".format(short, target))
        except Exception as e:
            skipped.append("{}: 错误 - {}".format(short, str(e)))

    parts = []
    if mirrored:
        parts.append("已镜像:\n" + "\n".join(mirrored))
    if skipped:
        parts.append("跳过: {}".format("; ".join(skipped)))

    return {
        "success": len(mirrored) > 0,
        "message": "镜像 Pose 完成。\n" + "\n".join(parts) if parts else "无操作。",
    }


# ---------------------------------------------------------------------------
# Tool: smooth_animation_curves
# ---------------------------------------------------------------------------

@tool(
    name="smooth_animation_curves",
    description=(
        "对指定物体的动画曲线进行平滑处理，减少抖动和噪声。"
        "适用于动捕数据清理。如果未指定 objects，则对当前选中的物体操作。"
        "可以指定平滑的强度（迭代次数）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要平滑的物体名称列表。不传则使用当前选择。",
            },
            "iterations": {
                "type": "integer",
                "description": "平滑迭代次数，数值越大越平滑。默认为 3。",
            },
            "attributes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "要平滑的属性列表，如 ['rotateX','rotateY','rotateZ']。"
                    "不传则平滑所有旋转属性。"
                ),
            },
        },
        "required": [],
    },
)
def smooth_animation_curves(objects=None, iterations=3, attributes=None):
    """Smooth animation curves by averaging neighboring keys."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    if not attributes:
        attributes = ["rotateX", "rotateY", "rotateZ"]

    smoothed = []
    skipped = []

    for obj in objects:
        if not cmds.objExists(obj):
            skipped.append("{}: 不存在".format(obj))
            continue

        short = obj.rsplit("|", 1)[-1]
        obj_smoothed = False

        for attr in attributes:
            full_attr = "{}.{}".format(obj, attr)

            # Get all keyframe times
            keys = cmds.keyframe(full_attr, query=True, timeChange=True) or []
            if len(keys) < 3:
                continue

            values = cmds.keyframe(full_attr, query=True, valueChange=True) or []
            if len(values) != len(keys):
                continue

            # Iterative averaging (skip first/last key)
            for _ in range(iterations):
                new_values = list(values)
                for i in range(1, len(values) - 1):
                    new_values[i] = (values[i - 1] + values[i] + values[i + 1]) / 3.0
                values = new_values

            # Apply smoothed values
            for t, v in zip(keys, values):
                cmds.keyframe(full_attr, edit=True, time=(t, t), valueChange=v)

            obj_smoothed = True

        if obj_smoothed:
            smoothed.append(short)
        else:
            skipped.append("{}: 无足够关键帧".format(short))

    parts = []
    if smoothed:
        parts.append("已平滑 ({}次迭代): {}".format(iterations, ", ".join(smoothed)))
    if skipped:
        parts.append("跳过: {}".format("; ".join(skipped)))

    return {
        "success": len(smoothed) > 0,
        "message": "动画平滑完成。\n" + "\n".join(parts) if parts else "无操作。",
    }
