# -*- coding: utf-8 -*-
"""
Rigging Tools - Joint, skin, constraint and deformer tools for the AI Agent.

Includes:
    - Create joints
    - Skin mesh to joints (bind skin)
    - Copy skin weights
    - Create constraints (parent, point, orient, aim, pole vector)
    - Add BlendShape
    - Joint orient
"""

import maya.cmds as cmds

from ..tool_registry import tool


# ---------------------------------------------------------------------------
# Tool: create_joints
# ---------------------------------------------------------------------------

@tool(
    name="create_joints",
    description=(
        "创建骨骼链(Joint Chain)。可以指定每个骨骼的名称和世界空间位置。\n"
        "骨骼将按列表顺序建立父子链关系。\n"
        "如果指定了 parent，则第一个骨骼将成为 parent 的子级。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "joints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "骨骼名称"},
                        "position": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "世界空间位置 [x, y, z]",
                        },
                    },
                    "required": ["name"],
                },
                "description": "骨骼列表，按顺序创建父子链。",
            },
            "parent": {
                "type": "string",
                "description": "父骨骼名称。第一个骨骼将成为此骨骼的子级。",
            },
        },
        "required": ["joints"],
    },
)
def create_joints(joints=None, parent=None):
    """Create a joint chain with specified positions."""
    if not joints:
        return {"success": False, "message": "未指定骨骼列表。"}

    created = []
    errors = []

    cmds.select(clear=True)

    if parent:
        if not cmds.objExists(parent):
            return {"success": False, "message": "父骨骼 '{}' 不存在。".format(parent)}
        cmds.select(parent)

    for jnt_info in joints:
        name = jnt_info.get("name", "joint1")
        pos = jnt_info.get("position", [0, 0, 0])

        try:
            jnt = cmds.joint(name=name, position=pos)
            created.append(jnt)
        except Exception as e:
            errors.append("{}: {}".format(name, str(e)))

    cmds.select(clear=True)

    parts = []
    if created:
        parts.append("已创建 {} 个骨骼: {}".format(len(created), ", ".join(created)))
    if errors:
        parts.append("错误: {}".format("; ".join(errors)))

    return {
        "success": len(created) > 0,
        "message": "\n".join(parts) if parts else "无操作。",
    }


# ---------------------------------------------------------------------------
# Tool: bind_skin
# ---------------------------------------------------------------------------

