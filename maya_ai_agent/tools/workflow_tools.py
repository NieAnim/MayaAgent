# -*- coding: utf-8 -*-
"""
Workflow Tools - Naming, selection, QA and rigging helper tools.

Includes:
    - Batch rename by pattern
    - Smart select / filter by pattern
    - QA check (non-zeroed transforms, etc.)
    - Create controllers for joints
"""

import re
import maya.cmds as cmds

from ..tool_registry import tool


# ---------------------------------------------------------------------------
# Tool: batch_rename
# ---------------------------------------------------------------------------

@tool(
    name="batch_rename",
    description=(
        "按规则批量重命名选中的物体。支持以下模式：\n"
        "1. prefix + base + suffix + 编号: 如 'L_Arm_{index:02d}_Jnt'\n"
        "2. 查找替换: 在名称中将 search 替换为 replace\n"
        "3. 添加前缀/后缀\n"
        "如果未指定 objects，则对当前选中的物体按层级/选择顺序操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要重命名的物体名称列表。不传则使用当前选择。",
            },
            "pattern": {
                "type": "string",
                "description": (
                    "命名模板。使用 {index} 表示编号（支持 {index:02d} 格式化），"
                    "{name} 表示原名。例如: 'L_Arm_{index:02d}_Jnt'"
                ),
            },
            "search": {
                "type": "string",
                "description": "查找替换模式中要查找的字符串。",
            },
            "replace": {
                "type": "string",
                "description": "查找替换模式中的替换字符串。",
            },
            "prefix": {
                "type": "string",
                "description": "要添加的前缀。",
            },
            "suffix": {
                "type": "string",
                "description": "要添加的后缀。",
            },
            "start_index": {
                "type": "integer",
                "description": "编号起始值，默认为 1。",
            },
        },
        "required": [],
    },
)
def batch_rename(objects=None, pattern=None, search=None, replace=None,
                 prefix=None, suffix=None, start_index=1):
    """Batch rename objects by pattern, search/replace, or prefix/suffix."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    if not pattern and not search and not prefix and not suffix:
        return {
            "success": False,
            "message": "请至少指定 pattern、search/replace、prefix 或 suffix 中的一种重命名方式。",
        }

    renamed = []
    # Process from deepest path first to avoid invalidating parent paths
    objects_sorted = sorted(objects, key=lambda x: x.count("|"), reverse=True)

    for i, obj in enumerate(objects_sorted):
        if not cmds.objExists(obj):
            continue

        short = obj.rsplit("|", 1)[-1]
        new_name = short

        if pattern:
            # Template-based rename
            try:
                new_name = pattern.format(
                    index=start_index + i,
                    name=short,
                )
            except (KeyError, IndexError, ValueError) as e:
                return {
                    "success": False,
                    "message": "命名模板错误: {}".format(str(e)),
                }
        elif search is not None:
            # Search and replace
            replace_str = replace if replace is not None else ""
            new_name = short.replace(search, replace_str)
        else:
            # Prefix / Suffix
            if prefix:
                new_name = prefix + new_name
            if suffix:
                new_name = new_name + suffix

        if new_name and new_name != short:
            try:
                result_name = cmds.rename(obj, new_name)
                renamed.append("{} → {}".format(short, result_name))
            except Exception as e:
                renamed.append("{}: 错误 - {}".format(short, str(e)))
        else:
            renamed.append("{}: 名称未变".format(short))

    return {
        "success": True,
        "message": "重命名完成 ({} 个物体):\n{}".format(len(renamed), "\n".join(renamed)),
    }


# ---------------------------------------------------------------------------
# Tool: smart_select
# ---------------------------------------------------------------------------

@tool(
    name="smart_select",
    description=(
        "根据条件智能选择场景中的物体。支持：\n"
        "- 按名称模式匹配（支持通配符 * 和正则表达式）\n"
        "- 按类型过滤（mesh, joint, nurbsCurve, transform 等）\n"
        "- 按层级关系（选择某物体的所有子级）\n"
        "多个条件为 AND 关系。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name_pattern": {
                "type": "string",
                "description": (
                    "名称匹配模式。支持 Maya 通配符（如 '*_ctrl'）"
                    "或正则表达式（以 'regex:' 开头，如 'regex:.*arm.*ctrl$'）。"
                ),
            },
            "node_type": {
                "type": "string",
                "description": (
                    "要筛选的节点类型，如 'mesh', 'joint', 'nurbsCurve', "
                    "'transform', 'camera', 'light' 等。"
                ),
            },
            "parent": {
                "type": "string",
                "description": "指定父物体，只选择该物体下的所有后代。",
            },
            "add_to_selection": {
                "type": "boolean",
                "description": "是否追加到当前选择（默认 false，替换选择）。",
            },
        },
        "required": [],
    },
)
def smart_select(name_pattern=None, node_type=None, parent=None,
                 add_to_selection=False):
    """Smart selection by name pattern, type, and hierarchy."""
    # Start with all DAG objects
    kwargs = {"dag": True, "long": True}

    if node_type:
        # Handle special type aliases
        type_alias = {
            "light": None,  # handled separately
            "curve": "nurbsCurve",
            "ctrl": "nurbsCurve",
            "controller": "nurbsCurve",
        }
        actual_type = type_alias.get(node_type, node_type)

        if node_type == "light":
            candidates = cmds.ls(lights=True, long=True) or []
            # Get their transforms
            candidates = [
                (cmds.listRelatives(c, parent=True, fullPath=True) or [None])[0]
                for c in candidates
            ]
            candidates = [c for c in candidates if c]
        else:
            if actual_type in ("mesh", "nurbsCurve", "camera"):
                shapes = cmds.ls(type=actual_type, long=True) or []
                candidates = []
                for s in shapes:
                    parents = cmds.listRelatives(s, parent=True, fullPath=True) or []
                    if parents:
                        candidates.append(parents[0])
            else:
                candidates = cmds.ls(type=actual_type, long=True) or []
    else:
        candidates = cmds.ls(dag=True, long=True) or []

    # Filter by parent hierarchy
    if parent:
        if not cmds.objExists(parent):
            return {"success": False, "message": "父物体 '{}' 不存在。".format(parent)}
        parent_long = cmds.ls(parent, long=True)
        if parent_long:
            parent_path = parent_long[0]
            candidates = [c for c in candidates if c.startswith(parent_path + "|")]

    # Filter by name pattern
    if name_pattern:
        if name_pattern.startswith("regex:"):
            # Regex mode
            regex = name_pattern[6:]
            try:
                pattern_re = re.compile(regex, re.IGNORECASE)
            except re.error as e:
                return {"success": False, "message": "正则表达式错误: {}".format(str(e))}
            candidates = [
                c for c in candidates
                if pattern_re.search(c.rsplit("|", 1)[-1])
            ]
        else:
            # Maya wildcard mode — use cmds.ls with the pattern
            maya_matches = set(cmds.ls(name_pattern, long=True) or [])
            candidates = [c for c in candidates if c in maya_matches]

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    candidates = unique

    if not candidates:
        return {"success": True, "message": "没有找到匹配的物体。", "selected_count": 0}

    # Select
    if add_to_selection:
        cmds.select(candidates, add=True)
    else:
        cmds.select(candidates, replace=True)

    short_names = [c.rsplit("|", 1)[-1] for c in candidates[:30]]
    msg = "已选中 {} 个物体".format(len(candidates))
    if len(candidates) <= 30:
        msg += ":\n" + ", ".join(short_names)
    else:
        msg += " (显示前30个):\n" + ", ".join(short_names) + " ..."

    return {"success": True, "message": msg, "selected_count": len(candidates)}


# ---------------------------------------------------------------------------
# Tool: qa_check_transforms
# ---------------------------------------------------------------------------

@tool(
    name="qa_check_transforms",
    description=(
        "QA 检查：扫描场景或指定物体，找出位移/旋转没有清零或缩放不为1的控制器和变换节点。"
        "常用于检查绑定控制器是否处于默认姿态。"
        "如果未指定 objects，则扫描所有名称中包含 'ctrl' 或 'Ctrl' 的变换节点。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要检查的物体名称列表。不传则自动扫描所有控制器。",
            },
            "tolerance": {
                "type": "number",
                "description": "数值容差，小于此值视为零。默认 0.001。",
            },
            "check_translate": {
                "type": "boolean",
                "description": "是否检查位移（默认 true）。",
            },
            "check_rotate": {
                "type": "boolean",
                "description": "是否检查旋转（默认 true）。",
            },
            "check_scale": {
                "type": "boolean",
                "description": "是否检查缩放（默认 true）。",
            },
        },
        "required": [],
    },
)
def qa_check_transforms(objects=None, tolerance=0.001,
                        check_translate=True, check_rotate=True,
                        check_scale=True):
    """QA check for non-default transforms on controllers."""
    if not objects:
        # Auto-find controllers
        all_transforms = cmds.ls(type="transform", long=True) or []
        objects = [
            t for t in all_transforms
            if re.search(r'(?i)ctrl|controller|con$|_ctl$|_cc$', t.rsplit("|", 1)[-1])
        ]

    if not objects:
        return {"success": True, "message": "未找到任何控制器/变换节点需要检查。"}

    issues = []
    clean_count = 0

    for obj in objects:
        if not cmds.objExists(obj):
            continue

        short = obj.rsplit("|", 1)[-1]
        obj_issues = []

        if check_translate:
            for attr in ["translateX", "translateY", "translateZ"]:
                try:
                    val = cmds.getAttr("{}.{}".format(obj, attr))
                    if abs(val) > tolerance:
                        obj_issues.append("{} = {:.4f}".format(attr, val))
                except Exception:
                    pass

        if check_rotate:
            for attr in ["rotateX", "rotateY", "rotateZ"]:
                try:
                    val = cmds.getAttr("{}.{}".format(obj, attr))
                    if abs(val) > tolerance:
                        obj_issues.append("{} = {:.4f}".format(attr, val))
                except Exception:
                    pass

        if check_scale:
            for attr in ["scaleX", "scaleY", "scaleZ"]:
                try:
                    val = cmds.getAttr("{}.{}".format(obj, attr))
                    if abs(val - 1.0) > tolerance:
                        obj_issues.append("{} = {:.4f}".format(attr, val))
                except Exception:
                    pass

        if obj_issues:
            issues.append("  {} : {}".format(short, ", ".join(obj_issues)))
        else:
            clean_count += 1

    total = len(issues) + clean_count
    if issues:
        msg = (
            "QA 检查完成: 共 {} 个物体，{} 个有问题，{} 个正常。\n"
            "以下物体的变换未归零:\n{}"
        ).format(total, len(issues), clean_count, "\n".join(issues[:50]))
        if len(issues) > 50:
            msg += "\n... 以及另外 {} 个".format(len(issues) - 50)
    else:
        msg = "QA 检查通过！共 {} 个物体的变换均已归零。".format(total)

    return {"success": True, "message": msg}


# ---------------------------------------------------------------------------
# Tool: create_controllers_for_joints
# ---------------------------------------------------------------------------

@tool(
    name="create_controllers_for_joints",
    description=(
        "为选中的骨骼(joint)按层级创建 NURBS 圆环控制器，并自动添加 parentConstraint 约束。"
        "控制器将匹配骨骼的位置和方向。"
        "如果未指定 joints，则对当前选中的骨骼操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "joints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要创建控制器的骨骼名称列表。不传则使用当前选择。",
            },
            "ctrl_suffix": {
                "type": "string",
                "description": "控制器后缀，默认 '_ctrl'。",
            },
            "grp_suffix": {
                "type": "string",
                "description": "偏移组后缀，默认 '_grp'。",
            },
            "radius": {
                "type": "number",
                "description": "控制器圆环半径，默认 1.0。",
            },
            "color_index": {
                "type": "integer",
                "description": (
                    "控制器显示颜色索引（Maya override color index）。"
                    "常用: 6=蓝色, 13=红色, 17=黄色, 18=青色。默认 17（黄色）。"
                ),
            },
        },
        "required": [],
    },
)
def create_controllers_for_joints(joints=None, ctrl_suffix="_ctrl",
                                  grp_suffix="_grp", radius=1.0,
                                  color_index=17):
    """Create NURBS circle controllers for joints with parent constraints."""
    if not joints:
        joints = cmds.ls(selection=True, type="joint", long=True) or []
    if not joints:
        # Maybe selected transforms that are actually joints?
        sel = cmds.ls(selection=True, long=True) or []
        joints = [s for s in sel if cmds.nodeType(s) == "joint"]
    if not joints:
        return {"success": False, "message": "没有指定骨骼，也没有选中任何骨骼。"}

    created = []
    errors = []

    for jnt in joints:
        if not cmds.objExists(jnt):
            errors.append("{}: 不存在".format(jnt))
            continue

        short = jnt.rsplit("|", 1)[-1]
        # Remove 'jnt' / 'Jnt' / 'JNT' / 'joint' suffix for clean naming
        base_name = re.sub(r'(?i)_?(?:jnt|joint)$', '', short)
        if not base_name:
            base_name = short

        ctrl_name = base_name + ctrl_suffix
        grp_name = base_name + grp_suffix

        try:
            # Create NURBS circle
            ctrl = cmds.circle(
                name=ctrl_name,
                normal=[1, 0, 0],
                radius=radius,
                constructionHistory=False,
            )[0]

            # Set override color
            shape = cmds.listRelatives(ctrl, shapes=True)[0]
            cmds.setAttr("{}.overrideEnabled".format(shape), 1)
            cmds.setAttr("{}.overrideColor".format(shape), color_index)

            # Create offset group
            grp = cmds.group(ctrl, name=grp_name)

            # Match to joint transform
            pos = cmds.xform(jnt, query=True, worldSpace=True, translation=True)
            rot = cmds.xform(jnt, query=True, worldSpace=True, rotation=True)
            cmds.xform(grp, worldSpace=True, translation=pos)
            cmds.xform(grp, worldSpace=True, rotation=rot)

            # Create parent constraint
            cmds.parentConstraint(ctrl, jnt, maintainOffset=True)

            created.append("{} → {}".format(short, ctrl_name))
        except Exception as e:
            errors.append("{}: {}".format(short, str(e)))

    parts = []
    if created:
        parts.append("已创建 {} 个控制器:\n{}".format(len(created), "\n".join(created)))
    if errors:
        parts.append("错误: {}".format("; ".join(errors)))

    return {
        "success": len(created) > 0,
        "message": "\n".join(parts) if parts else "无操作。",
    }


# ---------------------------------------------------------------------------
# Tool: delete_objects
# ---------------------------------------------------------------------------

@tool(
    name="delete_objects",
    description=(
        "删除指定的物体或当前选中的物体。支持删除节点、层级、历史等。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要删除的物体名称列表。不传则删除当前选择。",
            },
            "delete_history": {
                "type": "boolean",
                "description": "是否同时删除构造历史。默认 false。",
            },
        },
        "required": [],
    },
)
def delete_objects(objects=None, delete_history=False):
    """Delete specified objects or current selection."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    deleted = []
    errors = []

    for obj in objects:
        if not cmds.objExists(obj):
            errors.append("{}: 不存在".format(obj))
            continue

        short = obj.rsplit("|", 1)[-1]
        try:
            if delete_history:
                cmds.delete(obj, constructionHistory=True)
            cmds.delete(obj)
            deleted.append(short)
        except Exception as e:
            errors.append("{}: {}".format(short, str(e)))

    parts = []
    if deleted:
        parts.append("已删除: {}".format(", ".join(deleted)))
    if errors:
        parts.append("错误: {}".format("; ".join(errors)))

    return {
        "success": len(deleted) > 0,
        "message": "\n".join(parts) if parts else "无操作。",
    }


