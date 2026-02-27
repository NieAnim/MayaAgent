# -*- coding: utf-8 -*-
"""
Prompt Builder - Constructs LLM messages with cache-optimized structure.

Implements the "static prefix, dynamic suffix" principle:
    1. System Prompt (static) — role definition + tool rules + tool schemas JSON
       → Stays identical across the entire Maya session to trigger API-side
         prompt caching (DeepSeek, Claude, OpenAI, etc.)
    2. Conversation history (semi-static) — past user/assistant/tool messages
    3. Dynamic context (dynamic) — current Maya scene state + user's new message
       → Injected as the LAST user message, ensuring the static prefix is
         never invalidated.

This separation maximizes cache hit rates because the system prompt (which
includes the full tools schema and instructions) is the same for every request.
"""

import json
import traceback

from .tool_registry import registry
from .context_fetcher import fetch_full_context
from . import config


# ---------------------------------------------------------------------------
# Static System Prompt (cached across session)
# ---------------------------------------------------------------------------

_STATIC_SYSTEM_PROMPT_CACHE = None


def _build_static_system_prompt():
    """
    Build the STATIC portion of the system prompt.
    This MUST NOT include any dynamic data (scene state, selection, etc.).
    It should only contain:
        - AI role definition
        - Tool usage rules
        - Full tool schemas as JSON (so the LLM knows the exact interfaces)
    """
    tool_names = registry.get_all_names()
    tool_schemas = registry.get_all_schemas()

    tools_section = ""
    if tool_names:
        tools_section = (
            "\n\n## 重要：工具调用规则\n"
            "你拥有以下工具，可以直接在 Maya 中执行操作。\n"
            "【核心规则】当用户要求你执行任何 Maya 操作时（如归零、创建物体、打关键帧等），"
            "你 **必须** 使用 function calling（工具调用）来执行，"
            "**绝对禁止** 输出 Python 代码让用户自己去执行。\n"
            "你可以直接操作 Maya 场景，不需要用户手动运行任何代码。\n"
            "【完成规则】当你收到工具执行的结果后，**必须直接用自然语言回复用户**，"
            "告诉用户操作的结果，**不要再次调用相同的工具**。"
            "每个操作只需要调用一次工具即可，收到结果就意味着操作已经成功执行完毕。\n"
            "可用工具: {}\n".format(", ".join(tool_names))
        )

        # Embed tool schemas as JSON for additional clarity
        # (Some models benefit from seeing the full schema in the system prompt)
        tools_section += (
            "\n### 工具 Schema 参考\n"
            "```json\n{}\n```\n".format(
                json.dumps(tool_schemas, ensure_ascii=False, indent=2)
            )
        )

    prompt = (
        "你是一个运行在 Autodesk Maya 中的 AI 助手，专门帮助动画师完成日常工作。\n"
        "你精通 Maya Python API (maya.cmds, maya.api)、动画原理、绑定技术和工作流优化。\n"
        "请用中文回答，保持专业且简洁。\n"
        "\n"
        "## 关于场景信息的核心原则\n"
        "每次用户发消息时，系统会自动注入当前 Maya 场景的实时状态数据，\n"
        "包括：场景统计、对象列表、层级结构、变换值、材质、选择状态等。\n"
        "【绝对原则】你回答关于场景的问题时，**必须严格基于注入的场景状态数据**。\n"
        "如果场景数据中没有某个对象，你**绝对不能**编造或猜测它存在。\n"
        "如果你不确定，请明确告诉用户你看到了什么，或使用 execute_python_code 查询更多详情。\n"
        "**禁止凭空编造场景内容。**\n"
        "\n"
        "## 视觉能力\n"
        "你拥有 capture_viewport 工具，可以截取 Maya 视口画面来查看场景。\n"
        "当用户要求你查看、分析、评价场景画面、检查模型外观、灯光效果、材质、"
        "动画姿态等视觉相关内容时，你应该主动调用 capture_viewport 工具。\n"
        "截图后你会在下一条消息中收到视口画面图片，请基于实际看到的画面进行分析。\n"
        "\n"
        "### 视觉分析核心准则（最高优先级规则）\n"
        "当你收到视口截图时，你**必须严格遵守以下规则**：\n"
        "\n"
        "**规则0（最高优先级）：几何分析结论不可推翻**\n"
        "截图时系统会自动运行精确的几何分析（采样顶点位置、计算区域分布），\n"
        "如果分析报告中出现 '确定没有头部'、'确定没有脚部' 等结论，\n"
        "你**必须完全采纳这些结论**，即使你觉得图片中可能看到了某些东西。\n"
        "原因：几何分析是基于精确数学计算的，比视觉观察更可靠。\n"
        "绝对不要试图用'顶点数量多'、'包围盒大'等理由去反驳几何分析的结论。\n"
        "\n"
        "1. **只描述你在图片中实际看到的内容**，不要编造、推测或添加图片中不存在的细节。\n"
        "2. **数据优先于视觉猜测**：当几何分析数据与你的视觉印象冲突时，以数据为准。\n"
        "3. **准确描述姿态**：不要笼统地说'T-Pose'或'A-Pose'，而要具体描述你看到的："
        "手臂角度大约是多少度？双腿是否并拢还是分开？手指是否可见？躯干是否直立？\n"
        "4. **如实报告缺失部位**：如果几何分析或图片显示模型缺少头部、手部、脚部等，"
        "必须在回答开头就明确指出，不要假设它们存在。\n"
        "5. **区分显示模式**：准确描述你看到的渲染模式（线框、实体、纹理、X光等）。\n"
        "6. **不确定就说不确定**：如果图片模糊或你无法确定某个细节，明确说'无法确定'。\n"
        "\n"
        "## execute_python_code 使用策略\n"
        "你拥有 execute_python_code 工具，可以在 Maya 中执行任意 Python 代码。\n"
        "使用策略：\n"
        "- 当有对应的专用工具时（如 zero_out_transforms、set_keyframe），优先使用专用工具\n"
        "- 当专用工具无法完成需求时，使用 execute_python_code 编写并执行 Maya Python 代码\n"
        "- 查询场景信息、复杂批量操作、专用工具未覆盖的操作都应使用 execute_python_code\n"
        "- 代码中用 print() 输出结果，输出会返回给你用于后续判断\n"
        "- 可以使用 maya.cmds、maya.mel、maya.api.OpenMaya 等所有 Maya API\n"
        "- 不要在代码中 import 已不需要的模块，保持简洁\n"
        "{tools_section}"
    ).format(tools_section=tools_section)

    return prompt


