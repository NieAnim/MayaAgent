# -*- coding: utf-8 -*-
"""
Vision Tool - Allows the AI to capture and analyze the Maya viewport.

When the AI calls this tool, it captures the current viewport as a screenshot.
The image is then attached to the next LLM request as a vision message,
enabling the AI to "see" the Maya scene and provide visual analysis.

Enhanced with scene metadata collection to help cross-validate visual
observations against actual scene data, reducing hallucination.
"""

import traceback
from ..tool_registry import tool
from ..viewport_capture import capture_viewport
from ..logger import log


# Module-level storage for the latest captured image.
# This is read by prompt_builder to inject into the next LLM request.
_pending_viewport_image = None

# Module-level storage for scene metadata collected at capture time.
# This is injected alongside the image to help the LLM cross-validate.
_pending_scene_metadata = None


def get_pending_image():
    """Retrieve and clear the pending viewport image.

    Returns:
        str or None: base64-encoded PNG data URI, or None if no image pending.
    """
    global _pending_viewport_image
    img = _pending_viewport_image
    _pending_viewport_image = None
    return img


def get_pending_scene_metadata():
    """Retrieve and clear the pending scene metadata.

    Returns:
        str or None: Formatted scene metadata text, or None.
    """
    global _pending_scene_metadata
    meta = _pending_scene_metadata
    _pending_scene_metadata = None
    return meta


def has_pending_image():
    """Check if there is a pending viewport image."""
    return _pending_viewport_image is not None


