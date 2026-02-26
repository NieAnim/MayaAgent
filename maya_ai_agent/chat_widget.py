# -*- coding: utf-8 -*-
"""
Chat Widget - The main chat interface for Maya AI Agent.
A modern dockable panel inspired by CodeBuddy-style layout:
    - Left sidebar with icon tabs (New Chat / History / Settings)
    - Chat area with bubble-style messages
    - Multi-line input with auto-wrap (Enter to send, Shift+Enter for newline)
    - Font size control that affects chat content
"""

import datetime
import json

from .qt_compat import (
    QtWidgets, QtCore, QtGui, Signal, Slot, Qt, QTimer,
)
from .llm_worker import LLMWorker
from .action_executor import ActionExecutor
from .confirm_dialog import ConfirmDialog
from .tool_registry import registry
from .prompt_builder import build_messages, invalidate_prompt_cache
from .command_shortcut import try_shortcut, execute_shortcut
from .history_manager import HistoryManager
from .history_widget import HistoryWidget
from .settings_widget import SettingsWidget
from .markdown_renderer import render_markdown
from . import response_cache
from . import config

# Ensure tools are registered
from . import tools as _tools_init  # noqa: F401


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FONT_SIZE_MIN = 10
FONT_SIZE_MAX = 24
FONT_SIZE_DEFAULT = 13
FONT_SIZE_STEP = 1

# Max number of tool-call round-trips to prevent infinite loops
MAX_TOOL_ROUNDS = 10

# Sidebar width
SIDEBAR_WIDTH = 42

# Sidebar button IDs
TAB_CHAT = 0
TAB_HISTORY = 1
TAB_SETTINGS = 2


# ---------------------------------------------------------------------------
# Multi-line input that sends on Enter, newline on Shift+Enter
# ---------------------------------------------------------------------------

class ChatInput(QtWidgets.QTextEdit):
    """Multi-line input field: Enter sends, Shift+Enter inserts newline."""

    submit = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self._min_height = 36
        self._max_height = 120
        self.setMinimumHeight(self._min_height)
        self.setMaximumHeight(self._max_height)
        self.document().contentsChanged.connect(self._auto_resize)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                event.accept()
                self.submit.emit()
        else:
            super().keyPressEvent(event)

    def _auto_resize(self):
        doc_height = int(self.document().size().height()) + 10
        new_height = max(self._min_height, min(self._max_height, doc_height))
        self.setFixedHeight(new_height)


# ---------------------------------------------------------------------------
# Stylesheet builder
# ---------------------------------------------------------------------------

