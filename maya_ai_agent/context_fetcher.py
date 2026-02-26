# -*- coding: utf-8 -*-
"""
Context Fetcher - Gathers current Maya scene state for LLM context injection.

IMPORTANT: All functions in this module MUST be called from the MAIN THREAD
because maya.cmds is not thread-safe.
"""

import maya.cmds as cmds


def get_selection_info():
    """
    Get detailed information about currently selected objects.

    Returns:
        dict with keys:
            - count (int): number of selected objects
            - objects (list[dict]): per-object info (name, type, full_path)
    """
    sel = cmds.ls(selection=True, long=True) or []
    objects = []
    for obj in sel[:50]:  # Cap at 50 to avoid huge prompts
        short_name = obj.rsplit("|", 1)[-1]
        node_type = cmds.nodeType(obj)
        # For transforms, also report shape type
        shapes = cmds.listRelatives(obj, shapes=True, fullPath=True) or []
        shape_type = cmds.nodeType(shapes[0]) if shapes else None
        info = {
            "name": short_name,
            "full_path": obj,
            "node_type": node_type,
        }
        if shape_type and shape_type != node_type:
            info["shape_type"] = shape_type
        objects.append(info)

    return {"count": len(sel), "objects": objects}


def get_timeline_info():
    """
    Get current timeline / playback state.

    Returns:
        dict with keys:
            - current_frame (float)
            - start_frame (float): playback range start
            - end_frame (float): playback range end
            - anim_start (float): animation range start
            - anim_end (float): animation range end
            - fps (float): frames per second
            - time_unit (str): e.g. "ntsc", "film", "pal"
    """
    time_unit = cmds.currentUnit(query=True, time=True)

    fps_map = {
        "game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0,
        "show": 48.0, "palf": 50.0, "ntscf": 60.0,
        "23.976fps": 23.976, "29.97fps": 29.97, "29.97df": 29.97,
        "47.952fps": 47.952, "59.94fps": 59.94, "44100fps": 44100.0,
        "48000fps": 48000.0,
    }
    fps = fps_map.get(time_unit, 24.0)

    return {
        "current_frame": cmds.currentTime(query=True),
        "start_frame": cmds.playbackOptions(query=True, minTime=True),
        "end_frame": cmds.playbackOptions(query=True, maxTime=True),
        "anim_start": cmds.playbackOptions(query=True, animationStartTime=True),
        "anim_end": cmds.playbackOptions(query=True, animationEndTime=True),
        "fps": fps,
        "time_unit": time_unit,
    }


def get_scene_info():
    """
    Get general scene information.

    Returns:
        dict with keys:
            - scene_name (str): current file name or "untitled"
            - modified (bool): unsaved changes exist
            - up_axis (str): "y" or "z"
            - linear_unit (str): "cm", "m", etc.
    """
    scene_name = cmds.file(query=True, sceneName=True, shortName=True) or "untitled"
    return {
        "scene_name": scene_name,
        "modified": cmds.file(query=True, modified=True),
        "up_axis": cmds.upAxis(query=True, axis=True),
        "linear_unit": cmds.currentUnit(query=True, linear=True),
    }


def get_scene_stats():
    """
    Get quick scene statistics.

    Returns:
        dict with keys:
            - total_dag_nodes (int)
            - total_transforms (int)
            - total_meshes (int)
            - total_joints (int)
            - total_cameras (int)
            - total_lights (int)
            - total_curves (int)
    """
    return {
        "total_dag_nodes": len(cmds.ls(dag=True) or []),
        "total_transforms": len(cmds.ls(type="transform") or []),
        "total_meshes": len(cmds.ls(type="mesh") or []),
        "total_joints": len(cmds.ls(type="joint") or []),
        "total_cameras": len(cmds.ls(type="camera") or []),
        "total_lights": len(cmds.ls(lights=True) or []),
        "total_curves": len(cmds.ls(type="nurbsCurve") or []),
    }


def fetch_full_context():
    """
    Collect all context data and format as a readable string
    for injection into the LLM system prompt.

    Returns:
        str: Formatted context block.
    """
    scene = get_scene_info()
    timeline = get_timeline_info()
    selection = get_selection_info()
    stats = get_scene_stats()

    lines = []
    lines.append("=== Maya 场景状态 ===")

    # Scene info
    lines.append("[场景信息]")
    lines.append("  文件名: {}".format(scene["scene_name"]))
    lines.append("  未保存修改: {}".format("是" if scene["modified"] else "否"))
    lines.append("  上轴: {}".format(scene["up_axis"].upper()))
    lines.append("  线性单位: {}".format(scene["linear_unit"]))

    # Stats
    lines.append("[场景统计]")
    lines.append("  DAG 节点: {}  |  变换节点: {}  |  网格: {}".format(
        stats["total_dag_nodes"], stats["total_transforms"], stats["total_meshes"]))
    lines.append("  骨骼: {}  |  摄像机: {}  |  灯光: {}  |  曲线: {}".format(
        stats["total_joints"], stats["total_cameras"], stats["total_lights"],
        stats["total_curves"]))

    # Timeline
    lines.append("[时间轴]")
    lines.append("  当前帧: {}  |  播放范围: {} - {}  |  FPS: {} ({})".format(
        timeline["current_frame"],
        timeline["start_frame"], timeline["end_frame"],
        timeline["fps"], timeline["time_unit"]))

    # Selection
    lines.append("[当前选择] ({} 个对象)".format(selection["count"]))
    if selection["objects"]:
        for obj in selection["objects"][:20]:  # Show max 20 in prompt
            shape_info = " (shape: {})".format(obj["shape_type"]) if obj.get("shape_type") else ""
            lines.append("  - {} [{}{}]".format(
                obj["full_path"], obj["node_type"], shape_info))
        if selection["count"] > 20:
            lines.append("  ... 以及另外 {} 个对象".format(selection["count"] - 20))
    else:
        lines.append("  (无选择)")

    return "\n".join(lines)
