# -*- coding: utf-8 -*-
"""
Execute Code Tool - Allow the LLM to execute arbitrary Python code in Maya.

This is the most powerful tool: it enables the AI to do anything in Maya,
even operations not covered by dedicated tools.

Safety:
    - All execution is wrapped in undo chunks (by ActionExecutor)
    - Runs on the main thread via executeDeferred
    - Output is captured and returned
    - Code length is limited to 50KB
"""

import sys
import maya.cmds as cmds

from ..tool_registry import tool


# ---------------------------------------------------------------------------
# Tool: execute_python_code
# ---------------------------------------------------------------------------

@tool(
    name="execute_python_code",
    description=(
        "在 Maya 中执行任意 Python 代码。这是最灵活的工具，可以完成任何 Maya 操作。\n"
        "适用场景：\n"
        "- 其他工具无法覆盖的操作（如创建骨骼、蒙皮、约束、BlendShape 等）\n"
        "- 查询场景信息（如获取骨骼层级、属性值等）\n"
        "- 批量操作和复杂工作流\n"
        "- FBX 导入/导出\n"
        "\n"
        "重要规则：\n"
        "1. 代码中可以使用 maya.cmds、maya.mel、maya.api.OpenMaya 等 Maya API\n"
        "2. 使用 print() 输出结果，所有 print 输出会被捕获并返回给你\n"
        "3. 代码在 Maya 主线程中执行，可以直接操作场景\n"
        "4. 如果需要返回数据，请 print() 输出\n"
        "5. 代码长度限制 50KB\n"
        "6. 不要执行危险操作（如 os.system、subprocess、删除文件等）"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "要在 Maya 中执行的 Python 代码。可以是多行代码。"
                    "使用 print() 输出结果。"
                ),
            },
        },
        "required": ["code"],
    },
)
def execute_python_code(code=""):
    """Execute arbitrary Python code in Maya and capture output."""
    if not code or not code.strip():
        return {"success": False, "message": "代码为空，无法执行。"}

    # Safety: limit code length
    if len(code) > 50000:
        return {"success": False, "message": "代码长度超过 50KB 限制。"}

    # Safety: check for dangerous patterns
    dangerous_patterns = [
        "subprocess", "os.system", "os.popen", "os.exec",
        "shutil.rmtree", "__import__('os')",
    ]
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            return {
                "success": False,
                "message": "检测到潜在危险操作: {}。出于安全考虑，此操作被禁止。".format(pattern),
            }

    # Capture stdout
    class OutputCapture:
        def __init__(self):
            self.lines = []

        def write(self, text):
            if text and text.strip():
                self.lines.append(text)

        def flush(self):
            pass

        def get_output(self):
            return "".join(self.lines)

    capture = OutputCapture()
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        sys.stdout = capture
        sys.stderr = capture

        # Execute the code
        exec_globals = {
            "__builtins__": __builtins__,
            "cmds": cmds,
        }
        exec(code, exec_globals)

        output = capture.get_output()
        if not output:
            output = "代码执行成功（无输出）"

        return {
            "success": True,
            "message": output,
        }

    except Exception as e:
        output = capture.get_output()
        error_msg = str(e)
        result_msg = "执行出错: {}".format(error_msg)
        if output:
            result_msg = "部分输出:\n{}\n\n错误: {}".format(output, error_msg)
        return {
            "success": False,
            "message": result_msg,
        }

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