# ---------------------------------------------------------------------------
# Tool: freeze_transformations
# ---------------------------------------------------------------------------

@tool(
    name="freeze_transformations",
    description=(
        "冻结指定物体的变换（Freeze Transformations），将当前位移/旋转/缩放烘焙为零点。"
        "如果未指定 objects，则对当前选中的物体操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要冻结变换的物体名称列表。不传则使用当前选择。",
            },
            "translate": {
                "type": "boolean",
                "description": "是否冻结位移。默认 true。",
            },
            "rotate": {
                "type": "boolean",
                "description": "是否冻结旋转。默认 true。",
            },
            "scale": {
                "type": "boolean",
                "description": "是否冻结缩放。默认 true。",
            },
        },
        "required": [],
    },
)
def freeze_transformations(objects=None, translate=True, rotate=True, scale=True):
    """Freeze transformations on objects."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    frozen = []
    errors = []

    for obj in objects:
        if not cmds.objExists(obj):
            errors.append("{}: 不存在".format(obj))
            continue

        short = obj.rsplit("|", 1)[-1]
        try:
            cmds.makeIdentity(
                obj, apply=True,
                translate=translate,
                rotate=rotate,
                scale=scale,
                normal=False,
            )
            frozen.append(short)
        except Exception as e:
            errors.append("{}: {}".format(short, str(e)))

    parts = []
    if frozen:
        parts.append("已冻结: {}".format(", ".join(frozen)))
    if errors:
        parts.append("错误: {}".format("; ".join(errors)))

    return {
        "success": len(frozen) > 0,
        "message": "冻结变换完成。\n" + "\n".join(parts) if parts else "无操作。",
    }


# ---------------------------------------------------------------------------
# Tool: center_pivot
# ---------------------------------------------------------------------------

@tool(
    name="center_pivot",
    description=(
        "将指定物体的轴心点(Pivot)居中到物体的包围盒中心。"
        "如果未指定 objects，则对当前选中的物体操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要居中轴心的物体名称列表。不传则使用当前选择。",
            },
        },
        "required": [],
    },
)
def center_pivot(objects=None):
    """Center pivot on objects."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    centered = []
    for obj in objects:
        if not cmds.objExists(obj):
            continue
        short = obj.rsplit("|", 1)[-1]
        try:
            cmds.xform(obj, centerPivots=True)
            centered.append(short)
        except Exception as e:
            centered.append("{}: 错误 - {}".format(short, str(e)))

    return {
        "success": True,
        "message": "已居中轴心: {}".format(", ".join(centered)),
    }


# ---------------------------------------------------------------------------
# Tool: delete_history
# ---------------------------------------------------------------------------

@tool(
    name="delete_history",
    description=(
        "删除指定物体的构造历史(Construction History)。"
        "如果未指定 objects，则对当前选中的物体操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要删除历史的物体名称列表。不传则使用当前选择。",
            },
        },
        "required": [],
    },
)
def delete_history(objects=None):
    """Delete construction history on objects."""
    if not objects:
        objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        return {"success": False, "message": "没有指定物体，也没有选中任何物体。"}

    cleaned = []
    for obj in objects:
        if not cmds.objExists(obj):
            continue
        short = obj.rsplit("|", 1)[-1]
        try:
            cmds.delete(obj, constructionHistory=True)
            cleaned.append(short)
        except Exception as e:
            cleaned.append("{}: 错误 - {}".format(short, str(e)))

    return {
        "success": True,
        "message": "已删除构造历史: {}".format(", ".join(cleaned)),
    }