def get_static_system_prompt(force_rebuild=False):
    """
    Get the static system prompt, cached for the session.
    Call with force_rebuild=True if tools have been re-registered.
    """
    global _STATIC_SYSTEM_PROMPT_CACHE
    if _STATIC_SYSTEM_PROMPT_CACHE is None or force_rebuild:
        _STATIC_SYSTEM_PROMPT_CACHE = _build_static_system_prompt()
    return _STATIC_SYSTEM_PROMPT_CACHE


def invalidate_prompt_cache():
    """Call this when tools are re-registered or settings change."""
    global _STATIC_SYSTEM_PROMPT_CACHE
    _STATIC_SYSTEM_PROMPT_CACHE = None


# ---------------------------------------------------------------------------
# Dynamic Context Builder
# ---------------------------------------------------------------------------

def _build_dynamic_context():
    """
    Build the DYNAMIC portion: current Maya scene state.
    This changes on every request.
    """
    try:
        return fetch_full_context()
    except Exception:
        return "(场景上下文获取失败: {})".format(
            traceback.format_exc().splitlines()[-1]
        )


# ---------------------------------------------------------------------------
# Public API: Build Full Messages
# ---------------------------------------------------------------------------

def _count_rounds(conversation):
    """
    Count the number of user→assistant interaction rounds in conversation.
    One 'round' = one user message + the AI's response (including any tool
    messages belonging to that response).
    """
    rounds = 0
    for msg in conversation:
        if msg.get("role") == "user":
            rounds += 1
    return rounds


def _truncate_sliding_window(conversation, max_rounds=10):
    """
    Sliding Window truncation: keep only the last N rounds of conversation,
    but never break a tool_calls→tool_result sequence.

    A 'round' starts at a user message and includes everything until the
    next user message (assistant replies, tool_calls, tool results).

    Args:
        conversation: Full conversation list.
        max_rounds: Maximum number of user→assistant rounds to keep.

    Returns:
        list: Truncated conversation.
    """
    if not conversation:
        return []

    # Find the start indices of each round (each user message)
    round_starts = []
    for i, msg in enumerate(conversation):
        if msg.get("role") == "user":
            round_starts.append(i)

    if len(round_starts) <= max_rounds:
        return list(conversation)

    # Keep the last max_rounds rounds
    cut_idx = round_starts[-max_rounds]

    # Safety: don't cut into an orphaned tool response sequence
    while cut_idx > 0 and conversation[cut_idx].get("role") == "tool":
        cut_idx -= 1

    return list(conversation[cut_idx:])