def _build_stylesheet(font_size):
    fs = font_size
    small_fs = max(fs - 2, 10)
    btn_fs = max(fs - 1, 11)
    return """
/* ---- Global ---- */
QWidget#MayaAIAgentChat {{
    background-color: #1e1e1e;
}}

/* ---- Sidebar ---- */
QFrame#sidebar {{
    background-color: #252526;
    border-right: 1px solid #333333;
}}

QPushButton.sidebarBtn {{
    background-color: transparent;
    border: none;
    border-left: 2px solid transparent;
    color: #858585;
    font-size: 18px;
    padding: 10px 0px;
    min-height: 36px;
}}

QPushButton.sidebarBtn:hover {{
    color: #d4d4d4;
    background-color: #2a2d2e;
}}

QPushButton.sidebarBtn[active="true"] {{
    color: #ffffff;
    border-left: 2px solid #0078d4;
    background-color: #37373d;
}}

/* ---- Chat area ---- */
QTextEdit#chatHistory {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    padding: 12px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: {fs}px;
    selection-background-color: #264f78;
}}

/* ---- Input area ---- */
QTextEdit#chatInput {{
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 8px 12px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: {fs}px;
    selection-background-color: #264f78;
}}

QTextEdit#chatInput:focus {{
    border-color: #0078d4;
}}

/* ---- Send button ---- */
QPushButton#sendBtn {{
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 18px;
    font-size: {btn_fs}px;
    font-weight: bold;
    min-height: 32px;
}}

QPushButton#sendBtn:hover {{
    background-color: #1a8ae8;
}}

QPushButton#sendBtn:pressed {{
    background-color: #005a9e;
}}

QPushButton#sendBtn:disabled {{
    background-color: #555555;
    color: #888888;
}}

/* ---- Stop button ---- */
QPushButton#stopBtn {{
    background-color: #d42020;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: {btn_fs}px;
    font-weight: bold;
    min-height: 32px;
}}

QPushButton#stopBtn:hover {{
    background-color: #e83838;
}}

QPushButton#stopBtn:pressed {{
    background-color: #a01818;
}}

/* ---- Status ---- */
QLabel#statusLabel {{
    color: #888888;
    font-size: {small_fs}px;
    padding: 2px 8px;
}}

/* ---- Top bar in chat ---- */
QLabel#panelTitle {{
    color: #cccccc;
    font-size: 13px;
    font-weight: bold;
    padding: 0 4px;
}}

QPushButton#topBarBtn {{
    background-color: transparent;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    color: #858585;
    padding: 3px 8px;
    font-size: 12px;
}}

QPushButton#topBarBtn:hover {{
    background-color: #3c3c3c;
    color: #d4d4d4;
}}

QLabel#fontSizeLabel {{
    color: #858585;
    font-size: 11px;
    padding: 0 2px;
}}

/* ---- Stacked pages ---- */
QStackedWidget#pageStack {{
    background-color: #1e1e1e;
}}
""".format(fs=fs, small_fs=small_fs, btn_fs=btn_fs)


