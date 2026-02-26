# -*- coding: utf-8 -*-
"""
Export Tools - FBX import/export and scene management tools.

Includes:
    - FBX Export
    - FBX Import
    - Export selected
"""

import os
import maya.cmds as cmds
import maya.mel as mel

from ..tool_registry import tool


def _ensure_fbx_plugin():
    """Ensure the FBX plugin is loaded."""
    if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
        try:
            cmds.loadPlugin("fbxmaya")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tool: export_fbx
# ---------------------------------------------------------------------------

@tool(
    name="export_fbx",
    description=(
        "将场景或选中物体导出为 FBX 文件。\n"
        "支持设置动画范围、是否导出动画、是否导出蒙皮等选项。\n"
        "如果 export_selected 为 true，则只导出当前选中的物体。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "导出的 FBX 文件完整路径，如 'C:/output/character.fbx'。",
            },
            "export_selected": {
                "type": "boolean",
                "description": "是否只导出选中物体。默认 true。",
            },
            "animation": {
                "type": "boolean",
                "description": "是否导出动画。默认 true。",
            },
            "start_frame": {
                "type": "number",
                "description": "动画起始帧。默认使用时间轴起始帧。",
            },
            "end_frame": {
                "type": "number",
                "description": "动画结束帧。默认使用时间轴结束帧。",
            },
            "skins": {
                "type": "boolean",
                "description": "是否导出蒙皮。默认 true。",
            },
            "blendshapes": {
                "type": "boolean",
                "description": "是否导出 BlendShape。默认 true。",
            },
            "smoothing_groups": {
                "type": "boolean",
                "description": "是否导出平滑组。默认 true。",
            },
            "input_connections": {
                "type": "boolean",
                "description": "是否包含输入连接。默认 true。",
            },
        },
        "required": ["file_path"],
    },
)
def export_fbx(file_path="", export_selected=True, animation=True,
               start_frame=None, end_frame=None, skins=True,
               blendshapes=True, smoothing_groups=True,
               input_connections=True):
    """Export scene or selection as FBX."""
    if not file_path:
        return {"success": False, "message": "请指定导出文件路径。"}

    _ensure_fbx_plugin()

    # Normalize path
    file_path = file_path.replace("\\", "/")

    # Ensure directory exists
    dir_path = os.path.dirname(file_path)
    if dir_path and not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path)
        except Exception as e:
            return {"success": False, "message": "无法创建目录: {}".format(str(e))}

    try:
        # Set FBX export options
        mel.eval('FBXExportSmoothingGroups -v {}'.format(
            "true" if smoothing_groups else "false"))
        mel.eval('FBXExportInputConnections -v {}'.format(
            "true" if input_connections else "false"))
        mel.eval('FBXExportSkins -v {}'.format(
            "true" if skins else "false"))
        mel.eval('FBXExportShapes -v {}'.format(
            "true" if blendshapes else "false"))

        if animation:
            mel.eval('FBXExportBakeComplexAnimation -v true')
            if start_frame is not None and end_frame is not None:
                mel.eval('FBXExportBakeComplexStart -v {}'.format(int(start_frame)))
                mel.eval('FBXExportBakeComplexEnd -v {}'.format(int(end_frame)))
        else:
            mel.eval('FBXExportBakeComplexAnimation -v false')

        mel.eval('FBXExportConstraints -v false')
        mel.eval('FBXExportCameras -v false')
        mel.eval('FBXExportLights -v false')

        # Export
        if export_selected:
            mel.eval('FBXExport -f "{}" -s'.format(file_path))
        else:
            mel.eval('FBXExport -f "{}"'.format(file_path))

        return {
            "success": True,
            "message": "FBX 导出成功: {}".format(file_path),
        }

    except Exception as e:
        return {"success": False, "message": "FBX 导出失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: import_fbx
# ---------------------------------------------------------------------------

@tool(
    name="import_fbx",
    description=(
        "导入 FBX 文件到当前场景。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要导入的 FBX 文件完整路径。",
            },
            "merge_mode": {
                "type": "string",
                "enum": ["add", "merge", "exmerge"],
                "description": "导入模式: add(添加), merge(合并), exmerge(互斥合并)。默认 add。",
            },
        },
        "required": ["file_path"],
    },
)
def import_fbx(file_path="", merge_mode="add"):
    """Import FBX file into the current scene."""
    if not file_path:
        return {"success": False, "message": "请指定 FBX 文件路径。"}

    file_path = file_path.replace("\\", "/")

    if not os.path.exists(file_path):
        return {"success": False, "message": "文件不存在: {}".format(file_path)}

    _ensure_fbx_plugin()

    try:
        # Count objects before import
        before = set(cmds.ls(dag=True, long=True) or [])

        mel.eval('FBXImportMode -v {}'.format(merge_mode))
        mel.eval('FBXImport -f "{}"'.format(file_path))

        # Count new objects
        after = set(cmds.ls(dag=True, long=True) or [])
        new_objects = after - before

        return {
            "success": True,
            "message": "FBX 导入成功: {} (新增 {} 个对象)".format(
                file_path, len(new_objects)),
        }

    except Exception as e:
        return {"success": False, "message": "FBX 导入失败: {}".format(str(e))}