def build_messages(conversation, max_history=20, max_rounds=10):
    """
    Build the full messages array for the LLM API request.

    Structure (optimized for prompt caching):
        [0] system:  STATIC system prompt (role + tool rules + schemas)
        [1..N-1] conversation history (sliding window: last N rounds)
        [N] user:  DYNAMIC context block prepended to the last user message

    The system message (index 0) is IDENTICAL across all requests in a
    session, triggering server-side prompt caching on DeepSeek/Claude/OpenAI.

    Sliding Window Strategy:
        - Always keep the system prompt (index 0)
        - Keep the last `max_rounds` user→assistant rounds
        - Never break a tool_calls→tool_result sequence
        - Inject dynamic Maya context only into the final user message

    Args:
        conversation: List of conversation message dicts.
        max_history: Max number of raw messages to include (hard limit).
        max_rounds: Max number of user→assistant rounds to keep.

    Returns:
        list[dict]: Messages array ready for the API.
    """
    # 1. Static system prompt (always first, never changes)
    system_prompt = get_static_system_prompt()
    messages = [{"role": "system", "content": system_prompt}]

    # 2. Sliding window truncation (round-aware)
    conv = _truncate_sliding_window(conversation, max_rounds=max_rounds)

    # Hard message count limit as a safety net
    if len(conv) > max_history:
        start = len(conv) - max_history
        while start > 0 and conv[start].get("role") == "tool":
            start -= 1
        conv = conv[start:]

    # 3. Inject dynamic context into the last user message
    dynamic_context = _build_dynamic_context()
    context_prefix = (
        "[Maya 实时场景状态]\n{}\n\n"
        "[用户请求]\n".format(dynamic_context)
    )

    # Check for pending viewport image from vision_tool
    pending_image = _get_pending_viewport_image()
    pending_scene_meta = _get_pending_scene_metadata()

    # Build the final messages list
    for i, msg in enumerate(conv):
        if msg.get("role") == "user" and i == len(conv) - 1:
            # Last user message: prepend dynamic context
            user_text = context_prefix + (msg.get("content") or "")

            if pending_image:
                # Add scene metadata and vision analysis instructions
                vision_instructions = (
                    "\n\n[视觉分析任务]\n"
                    "下面附带了一张 Maya 视口截图。请**严格基于图片中实际可见的内容**进行分析。\n"
                    "\n"
                    "【最高优先级】以下是系统通过精确几何计算生成的分析报告。\n"
                    "报告中标记为'确定没有XX'的结论是通过顶点位置采样数学计算得出的，\n"
                    "准确率极高。你**必须完全采纳**这些结论，不可质疑或反驳。\n"
                    "即使你觉得图中某个区域'看起来像是有东西'，也以数据分析为准。\n"
                )
                if pending_scene_meta:
                    vision_instructions += "\n{}\n".format(pending_scene_meta)

                user_text += vision_instructions

                # Multimodal content: text + image
                augmented = dict(msg)
                augmented["content"] = [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": pending_image,
                            "detail": config.get("VISION_DETAIL", "high"),
                        },
                    },
                ]
                messages.append(augmented)
            else:
                # Standard text-only content
                augmented = dict(msg)
                augmented["content"] = user_text
                messages.append(augmented)
        else:
            messages.append(msg)

    return messages


def _get_pending_viewport_image():
    """Safely retrieve the pending viewport image from vision_tool.

    Returns None if the vision_tool module is not loaded or no image pending.
    """
    try:
        from .tools.vision_tool import get_pending_image
        return get_pending_image()
    except (ImportError, Exception):
        return None


def _get_pending_scene_metadata():
    """Safely retrieve the pending scene metadata from vision_tool.

    Returns None if no metadata pending.
    """
    try:
        from .tools.vision_tool import get_pending_scene_metadata
        return get_pending_scene_metadata()
    except (ImportError, Exception):
        return None