class ChatWidget(QtWidgets.QWidget):
    """
    Main chat interface widget with CodeBuddy-style sidebar layout.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MayaAIAgentChat")

        self._font_size = self._load_font_size()

        # Conversation history for LLM context
        self._conversation = []
        # Active worker reference
        self._worker = None
        # Tool call loop counter
        self._tool_round = 0
        # Pending tool results collector
        self._pending_tool_results = {}
        self._expected_tool_ids = []
        # Last assistant message with tool_calls
        self._last_assistant_tool_msg = None
        # Tracking for response caching
        self._last_user_query = ""
        self._last_used_tools = False

        # Streaming state
        self._streaming_content = ""
        self._streaming_active = False
        self._stream_block_start = 0

        # History manager (persistent storage)
        self._history = HistoryManager.instance()
        self._tools_used_names = []

        # Action executor (main thread tool runner)
        self._executor = ActionExecutor(parent=self)
        self._executor.execution_finished.connect(self._on_tool_executed)
        self._executor.execution_error.connect(self._on_tool_exec_error)

        # Thinking animation
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(400)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._thinking_dots = 0

        self._current_tab = TAB_CHAT
        self._sidebar_buttons = []

        self._build_ui()
        self._apply_font_size()

    # ----- Font Size --------------------------------------------------------

    @staticmethod
    def _load_font_size():
        try:
            size = int(config.get("UI_FONT_SIZE", str(FONT_SIZE_DEFAULT)))
            return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, size))
        except (ValueError, TypeError):
            return FONT_SIZE_DEFAULT

    def _save_font_size(self):
        cfg = config.load_config(force_reload=True)
        cfg["UI_FONT_SIZE"] = str(self._font_size)
        config.save_config(cfg)

    def _apply_font_size(self):
        self.setStyleSheet(_build_stylesheet(self._font_size))
        if hasattr(self, '_font_size_label'):
            self._font_size_label.setText("{}px".format(self._font_size))
        # Apply font to chat history via default font (overrides all content)
        if hasattr(self, 'chat_history'):
            font = QtGui.QFont("Segoe UI", self._font_size)
            font.setStyleHint(QtGui.QFont.SansSerif)
            self.chat_history.document().setDefaultFont(font)
        # Apply font to chat input
        if hasattr(self, 'chat_input'):
            font = QtGui.QFont("Segoe UI", self._font_size)
            font.setStyleHint(QtGui.QFont.SansSerif)
            self.chat_input.document().setDefaultFont(font)
        # Update sidebar button active states after stylesheet reset
        self._update_sidebar_active()

    @Slot()
    def _on_font_increase(self):
        if self._font_size < FONT_SIZE_MAX:
            self._font_size += FONT_SIZE_STEP
            self._apply_font_size()
            self._save_font_size()

    @Slot()
    def _on_font_decrease(self):
        if self._font_size > FONT_SIZE_MIN:
            self._font_size -= FONT_SIZE_STEP
            self._apply_font_size()
            self._save_font_size()

    # ----- UI Construction ---------------------------------------------------

    def _build_ui(self):
        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ====== Left sidebar ======
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 8)
        sidebar_layout.setSpacing(2)

        # Sidebar buttons: New Chat, History, Settings
        btn_data = [
            ("💬", "新增对话", TAB_CHAT),
            ("📋", "历史记录", TAB_HISTORY),
            ("⚙", "设置", TAB_SETTINGS),
        ]
        for icon, tooltip, tab_id in btn_data:
            btn = QtWidgets.QPushButton(icon)
            btn.setProperty("class", "sidebarBtn")
            btn.setToolTip(tooltip)
            btn.setFixedSize(SIDEBAR_WIDTH, 40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, tid=tab_id: self._switch_tab(tid))
            sidebar_layout.addWidget(btn)
            self._sidebar_buttons.append(btn)

        sidebar_layout.addStretch()
        root_layout.addWidget(sidebar)

        # ====== Right content area (stacked) ======
        self._page_stack = QtWidgets.QStackedWidget()
        self._page_stack.setObjectName("pageStack")

        # --- Page 0: Chat ---
        self._page_stack.addWidget(self._build_chat_page())

        # --- Page 1: History ---
        self._history_widget = HistoryWidget()
        self._history_widget.reuse_reply.connect(self._on_reuse_history_reply)
        self._history_widget.resume_session.connect(self._on_resume_session)
        self._page_stack.addWidget(self._history_widget)

        # --- Page 2: Settings ---
        self._settings_widget = SettingsWidget()
        self._page_stack.addWidget(self._settings_widget)

        root_layout.addWidget(self._page_stack, stretch=1)

        # Set initial tab
        self._switch_tab(TAB_CHAT)

    def _build_chat_page(self):
        """Build the chat page widget."""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Top bar ---
        top_bar = QtWidgets.QFrame()
        top_bar.setStyleSheet("QFrame { background-color: #252526; border-bottom: 1px solid #333333; }")
        top_bar.setFixedHeight(38)
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setSpacing(6)

        title = QtWidgets.QLabel("Maya AI Agent")
        title.setObjectName("panelTitle")
        top_layout.addWidget(title)

        # Token usage mini label in top bar
        self._token_label = QtWidgets.QLabel("")
        self._token_label.setStyleSheet(
            "color: #4ec9b0; font-size: 11px; padding: 0 6px;"
        )
        self._token_label.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self._token_label)

        top_layout.addStretch()

        # Font size controls
        font_down_btn = QtWidgets.QPushButton("A-")
        font_down_btn.setObjectName("topBarBtn")
        font_down_btn.setToolTip("减小字体")
        font_down_btn.setFixedWidth(28)
        font_down_btn.clicked.connect(self._on_font_decrease)
        top_layout.addWidget(font_down_btn)

        self._font_size_label = QtWidgets.QLabel("{}px".format(self._font_size))
        self._font_size_label.setObjectName("fontSizeLabel")
        self._font_size_label.setAlignment(Qt.AlignCenter)
        self._font_size_label.setFixedWidth(32)
        top_layout.addWidget(self._font_size_label)

        font_up_btn = QtWidgets.QPushButton("A+")
        font_up_btn.setObjectName("topBarBtn")
        font_up_btn.setToolTip("增大字体")
        font_up_btn.setFixedWidth(28)
        font_up_btn.clicked.connect(self._on_font_increase)
        top_layout.addWidget(font_up_btn)

        # Clear conversation
        clear_btn = QtWidgets.QPushButton("清空")
        clear_btn.setObjectName("topBarBtn")
        clear_btn.clicked.connect(self._on_clear)
        top_layout.addWidget(clear_btn)

        layout.addWidget(top_bar)

        # --- Chat history ---
        self.chat_history = QtWidgets.QTextEdit()
        self.chat_history.setObjectName("chatHistory")
        self.chat_history.setReadOnly(True)
        self.chat_history.setAcceptRichText(True)
        self.chat_history.setPlaceholderText("在下方输入消息，开始与 AI 对话...")
        layout.addWidget(self.chat_history, stretch=1)

        # --- Status ---
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        # --- Input area ---
        input_container = QtWidgets.QFrame()
        input_container.setStyleSheet(
            "QFrame { background-color: #252526; border-top: 1px solid #333333; }"
        )
        input_layout = QtWidgets.QHBoxLayout(input_container)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self.chat_input = ChatInput()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setPlaceholderText("输入消息... (Enter 发送, Shift+Enter 换行)")
        self.chat_input.submit.connect(self._on_send)
        input_layout.addWidget(self.chat_input, stretch=1)

        self.send_btn = QtWidgets.QPushButton("发送")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self.send_btn, alignment=Qt.AlignBottom)

        self.stop_btn = QtWidgets.QPushButton("停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setToolTip("停止生成")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setVisible(False)
        input_layout.addWidget(self.stop_btn, alignment=Qt.AlignBottom)

        layout.addWidget(input_container)

        return page

    # ----- Sidebar Tab Switching -------------------------------------------

    def _switch_tab(self, tab_id):
        self._current_tab = tab_id
        self._page_stack.setCurrentIndex(tab_id)
        self._update_sidebar_active()

        # Refresh data on switch
        if tab_id == TAB_HISTORY:
            self._history_widget.refresh()
        elif tab_id == TAB_SETTINGS:
            self._settings_widget.reload_config()

    def _update_sidebar_active(self):
        for i, btn in enumerate(self._sidebar_buttons):
            btn.setProperty("active", "true" if i == self._current_tab else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ----- Chat Display Helpers ---------------------------------------------

    def _append_message(self, role, text):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.chat_history.setTextCursor(cursor)

        if role == "user":
            label = "🧑 你"; color = "#569cd6"; bg = "#1a1a2e"
        elif role == "assistant":
            label = "🤖 AI"; color = "#4ec9b0"; bg = "#1a2e1a"
        elif role == "tool":
            label = "🔧 工具"; color = "#dcdcaa"; bg = "#2e2a1a"
        elif role == "error":
            label = "⚠ 错误"; color = "#f44747"; bg = "#2e1a1a"
        else:
            label = "ℹ 系统"; color = "#888888"; bg = "#252525"

        # Render content: Markdown for assistant, plain escaped HTML for others
        if role == "assistant":
            rendered_text = render_markdown(text)
        else:
            rendered_text = self._escape_html(text)

        # NOTE: Do NOT set font-size in inline HTML styles.
        # Font size is controlled by chat_history.document().setDefaultFont()
        # so that A+/A- changes affect ALL messages (existing + new) instantly.
        html = (
            '<div style="margin: 4px 0; padding: 8px 12px; '
            'background-color: {bg}; border-radius: 8px; border-left: 3px solid {color};">'
            '<span style="color:{color}; font-weight:bold;">{label}</span>'
            '  <span style="color:#555; font-size:small;">{time}</span>'
            '<div style="color:#d4d4d4; '
            'margin-top: 4px; line-height: 1.5;">{text}</div>'
            '</div>'
        ).format(
            color=color, bg=bg, label=label, time=timestamp,
            text=rendered_text,
        )
        self.chat_history.append(html)
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @staticmethod
    def _escape_html(text):
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
        )

    def _append_reasoning(self, reasoning_text):
        """Append a collapsible reasoning/thinking block (DeepSeek-Reasoner)."""
        escaped = self._escape_html(reasoning_text)
        # QTextEdit doesn't support <details>/<summary>, so we use a styled div
        # with a smaller font and muted color to visually separate it.
        html = (
            '<div style="margin: 2px 0 4px 0; padding: 6px 12px; '
            'background-color: #1a1a2e; border-radius: 6px; '
            'border-left: 3px solid #6a5acd;">'
            '<span style="color:#6a5acd; font-weight:bold; font-size:small;">'
            '💭 思维链 (Reasoning)</span>'
            '<div style="color:#8888aa; font-size:small; '
            'margin-top: 4px; line-height: 1.4;">{text}</div>'
            '</div>'
        ).format(text=escaped)
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.chat_history.setTextCursor(cursor)
        self.chat_history.append(html)
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ----- Thinking Animation -----------------------------------------------

    def _animate_thinking(self):
        self._thinking_dots = (self._thinking_dots % 3) + 1
        dots = "." * self._thinking_dots
        self.status_label.setText("AI 正在思考" + dots)

    def _set_busy(self, busy):
        self.send_btn.setEnabled(not busy)
        self.send_btn.setVisible(not busy)
        self.stop_btn.setVisible(busy)
        self.chat_input.setEnabled(not busy)
        if busy:
            self._thinking_dots = 0
            self._thinking_timer.start()
        else:
            self._thinking_timer.stop()
            self.status_label.setText("")

    # ----- Build Messages ---------------------------------------------------

    def _build_messages(self):
        return build_messages(self._conversation, max_history=20)

    def _get_tools_schema(self):
        schemas = registry.get_all_schemas()
        return schemas if schemas else None

    # ----- Send & LLM Loop --------------------------------------------------

    @Slot()
    def _on_send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        self.chat_input.clear()
        self._append_message("user", text)
        self._conversation.append({"role": "user", "content": text})

        # --- Layer 1: Local command shortcut (zero-latency) ---
        shortcut = try_shortcut(text)
        if shortcut:
            self._execute_shortcut(shortcut)
            return

        # --- Layer 2: Response cache lookup (zero-latency for Q&A) ---
        cached = response_cache.lookup(text)
        if cached:
            self._append_message("assistant", cached)
            self._append_message("system", "（来自本地缓存）")
            self._conversation.append({"role": "assistant", "content": cached})
            self._history.append(
                user_input=text,
                assistant_reply=cached,
                tools_used=[],
                is_shortcut=False,
            )
            return

        # --- Layer 3: Full LLM request ---
        api_key = config.get("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            self._append_message("system", "请先点击左侧「⚙ 设置」配置你的 API Key。")
            return

        self._last_user_query = text
        self._last_used_tools = False
        self._tools_used_names = []

        self._tool_round = 0
        self._start_llm_request()

    def _execute_shortcut(self, shortcut_info):
        import maya.utils

        tool_name = shortcut_info["tool_name"]
        matched_input = shortcut_info.get("matched_input", tool_name)
        self._append_message("tool", "⚡ 快捷执行: {}".format(tool_name))

        def _do():
            import maya.cmds as cmds
            chunk_name = "AIAgent_shortcut_{}".format(tool_name)
            cmds.undoInfo(openChunk=True, chunkName=chunk_name)
            try:
                result = execute_shortcut(shortcut_info)
            finally:
                cmds.undoInfo(closeChunk=True)

            msg = result.get("message", str(result))
            self._append_message("tool", "结果: {}".format(msg))

            reply_text = "已执行 {}: {}".format(tool_name, msg)
            self._conversation.append({
                "role": "assistant",
                "content": reply_text,
            })

            self._history.append(
                user_input=matched_input,
                assistant_reply=reply_text,
                tools_used=[tool_name],
                is_shortcut=True,
            )

        maya.utils.executeDeferred(_do)

    def _start_llm_request(self, force_text_only=False):
        messages = self._build_messages()
        tools = self._get_tools_schema()
        tool_choice = "none" if force_text_only else "auto"

        # Enable streaming for text-only responses (not tool calls)
        use_stream = True

        self._streaming_content = ""
        self._streaming_active = False

        self._set_busy(True)
        self._worker = LLMWorker(
            messages, tools=tools, tool_choice=tool_choice,
            stream=use_stream, parent=self
        )
        self._worker.response_chunk.connect(self._on_response_chunk)
        self._worker.response_finished.connect(self._on_response)
        self._worker.tool_calls_received.connect(self._on_tool_calls)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.status_changed.connect(self._on_status)
        self._worker.usage_received.connect(self._on_usage)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    # ----- Response Handlers ------------------------------------------------

    @Slot(str)
    def _on_response_chunk(self, chunk_text):
        """Handle a streaming text chunk — append text directly for performance."""
        if not self._streaming_active:
            # First chunk: create the message bubble header, then insert text
            self._streaming_active = True
            self._streaming_content = chunk_text

            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            header_html = (
                '<div style="margin: 4px 0; padding: 8px 12px; '
                'background-color: #1a2e1a; border-radius: 8px; '
                'border-left: 3px solid #4ec9b0;">'
                '<span style="color:#4ec9b0; font-weight:bold;">\U0001f916 AI</span>'
                '  <span style="color:#555; font-size:small;">{time}</span>'
                '<div id="stream-content" style="color:#d4d4d4; '
                'margin-top: 4px; line-height: 1.5;">'
            ).format(time=timestamp)

            # Record block count before appending so _finalize_stream knows where to trim
            self._stream_block_start = self.chat_history.document().blockCount()

            cursor = self.chat_history.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            self.chat_history.setTextCursor(cursor)
            self.chat_history.append(header_html)

            # Append raw text
            cursor = self.chat_history.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            cursor.insertText(chunk_text)
            self.chat_history.setTextCursor(cursor)
        else:
            # Subsequent chunks: just append text at the end (no re-render)
            self._streaming_content += chunk_text
            cursor = self.chat_history.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            cursor.insertText(chunk_text)
            self.chat_history.setTextCursor(cursor)

        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _finalize_stream(self, final_text):
        """Replace the raw streamed plain-text with a Markdown-rendered version."""
        # Clear the streaming bubble and re-render as a proper assistant message
        doc = self.chat_history.document()
        # We recorded _stream_block_start earlier; find that position
        start_block_num = max(getattr(self, '_stream_block_start', doc.blockCount()) - 1, 0)
        start_block = doc.findBlockByNumber(start_block_num)
        cursor = QtGui.QTextCursor(doc)
        cursor.setPosition(start_block.position())
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        if not cursor.atStart():
            cursor.deletePreviousChar()
        self.chat_history.setTextCursor(cursor)
        # Re-append with full Markdown rendering
        self._append_message("assistant", final_text)

    @Slot(str)
    def _on_response(self, response_json):
        # response_json is now a JSON string: {"content": "...", "reasoning_content": "..."}
        # Fall back to treating as plain text for backward compatibility.
        try:
            resp = json.loads(response_json)
            text = resp.get("content", "")
            reasoning_content = resp.get("reasoning_content", "") or ""
        except (json.JSONDecodeError, TypeError):
            text = response_json
            reasoning_content = ""

        if text:
            if self._streaming_active:
                self._finalize_stream(text)
                self._streaming_active = False
                self._streaming_content = ""
            else:
                self._append_message("assistant", text)

            # Display reasoning chain (DeepSeek-Reasoner / R1) as a collapsible block
            if reasoning_content:
                self._append_reasoning(reasoning_content)

            assistant_msg = {"role": "assistant", "content": text}
            # Preserve reasoning_content for DeepSeek-Reasoner (R1)
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            self._conversation.append(assistant_msg)

            user_q = getattr(self, "_last_user_query", "")
            used_tools = getattr(self, "_last_used_tools", False)

            if not used_tools and user_q:
                response_cache.store(user_q, text)

            self._history.append(
                user_input=user_q,
                assistant_reply=text,
                tools_used=getattr(self, "_tools_used_names", []),
                is_shortcut=False,
            )
            self._last_user_query = ""
            self._tools_used_names = []

    @Slot(str)
    def _on_tool_calls(self, payload_json):
        self._last_used_tools = True
        try:
            payload = json.loads(payload_json)
            tool_calls = payload.get("tool_calls", [])
            accompanying_text = payload.get("content", "") or ""
            reasoning_content = payload.get("reasoning_content", "") or ""
        except json.JSONDecodeError:
            self._append_message("error", "tool_calls 解析失败")
            return

        for tc in tool_calls:
            fn = tc.get("function", {}).get("name", "")
            if fn and fn not in getattr(self, "_tools_used_names", []):
                if not hasattr(self, "_tools_used_names"):
                    self._tools_used_names = []
                self._tools_used_names.append(fn)

        if accompanying_text:
            self._append_message("assistant", accompanying_text)

        assistant_msg = {
            "role": "assistant",
            "content": accompanying_text or None,
            "tool_calls": tool_calls,
        }
        # DeepSeek-Reasoner (R1) requires reasoning_content in assistant
        # messages, otherwise the API returns 400.
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        self._conversation.append(assistant_msg)

        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "?")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                args_display = json.dumps(args, ensure_ascii=False, indent=2)
            except Exception:
                args_display = args_str
            self._append_message(
                "tool",
                "调用工具: {}\n参数: {}".format(func_name, args_display)
            )

        if not ConfirmDialog.is_auto_approved():
            dlg = ConfirmDialog(tool_calls, parent=self)
            result = dlg.exec_()
            if result != QtWidgets.QDialog.Accepted:
                self._append_message("system", "用户拒绝了工具执行。")
                for tc in tool_calls:
                    call_id = tc.get("id", "")
                    self._conversation.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(
                            {"success": False, "message": "用户拒绝执行此操作。"},
                            ensure_ascii=False,
                        ),
                    })
                self._set_busy(False)
                return

        self._expected_tool_ids = [tc.get("id", "") for tc in tool_calls]
        self._pending_tool_results = {}

        self.status_label.setText("正在执行工具...")
        self._executor.execute_tool_calls(json.dumps(tool_calls, ensure_ascii=False))

    @Slot(str, str, str)
    def _on_tool_executed(self, call_id, func_name, result_json):
        try:
            result = json.loads(result_json)
            msg = result.get("message", result_json)
        except Exception:
            msg = result_json

        self._append_message("tool", "结果 [{}]: {}".format(func_name, msg))

        self._pending_tool_results[call_id] = (func_name, result_json)

        if all(tid in self._pending_tool_results for tid in self._expected_tool_ids):
            self._on_all_tools_done()

    def _on_all_tools_done(self):
        for call_id in self._expected_tool_ids:
            func_name, result_json = self._pending_tool_results[call_id]
            self._conversation.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result_json,
            })

        self._pending_tool_results.clear()
        self._expected_tool_ids = []

        self._tool_round += 1
        if self._tool_round >= MAX_TOOL_ROUNDS:
            self._append_message(
                "system",
                "已达到工具调用轮次上限 ({})，终止循环。".format(MAX_TOOL_ROUNDS)
            )
            self._set_busy(False)
            return

        # Allow the LLM to call more tools in subsequent rounds
        # (e.g. "query scene → then create controllers").
        # Only force text-only on the very last allowed round as a safety net.
        force_text = (self._tool_round >= MAX_TOOL_ROUNDS - 1)
        self._start_llm_request(force_text_only=force_text)

    @Slot(str)
    def _on_tool_exec_error(self, error_text):
        self._append_message("error", "工具执行错误: {}".format(error_text))

    @Slot(str)
    def _on_error(self, error_text):
        self._append_message("error", error_text)

    @Slot(str)
    def _on_status(self, status):
        if status == "idle":
            self.status_label.setText("")

    @Slot(str)
    def _on_usage(self, usage_json):
        """Display token usage in top bar and settings page."""
        try:
            usage = json.loads(usage_json)
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            self._session_tokens = getattr(self, "_session_tokens", 0) + total_tokens

            # Update top bar mini label
            self._token_label.setText(
                "T:{} (累计:{})".format(total_tokens, self._session_tokens)
            )

            # Update settings page usage panel
            if hasattr(self, '_settings_widget'):
                self._settings_widget.update_usage(
                    prompt_tokens, completion_tokens, total_tokens,
                    self._session_tokens
                )
        except (json.JSONDecodeError, TypeError):
            pass

    @Slot()
    def _on_worker_done(self):
        if not self._expected_tool_ids:
            self._set_busy(False)
        self._worker = None

    @Slot()
    def _on_stop(self):
        """Stop the current LLM generation."""
        if self._worker is not None:
            self._worker.cancel()
        # If streaming was active, finalise whatever content we have so far
        if self._streaming_active and self._streaming_content:
            self._conversation.append({
                "role": "assistant",
                "content": self._streaming_content,
            })
            self._streaming_active = False
            self._streaming_content = ""
        self._expected_tool_ids = []
        self._pending_tool_results.clear()
        self._set_busy(False)
        self._append_message("system", "已停止生成。")

    @Slot()
    def _on_clear(self):
        self._conversation.clear()
        self.chat_history.clear()
        self.status_label.setText("")
        self._tool_round = 0
        self._pending_tool_results.clear()
        self._expected_tool_ids = []
        self._last_user_query = ""
        self._last_used_tools = False
        self._tools_used_names = []
        self._streaming_active = False
        self._streaming_content = ""
        self._stream_block_start = 0
        self._session_tokens = 0
        self._token_label.setText("")
        if hasattr(self, '_settings_widget'):
            self._settings_widget.reset_usage()
        ConfirmDialog.reset_auto_approve()
        invalidate_prompt_cache()

    @Slot(str)
    def _on_reuse_history_reply(self, reply_text):
        self._append_message("assistant", reply_text)
        self._append_message("system", "（复用历史回复）")
        self._conversation.append({"role": "assistant", "content": reply_text})
        self._switch_tab(TAB_CHAT)

    @Slot(str)
    def _on_resume_session(self, session_id):
        """Restore a full historical session into the chat so the user can continue."""
        records = self._history.get_session_records(session_id)
        if not records:
            self._append_message("system", "未找到该会话的记录。")
            self._switch_tab(TAB_CHAT)
            return

        # Clear current conversation first
        self._conversation.clear()
        self.chat_history.clear()
        self.status_label.setText("")
        self._tool_round = 0
        self._streaming_active = False
        self._streaming_content = ""

        # Rebuild conversation from history records
        for r in records:
            user_input = r.get("user_input", "")
            assistant_reply = r.get("assistant_reply", "")
            tools_used = r.get("tools_used") or []

            if user_input:
                self._append_message("user", user_input)
                self._conversation.append({"role": "user", "content": user_input})

            if tools_used:
                self._append_message("tool", "使用工具: {}".format(", ".join(tools_used)))

            if assistant_reply:
                self._append_message("assistant", assistant_reply)
                self._conversation.append({"role": "assistant", "content": assistant_reply})

        self._append_message("system",
            "已恢复历史会话 ({} 条记录)，可以继续对话。".format(len(records))
        )
        self._switch_tab(TAB_CHAT)