@tool(
    name="bind_skin",
    description=(
        "将网格绑定到骨骼（Smooth Bind Skin）。\n"
        "如果未指定 mesh 和 joints，则使用当前选择（先选骨骼再选网格）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "mesh": {
                "type": "string",
                "description": "要绑定的网格名称。",
            },
            "joints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要绑定的骨骼列表。如果不指定则使用层级中的所有骨骼。",
            },
            "max_influences": {
                "type": "integer",
                "description": "每个顶点的最大影响骨骼数，默认为 4。",
            },
            "bind_method": {
                "type": "integer",
                "description": "绑定方法: 0=最近距离, 1=最近骨骼, 2=热力图。默认为 0。",
            },
        },
        "required": [],
    },
)
def bind_skin(mesh=None, joints=None, max_influences=4, bind_method=0):
    """Bind skin (smooth bind) mesh to joints."""
    if not mesh and not joints:
        sel = cmds.ls(selection=True, long=True) or []
        if len(sel) < 2:
            return {"success": False, "message": "请选择骨骼和网格，或指定 mesh 和 joints 参数。"}
        # Assume last selected is mesh, rest are joints
        mesh = sel[-1]
        joints = sel[:-1]

    if not mesh:
        return {"success": False, "message": "未指定网格。"}

    if not cmds.objExists(mesh):
        return {"success": False, "message": "网格 '{}' 不存在。".format(mesh)}

    try:
        bind_args = [mesh]
        if joints:
            bind_args = joints + [mesh]

        skin_cluster = cmds.skinCluster(
            *bind_args,
            toSelectedBones=not bool(joints),
            bindMethod=bind_method,
            skinMethod=0,
            normalizeWeights=1,
            maximumInfluences=max_influences,
            obeyMaxInfluences=True,
        )

        return {
            "success": True,
            "message": "已绑定蒙皮: {} → skinCluster: {}".format(mesh, skin_cluster[0]),
        }
    except Exception as e:
        return {"success": False, "message": "绑定蒙皮失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: copy_skin_weights
# ---------------------------------------------------------------------------

@tool(
    name="copy_skin_weights",
    description=(
        "从源网格复制蒙皮权重到目标网格。\n"
        "两个网格都必须已经绑定蒙皮(有skinCluster)。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "源网格名称（权重来源）。",
            },
            "target": {
                "type": "string",
                "description": "目标网格名称（权重目标）。",
            },
            "surface_association": {
                "type": "string",
                "description": "关联方式: 'closestPoint'(默认), 'closestComponent', 'rayCast'。",
            },
            "influence_association": {
                "type": "string",
                "description": "骨骼关联: 'closestJoint'(默认), 'name', 'label', 'oneToOne'。",
            },
        },
        "required": ["source", "target"],
    },
)
def copy_skin_weights(source="", target="", surface_association="closestPoint",
                      influence_association="closestJoint"):
    """Copy skin weights from source mesh to target mesh."""
    if not source or not target:
        return {"success": False, "message": "请指定源网格和目标网格。"}

    for name in [source, target]:
        if not cmds.objExists(name):
            return {"success": False, "message": "'{}' 不存在。".format(name)}

    def _find_skin_cluster(mesh_name):
        """Find the skinCluster node attached to a mesh."""
        history = cmds.listHistory(mesh_name, pruneDagObjects=True) or []
        clusters = cmds.ls(history, type="skinCluster") or []
        return clusters[0] if clusters else None

    src_skin = _find_skin_cluster(source)
    if not src_skin:
        return {"success": False, "message": "源网格 '{}' 没有 skinCluster。".format(source)}

    dst_skin = _find_skin_cluster(target)
    if not dst_skin:
        return {"success": False, "message": "目标网格 '{}' 没有 skinCluster。".format(target)}

    try:
        cmds.copySkinWeights(
            sourceSkin=src_skin,
            destinationSkin=dst_skin,
            noMirror=True,
            surfaceAssociation=surface_association,
            influenceAssociation=influence_association,
        )
        return {
            "success": True,
            "message": "已从 {} ({}) 复制蒙皮权重到 {} ({})。".format(
                source, src_skin, target, dst_skin),
        }
    except Exception as e:
        return {"success": False, "message": "复制蒙皮权重失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: create_constraint
# ---------------------------------------------------------------------------

@tool(
    name="create_constraint",
    description=(
        "创建约束。支持的约束类型：\n"
        "- parent: 父子约束（位移+旋转）\n"
        "- point: 点约束（仅位移）\n"
        "- orient: 方向约束（仅旋转）\n"
        "- scale: 缩放约束\n"
        "- aim: 目标约束\n"
        "- poleVector: 极向量约束（用于 IK）\n"
        "driver 驱动 target。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "constraint_type": {
                "type": "string",
                "enum": ["parent", "point", "orient", "scale", "aim", "poleVector"],
                "description": "约束类型。",
            },
            "driver": {
                "type": "string",
                "description": "驱动物体名称。",
            },
            "target": {
                "type": "string",
                "description": "目标物体名称（被约束的物体）。",
            },
            "maintain_offset": {
                "type": "boolean",
                "description": "是否保持偏移，默认 true。",
            },
        },
        "required": ["constraint_type", "driver", "target"],
    },
)
def create_constraint(constraint_type="parent", driver="", target="",
                      maintain_offset=True):
    """Create a constraint between objects."""
    if not driver or not target:
        return {"success": False, "message": "请指定驱动物体和目标物体。"}

    for name in [driver, target]:
        if not cmds.objExists(name):
            return {"success": False, "message": "'{}' 不存在。".format(name)}

    constraint_funcs = {
        "parent": cmds.parentConstraint,
        "point": cmds.pointConstraint,
        "orient": cmds.orientConstraint,
        "scale": cmds.scaleConstraint,
        "aim": cmds.aimConstraint,
        "poleVector": cmds.poleVectorConstraint,
    }

    func = constraint_funcs.get(constraint_type)
    if not func:
        return {"success": False, "message": "不支持的约束类型: {}".format(constraint_type)}

    try:
        kwargs = {"maintainOffset": maintain_offset}
        if constraint_type == "poleVector":
            kwargs = {}  # poleVector doesn't support maintainOffset

        result = func(driver, target, **kwargs)
        return {
            "success": True,
            "message": "已创建 {} 约束: {} → {} ({})".format(
                constraint_type, driver, target, result[0]),
        }
    except Exception as e:
        return {"success": False, "message": "创建约束失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: create_ik_handle
# ---------------------------------------------------------------------------

@tool(
    name="create_ik_handle",
    description=(
        "创建 IK 句柄。支持 ikRPsolver（旋转平面）和 ikSCsolver（单链）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "start_joint": {
                "type": "string",
                "description": "IK 链的起始骨骼。",
            },
            "end_joint": {
                "type": "string",
                "description": "IK 链的末端骨骼。",
            },
            "solver": {
                "type": "string",
                "enum": ["ikRPsolver", "ikSCsolver", "ikSplineSolver"],
                "description": "IK 解算器类型，默认 ikRPsolver。",
            },
            "name": {
                "type": "string",
                "description": "IK 句柄名称。",
            },
        },
        "required": ["start_joint", "end_joint"],
    },
)
def create_ik_handle(start_joint="", end_joint="", solver="ikRPsolver", name=None):
    """Create an IK handle."""
    if not start_joint or not end_joint:
        return {"success": False, "message": "请指定起始骨骼和末端骨骼。"}

    for jnt in [start_joint, end_joint]:
        if not cmds.objExists(jnt):
            return {"success": False, "message": "骨骼 '{}' 不存在。".format(jnt)}

    try:
        kwargs = {
            "startJoint": start_joint,
            "endEffector": end_joint,
            "solver": solver,
        }
        if name:
            kwargs["name"] = name

        result = cmds.ikHandle(**kwargs)
        return {
            "success": True,
            "message": "已创建 IK 句柄: {} (solver: {})".format(result[0], solver),
        }
    except Exception as e:
        return {"success": False, "message": "创建 IK 句柄失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: add_blendshape
# ---------------------------------------------------------------------------

@tool(
    name="add_blendshape",
    description=(
        "为目标网格添加 BlendShape 变形器。\n"
        "target_meshes 是形状目标列表，base_mesh 是基础网格。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "base_mesh": {
                "type": "string",
                "description": "基础网格（被变形的网格）。",
            },
            "target_meshes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "BlendShape 目标网格列表。",
            },
            "name": {
                "type": "string",
                "description": "BlendShape 变形器名称。",
            },
        },
        "required": ["base_mesh", "target_meshes"],
    },
)
def add_blendshape(base_mesh="", target_meshes=None, name=None):
    """Add BlendShape deformer to mesh."""
    if not base_mesh or not target_meshes:
        return {"success": False, "message": "请指定基础网格和目标网格列表。"}

    if not cmds.objExists(base_mesh):
        return {"success": False, "message": "基础网格 '{}' 不存在。".format(base_mesh)}

    missing = [t for t in target_meshes if not cmds.objExists(t)]
    if missing:
        return {"success": False, "message": "目标网格不存在: {}".format(", ".join(missing))}

    try:
        args = target_meshes + [base_mesh]
        kwargs = {}
        if name:
            kwargs["name"] = name

        bs_node = cmds.blendShape(*args, **kwargs)
        return {
            "success": True,
            "message": "已创建 BlendShape: {} (目标: {})".format(
                bs_node[0], ", ".join(target_meshes)),
        }
    except Exception as e:
        return {"success": False, "message": "创建 BlendShape 失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: orient_joints
# ---------------------------------------------------------------------------

@tool(
    name="orient_joints",
    description=(
        "重定向骨骼的 Joint Orient，使骨骼轴向对齐骨骼链方向。\n"
        "如果未指定 joints，则对当前选中的骨骼操作。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "joints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要重定向的骨骼名称列表。不传则使用当前选择。",
            },
            "primary_axis": {
                "type": "string",
                "enum": ["xyz", "xzy", "yxz", "yzx", "zxy", "zyx"],
                "description": "主轴方向，默认 'xyz'（X 指向子骨骼）。",
            },
            "secondary_axis": {
                "type": "string",
                "enum": ["xup", "xdown", "yup", "ydown", "zup", "zdown"],
                "description": "次轴方向，默认 'yup'。",
            },
        },
        "required": [],
    },
)
def orient_joints(joints=None, primary_axis="xyz", secondary_axis="yup"):
    """Orient joints to align with the joint chain direction."""
    if not joints:
        joints = cmds.ls(selection=True, type="joint") or []
    if not joints:
        return {"success": False, "message": "未指定骨骼，也没有选中任何骨骼。"}

    try:
        for jnt in joints:
            if not cmds.objExists(jnt):
                continue
            cmds.joint(jnt, edit=True, orientJoint=primary_axis,
                       secondaryAxisOrient=secondary_axis)

        return {
            "success": True,
            "message": "已重定向 {} 个骨骼的 Joint Orient。".format(len(joints)),
        }
    except Exception as e:
        return {"success": False, "message": "骨骼定向失败: {}".format(str(e))}
