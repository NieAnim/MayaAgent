# -*- coding: utf-8 -*-
"""
Mocap Tools - Integration with ai_mocap_toolkit for motion capture data cleanup.

Provides AI-accessible wrappers for:
    - Root Motion generation
    - Finger cleanup
"""

import sys
import os

from ..tool_registry import tool


def _ensure_toolkit_path():
    """Ensure ai_mocap_toolkit is importable."""
    # The toolkit lives alongside the Maya Agent project
    toolkit_candidates = [
        os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "ai_mocap_toolkit"
        )),
    ]
    # Check if already importable
    try:
        import ai_mocap_toolkit
        return True
    except ImportError:
        pass

    # Try adding parent directories to sys.path
    for candidate in toolkit_candidates:
        parent = os.path.dirname(candidate)
        if os.path.isdir(candidate) and parent not in sys.path:
            sys.path.insert(0, parent)
            try:
                import ai_mocap_toolkit
                return True
            except ImportError:
                sys.path.remove(parent)

    return False


# ---------------------------------------------------------------------------
# Tool: generate_root_motion
# ---------------------------------------------------------------------------

@tool(
    name="generate_root_motion",
    description=(
        "为 AI 动捕数据生成 Root Motion。\n"
        "解决的问题：AI 生成的动画中 Root 骨骼通常锁在原点，位移数据堆积在 Pelvis 上，"
        "导致在 UE 中无法正确使用 Root Motion。\n"
        "此工具会自动从 Pelvis 提取水平位移(XZ)和旋转(Yaw)到 Root 骨骼。\n"
        "需要场景中存在 Root 和 Pelvis 骨骼。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "root_joint": {
                "type": "string",
                "description": "Root 骨骼名称，默认 'root'。",
            },
            "pelvis_joint": {
                "type": "string",
                "description": "Pelvis 骨骼名称，默认 'pelvis'。",
            },
            "extract_tx": {
                "type": "boolean",
                "description": "是否提取 X 轴位移。默认 true。",
            },
            "extract_tz": {
                "type": "boolean",
                "description": "是否提取 Z 轴位移。默认 true。",
            },
            "extract_ty": {
                "type": "boolean",
                "description": "是否提取 Y 轴位移（垂直）。默认 false。",
            },
            "extract_yaw": {
                "type": "boolean",
                "description": "是否提取 Yaw 旋转。默认 true。",
            },
            "smooth_iterations": {
                "type": "integer",
                "description": "曲线平滑迭代次数，0 表示不平滑。默认 0。",
            },
            "zero_start": {
                "type": "boolean",
                "description": "是否让起始帧的 Root 归零。默认 true。",
            },
        },
        "required": [],
    },
)
def generate_root_motion(root_joint="root", pelvis_joint="pelvis",
                         extract_tx=True, extract_tz=True, extract_ty=False,
                         extract_yaw=True, smooth_iterations=0, zero_start=True):
    """Generate root motion from pelvis movement."""
    import maya.cmds as cmds

    if not _ensure_toolkit_path():
        return {
            "success": False,
            "message": "ai_mocap_toolkit 未找到。请确保工具包在正确路径下。",
        }

    # Validate joints exist
    for jnt_name, label in [(root_joint, "Root"), (pelvis_joint, "Pelvis")]:
        if not cmds.objExists(jnt_name):
            return {"success": False, "message": "{} 骨骼 '{}' 不存在。".format(label, jnt_name)}

    try:
        from ai_mocap_toolkit.core.root_motion import RootMotionConfig, generate_root_motion as _gen

        config = RootMotionConfig()
        config.root_joint = root_joint
        config.pelvis_joint = pelvis_joint
        config.extract_tx = extract_tx
        config.extract_tz = extract_tz
        config.extract_ty = extract_ty
        config.extract_yaw = extract_yaw
        config.smooth_iterations = smooth_iterations
        config.zero_start = zero_start

        result = _gen(config)

        return {
            "success": True,
            "message": "Root Motion 生成完成。已从 {} 提取位移到 {}。".format(
                pelvis_joint, root_joint),
        }

    except Exception as e:
        return {"success": False, "message": "Root Motion 生成失败: {}".format(str(e))}


# ---------------------------------------------------------------------------
# Tool: cleanup_finger_animation
# ---------------------------------------------------------------------------

@tool(
    name="cleanup_finger_animation",
    description=(
        "清理 AI 动捕数据中的手指动画噪声。\n"
        "解决的问题：AI 生成的手指动画通常有严重噪声、穿插、角度异常。\n"
        "此工具会自动检测手指骨骼，按轴向分离 curl/spread/twist 分量，"
        "过滤噪声并钳制到生理角度范围内。\n"
        "支持 MetaHuman、UE Mannequin、Mixamo 等 16+ 种骨架。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "hand_side": {
                "type": "string",
                "enum": ["left", "right", "both"],
                "description": "处理哪只手: 'left', 'right', 'both'(默认)。",
            },
            "smooth_strength": {
                "type": "number",
                "description": "平滑强度 (0-1)，默认 0.5。",
            },
            "clamp_angles": {
                "type": "boolean",
                "description": "是否将角度钳制到生理范围。默认 true。",
            },
            "suppress_spread": {
                "type": "boolean",
                "description": "是否压制中末节的 spread 噪声。默认 true。",
            },
            "suppress_twist": {
                "type": "boolean",
                "description": "是否压制 twist 噪声。默认 true。",
            },
        },
        "required": [],
    },
)
def cleanup_finger_animation(hand_side="both", smooth_strength=0.5,
                             clamp_angles=True, suppress_spread=True,
                             suppress_twist=True):
    """Clean up finger animation noise from AI mocap data."""
    if not _ensure_toolkit_path():
        return {
            "success": False,
            "message": "ai_mocap_toolkit 未找到。请确保工具包在正确路径下。",
        }

    try:
        from ai_mocap_toolkit.core.finger_cleanup import FingerCleanupConfig, cleanup_fingers

        config = FingerCleanupConfig()
        config.hand_side = hand_side
        config.smooth_strength = smooth_strength
        config.clamp_angles = clamp_angles
        config.suppress_spread = suppress_spread
        config.suppress_twist = suppress_twist

        result = cleanup_fingers(config)

        return {
            "success": True,
            "message": "手指动画清理完成 (手部: {})。".format(hand_side),
        }

    except ImportError:
        return {
            "success": False,
            "message": "ai_mocap_toolkit.core.finger_cleanup 模块导入失败。请检查安装。",
        }
    except Exception as e:
        return {"success": False, "message": "手指动画清理失败: {}".format(str(e))}
