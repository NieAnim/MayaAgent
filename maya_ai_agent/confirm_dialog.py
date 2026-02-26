# -*- coding: utf-8 -*-
"""
Confirm Dialog - Human-in-the-loop confirmation before executing AI tool calls.

Shows the user what the AI wants to do (function name + arguments)
and requires explicit approval before execution proceeds.
"""

import json

from .qt_compat import QtWidgets, QtGui, Qt, Signal, Slot


_DIALOG_STYLE = """
QDialog {
    background-color: #2b2b2b;
}
QLabel {
    color: #d4d4d4;
    font-size: 13px;
}
QLabel#titleLabel {
    color: #4ec9b0;
    font-size: 15px;
    font-weight: bold;
}
QLabel#warningLabel {
    color: #f0c674;
    font-size: 12px;
}
QTextEdit#detailsBox {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QPushButton#approveBtn {
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
    min-width: 80px;
}
QPushButton#approveBtn:hover {
    background-color: #1a8ae8;
}
QPushButton#rejectBtn {
    background-color: #555555;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    min-width: 80px;
}
QPushButton#rejectBtn:hover {
    background-color: #666666;
}
QPushButton#approveAllBtn {
    background-color: transparent;
    color: #888888;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
}
QPushButton#approveAllBtn:hover {
    background-color: #3c3c3c;
    color: #d4d4d4;
}
QCheckBox {
    color: #aaaaaa;
    font-size: 12px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
}
"""


class ConfirmDialog(QtWidgets.QDialog):
    """
    Modal dialog that asks the user to approve/reject an AI tool call.

    Returns QDialog.Accepted if approved, QDialog.Rejected otherwise.
    Also tracks "approve all for this session" state.
    """

    # Class-level flag: if True, skip confirmation for all subsequent calls
    _auto_approve = False

    @classmethod
    def reset_auto_approve(cls):
        cls._auto_approve = False

    @classmethod
    def is_auto_approved(cls):
        return cls._auto_approve

    def __init__(self, tool_calls, parent=None):
        """
        Args:
            tool_calls: list of tool call dicts from the LLM.
        """
        super().__init__(parent)
        self.setWindowTitle("AI 操作确认")
        self.setMinimumWidth(480)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowStaysOnTopHint
        )

        self._tool_calls = tool_calls
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title
        title = QtWidgets.QLabel("AI 请求执行以下操作")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        # Warning
        warning = QtWidgets.QLabel(
            "请确认以下工具调用是否安全。所有操作均可通过 Ctrl+Z 撤销。"
        )
        warning.setObjectName("warningLabel")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # Tool call details
        details_text = self._format_tool_calls()
        details = QtWidgets.QTextEdit()
        details.setObjectName("detailsBox")
        details.setPlainText(details_text)
        details.setReadOnly(True)
        details.setMaximumHeight(260)
        layout.addWidget(details)

        # Approve all checkbox
        self._approve_all_cb = QtWidgets.QCheckBox("本次会话不再询问（自动批准）")
        layout.addWidget(self._approve_all_cb)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        reject_btn = QtWidgets.QPushButton("拒绝")
        reject_btn.setObjectName("rejectBtn")
        reject_btn.clicked.connect(self.reject)
        btn_layout.addWidget(reject_btn)

        approve_btn = QtWidgets.QPushButton("批准执行")
        approve_btn.setObjectName("approveBtn")
        approve_btn.clicked.connect(self._on_approve)
        approve_btn.setDefault(True)
        btn_layout.addWidget(approve_btn)

        layout.addLayout(btn_layout)

    def _format_tool_calls(self):
        """Format tool calls into readable text."""
        lines = []
        for i, tc in enumerate(self._tool_calls, 1):
            func_name = tc.get("function", {}).get("name", "?")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                args_display = json.dumps(args, ensure_ascii=False, indent=2)
            except Exception:
                args_display = str(args_str)

            lines.append("--- 操作 {} ---".format(i))
            lines.append("工具: {}".format(func_name))
            lines.append("参数:")
            lines.append(args_display)
            lines.append("")

        return "\n".join(lines)

    @Slot()
    def _on_approve(self):
        if self._approve_all_cb.isChecked():
            ConfirmDialog._auto_approve = True
        self.accept()