def _analyze_body_completeness(cmds):
    """Analyze whether a human body mesh has head, hands, feet, etc.

    Uses vertex position sampling and bounding box analysis to determine
    which body parts actually have geometry.

    Returns:
        list[str]: Lines of analysis results with definitive conclusions.
    """
    lines = []
    all_meshes = cmds.ls(type="mesh", long=True) or []

    for mesh in all_meshes:
        try:
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            if not transform:
                continue
            transform = transform[0]
            vis = cmds.getAttr("{}.visibility".format(transform))
            intermediate = cmds.getAttr("{}.intermediateObject".format(mesh))
            if not vis or intermediate:
                continue

            short_name = transform.rsplit("|", 1)[-1]
            name_lower = short_name.lower()

            # Only analyze meshes that look like body/character meshes
            is_body_mesh = any(kw in name_lower for kw in [
                "body", "character", "human", "avatar", "figure",
                "skm_", "sk_", "mesh"
            ])
            if not is_body_mesh:
                continue

            bb = cmds.exactWorldBoundingBox(transform)
            # bb = [xmin, ymin, zmin, xmax, ymax, zmax]
            bb_height = bb[4] - bb[1]
            bb_ymax = bb[4]
            bb_ymin = bb[1]

            # Only analyze if it looks like a human-scale mesh (height > 50 units)
            if bb_height < 50:
                continue

            lines.append("[身体完整性分析] 网格: {}".format(short_name))
            lines.append("  包围盒高度: {:.1f}  Y范围: [{:.1f}, {:.1f}]".format(
                bb_height, bb_ymin, bb_ymax))

            # Sample vertices to check which body regions have geometry
            num_verts = cmds.polyEvaluate(transform, vertex=True)
            if not num_verts or num_verts == 0:
                lines.append("  结论: 网格没有顶点")
                continue

            # Sample up to 2000 vertices for efficiency
            sample_step = max(1, num_verts // 2000)
            sample_indices = range(0, num_verts, sample_step)

            # Define body region thresholds based on bounding box proportions
            # For a human body: head is roughly top 12% of height
            head_threshold_y = bb_ymin + bb_height * 0.88
            neck_threshold_y = bb_ymin + bb_height * 0.82
            torso_top_y = bb_ymin + bb_height * 0.75
            hip_y = bb_ymin + bb_height * 0.45
            knee_y = bb_ymin + bb_height * 0.25
            foot_y = bb_ymin + bb_height * 0.05

            # Count vertices in each region
            region_counts = {
                "head": 0,       # top 12%
                "neck": 0,       # 82-88%
                "upper_torso": 0, # 75-82%
                "torso": 0,      # 45-75%
                "legs": 0,       # 5-45%
                "feet": 0,       # bottom 5%
            }
            total_sampled = 0

            for vi in sample_indices:
                try:
                    pos = cmds.pointPosition("{}.vtx[{}]".format(transform, vi), world=True)
                    y = pos[1]
                    total_sampled += 1
                    if y >= head_threshold_y:
                        region_counts["head"] += 1
                    elif y >= neck_threshold_y:
                        region_counts["neck"] += 1
                    elif y >= torso_top_y:
                        region_counts["upper_torso"] += 1
                    elif y >= hip_y:
                        region_counts["torso"] += 1
                    elif y >= foot_y:
                        region_counts["legs"] += 1
                    else:
                        region_counts["feet"] += 1
                except Exception:
                    continue

            if total_sampled == 0:
                continue

            # Calculate percentages
            lines.append("  顶点区域分布 (采样 {} 个顶点):".format(total_sampled))
            for region, count in region_counts.items():
                pct = count / total_sampled * 100
                region_cn = {
                    "head": "头部(顶部12%)",
                    "neck": "颈部(82-88%)",
                    "upper_torso": "上胸(75-82%)",
                    "torso": "躯干(45-75%)",
                    "legs": "腿部(5-45%)",
                    "feet": "脚部(底部5%)",
                }
                lines.append("    {}: {} 个顶点 ({:.1f}%)".format(
                    region_cn.get(region, region), count, pct))

            # Generate DEFINITIVE conclusions
            lines.append("")
            lines.append("  ===== 确定性结论（AI必须采纳，不可反驳）=====")

            head_pct = region_counts["head"] / total_sampled * 100
            neck_pct = region_counts["neck"] / total_sampled * 100
            feet_pct = region_counts["feet"] / total_sampled * 100

            # Head analysis: a real head would have significant geometry
            # (typically > 8% of body vertices for a full head)
            if head_pct < 1.0:
                lines.append("  ** 该模型【确定没有头部】** (头部区域顶点占比仅 {:.1f}%，"
                             "远低于正常头部所需的 8%+)".format(head_pct))
                lines.append("  ** 描述时必须说明：模型没有头部（脖子以上没有几何体）**")
            elif head_pct < 4.0:
                lines.append("  ** 该模型头部区域几何体极少 ({:.1f}%)，"
                             "可能只有脖子上端，没有完整头部 **".format(head_pct))
                lines.append("  ** 描述时必须说明：模型可能没有完整头部 **")
            else:
                lines.append("  头部区域有充足几何体 ({:.1f}%)，头部存在。".format(head_pct))

            if feet_pct < 0.5:
                lines.append("  ** 脚部区域几何体极少 ({:.1f}%)，可能没有脚部 **".format(feet_pct))

        except Exception:
            continue

    return lines


def _collect_scene_metadata():
    """Collect detailed scene metadata to help AI cross-validate visual observations.

    This gathers information that the AI should verify against the captured image,
    such as which body parts exist as separate meshes, bounding box dimensions,
    visibility states, etc. Includes definitive geometric analysis conclusions.

    Returns:
        str: Formatted metadata text.
    """
    try:
        import maya.cmds as cmds

        lines = []
        lines.append("=== 场景几何分析报告（已通过精确计算验证，AI必须采纳这些结论）===")

        # Viewport display info
        try:
            panel = cmds.getPanel(withFocus=True)
            if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
                display_mode = cmds.modelEditor(panel, query=True, displayAppearance=True)
                wireframe_on = cmds.modelEditor(panel, query=True, wireframeOnShaded=True)
                xray = cmds.modelEditor(panel, query=True, xray=True)
                show_joints = cmds.modelEditor(panel, query=True, joints=True)
                show_nurbs_curves = cmds.modelEditor(panel, query=True, nurbsCurves=True)
                lines.append("[视口显示模式]")
                lines.append("  显示模式: {}".format(display_mode))
                lines.append("  线框叠加: {}".format("是" if wireframe_on else "否"))
                lines.append("  X光模式: {}".format("是" if xray else "否"))
                lines.append("  显示骨骼: {}".format("是" if show_joints else "否"))
                lines.append("  显示曲线: {}".format("是" if show_nurbs_curves else "否"))
        except Exception:
            pass

        # Camera info
        try:
            panel = cmds.getPanel(withFocus=True)
            if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
                camera = cmds.modelPanel(panel, query=True, camera=True)
                cam_pos = cmds.xform(camera, query=True, worldSpace=True, translation=True)
                lines.append("[摄像机]")
                lines.append("  摄像机: {}  位置: [{:.1f}, {:.1f}, {:.1f}]".format(
                    camera, cam_pos[0], cam_pos[1], cam_pos[2]))
        except Exception:
            pass

        # All visible mesh objects with detailed info
        all_meshes = cmds.ls(type="mesh", long=True) or []
        visible_meshes = []
        for mesh in all_meshes:
            try:
                transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
                if not transform:
                    continue
                transform = transform[0]
                vis = cmds.getAttr("{}.visibility".format(transform))
                intermediate = cmds.getAttr("{}.intermediateObject".format(mesh))
                if vis and not intermediate:
                    short_name = transform.rsplit("|", 1)[-1]
                    verts = cmds.polyEvaluate(transform, vertex=True)
                    faces = cmds.polyEvaluate(transform, face=True)
                    bb = cmds.exactWorldBoundingBox(transform)
                    bb_size = [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]
                    visible_meshes.append({
                        "name": short_name,
                        "vertices": verts,
                        "faces": faces,
                        "bb_min": [round(bb[0], 1), round(bb[1], 1), round(bb[2], 1)],
                        "bb_max": [round(bb[3], 1), round(bb[4], 1), round(bb[5], 1)],
                        "bb_size": [round(s, 1) for s in bb_size],
                    })
            except Exception:
                continue

        if visible_meshes:
            lines.append("[可见网格对象] (共 {} 个)".format(len(visible_meshes)))
            for m in visible_meshes[:20]:
                lines.append("  - {} (顶点:{}, 面:{})".format(
                    m["name"], m["vertices"], m["faces"]))
                lines.append("    包围盒: min={} max={} 尺寸={}".format(
                    m["bb_min"], m["bb_max"], m["bb_size"]))

        # Perform body completeness analysis
        body_analysis = _analyze_body_completeness(cmds)
        if body_analysis:
            lines.extend(body_analysis)

        # Joint/skeleton info
        all_joints = cmds.ls(type="joint") or []
        if all_joints:
            lines.append("[骨骼系统] 共 {} 个骨骼".format(len(all_joints)))
            root_joints = [j for j in all_joints if not cmds.listRelatives(j, parent=True, type="joint")]
            if root_joints:
                lines.append("  根骨骼: {}".format(", ".join(root_joints[:5])))

            # Check if head-related joints exist but no head mesh
            head_joints = [j for j in all_joints if "head" in j.lower()]
            neck_joints = [j for j in all_joints if "neck" in j.lower()]
            if head_joints or neck_joints:
                lines.append("  头部/颈部相关骨骼: {}".format(
                    ", ".join((head_joints + neck_joints)[:10])))
                lines.append("  注意: 即使存在头部骨骼，也不代表有头部网格。"
                             "骨骼是绑定结构，网格才是可见几何体。")

        # Selected objects
        sel = cmds.ls(selection=True) or []
        if sel:
            lines.append("[当前选择] {}".format(", ".join(sel[:10])))
        else:
            lines.append("[当前选择] 无")

        return "\n".join(lines)

    except Exception:
        log.warning("Failed to collect scene metadata: %s", traceback.format_exc())
        return "(场景元数据收集失败)"


@tool(
    name="capture_viewport",
    description=(
        "截取当前 Maya 视口画面，让你能够看到场景中的实际情况。"
        "截图后你会在下一条消息中收到视口画面，可以据此分析场景布局、"
        "灯光效果、模型外观、材质效果、动画姿态等。"
        "当用户要求你查看/分析/评价场景画面时，请先调用此工具。"
        "\n【重要】收到图片后你必须严格基于图片中实际可见的内容进行描述，"
        "禁止编造或推测图片中不存在的细节。对于缺失的部位（如无头、无手），"
        "必须如实报告。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "width": {
                "type": "integer",
                "description": "截图宽度(像素)，默认1280。增大可看到更多细节。",
            },
            "height": {
                "type": "integer",
                "description": "截图高度(像素)，默认720。",
            },
        },
        "required": [],
    },
)
def capture_viewport_tool(width=1280, height=720):
    """Capture the Maya viewport and store the image for the next LLM request.

    The image is NOT returned as text to the LLM directly (base64 is too long).
    Instead, it's stored in module state and injected as a vision message in
    the next prompt_builder cycle.

    Also collects scene metadata at capture time to help the LLM cross-validate
    its visual observations.

    Returns:
        dict: Success status and a brief description for the LLM.
    """
    global _pending_viewport_image
    global _pending_scene_metadata

    result = capture_viewport(width=width, height=height)

    if not result["success"]:
        _pending_scene_metadata = None
        return {
            "success": False,
            "message": "视口截图失败: {}".format(result.get("error", "unknown")),
        }

    # Store as data URI for the vision API
    _pending_viewport_image = "data:image/png;base64," + result["image_base64"]

    # Collect scene metadata for cross-validation
    _pending_scene_metadata = _collect_scene_metadata()

    # Extract key conclusions from metadata to include in tool response
    conclusions = ""
    if _pending_scene_metadata:
        meta_lines = _pending_scene_metadata.split("\n")
        conclusion_lines = [l for l in meta_lines if "确定没有" in l or "确定性结论" in l
                           or "必须说明" in l or "没有完整" in l]
        if conclusion_lines:
            conclusions = (
                "\n\n【几何分析关键结论】\n" +
                "\n".join(l.strip() for l in conclusion_lines) +
                "\n你在回答中必须采纳以上结论。"
            )

    return {
        "success": True,
        "message": (
            "已成功截取视口画面 ({}x{})。"
            "图片将在下一条消息中以视觉内容发送给你。"
            "系统已完成精确几何分析，分析报告将一并注入。"
            "你必须优先采纳几何分析的结论，不可自行推翻。{}"
        ).format(result["width"], result["height"], conclusions),
    }
