# -*- coding: utf-8 -*-
"""
History Widget - UI for browsing and searching chat history.

Provides a page that shows all past conversations with:
    - Real-time keyword search
    - Session grouping
    - Expandable record details
    - Click to reuse reply
"""

import datetime

from .qt_compat import (
    QtWidgets, QtCore, QtGui, Signal, Slot, Qt,
)
from .history_manager import HistoryManager


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

_HISTORY_STYLE = """
QWidget#HistoryPanel {
    background-color: #1e1e1e;
}

QLineEdit#historySearch {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 8px 12px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    selection-background-color: #264f78;
}

QLineEdit#historySearch:focus {
    border-color: #0078d4;
}

QTreeWidget#historyTree {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 12px;
    alternate-background-color: #222222;
    outline: none;
}

QTreeWidget#historyTree::item {
    padding: 6px 8px;
    border-bottom: 1px solid #2a2a2a;
}

QTreeWidget#historyTree::item:selected {
    background-color: #264f78;
}

QTreeWidget#historyTree::item:hover {
    background-color: #2a2d2e;
}

QHeaderView::section {
    background-color: #252526;
    color: #aaaaaa;
    border: none;
    border-bottom: 1px solid #3c3c3c;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: bold;
}

QLabel#statsLabel {
    color: #666666;
    font-size: 11px;
    padding: 2px 8px;
}

QPushButton#historyBtn {
    background-color: #2d2d2d;
    color: #bbbbbb;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 12px;
}

QPushButton#historyBtn:hover {
    background-color: #3c3c3c;
    color: #d4d4d4;
}

QPushButton#reuseBtn {
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#reuseBtn:hover {
    background-color: #1a8ae8;
}

QTextEdit#detailView {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    border-top: 1px solid #333333;
    padding: 12px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 12px;
}

QLabel#historyTitle {
    color: #cccccc;
    font-size: 13px;
    font-weight: bold;
    padding: 0 4px;
}
"""


class HistoryWidget(QtWidgets.QWidget):
    """
    History browsing and search widget.
    Used as a page in the sidebar stack.
    """

    reuse_reply = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryPanel")
        self.setStyleSheet(_HISTORY_STYLE)
        self._manager = HistoryManager.instance()
        self._all_records = []
        self._build_ui()
        self._load_history()

    # ----- UI Construction -------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Top bar ---
        top_bar = QtWidgets.QFrame()
        top_bar.setStyleSheet("QFrame { background-color: #252526; border-bottom: 1px solid #333333; }")
        top_bar.setFixedHeight(38)
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setSpacing(6)

        title = QtWidgets.QLabel("历史记录")
        title.setObjectName("historyTitle")
        top_layout.addWidget(title)
        top_layout.addStretch()

        refresh_btn = QtWidgets.QPushButton("刷新")
        refresh_btn.setObjectName("historyBtn")
        refresh_btn.clicked.connect(self._load_history)
        top_layout.addWidget(refresh_btn)

        clear_btn = QtWidgets.QPushButton("清除全部")
        clear_btn.setObjectName("historyBtn")
        clear_btn.clicked.connect(self._on_clear_history)
        top_layout.addWidget(clear_btn)

        layout.addWidget(top_bar)

        # --- Search ---
        search_container = QtWidgets.QWidget()
        search_container.setStyleSheet("background-color: #1e1e1e;")
        search_layout = QtWidgets.QHBoxLayout(search_container)
        search_layout.setContentsMargins(12, 8, 12, 8)

        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setObjectName("historySearch")
        self._search_input.setPlaceholderText("搜索历史记录 (关键词、代码、工具名)...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input)

        layout.addWidget(search_container)

        # --- Splitter: tree + detail ---
        splitter = QtWidgets.QSplitter(Qt.Vertical)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #333333;
                height: 2px;
            }
        """)

        # Record tree
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setObjectName("historyTree")
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setHeaderLabels(["时间", "用户输入", "AI 回复", "工具"])
        self._tree.setColumnCount(4)
        header = self._tree.header()
        header.resizeSection(0, 110)
        header.resizeSection(1, 160)
        header.resizeSection(2, 180)
        header.resizeSection(3, 80)
        header.setStretchLastSection(True)
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._tree.currentItemChanged.connect(self._on_item_selected)
        splitter.addWidget(self._tree)

        # Detail view
        self._detail_view = QtWidgets.QTextEdit()
        self._detail_view.setObjectName("detailView")
        self._detail_view.setReadOnly(True)
        self._detail_view.setPlaceholderText("选择一条记录查看详情...")
        splitter.addWidget(self._detail_view)

        splitter.setSizes([350, 180])
        layout.addWidget(splitter, stretch=1)

        # --- Bottom bar ---
        bottom_bar = QtWidgets.QFrame()
        bottom_bar.setStyleSheet("QFrame { background-color: #252526; border-top: 1px solid #333333; }")
        bottom_layout = QtWidgets.QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 6, 12, 6)

        self._stats_label = QtWidgets.QLabel("")
        self._stats_label.setObjectName("statsLabel")
        bottom_layout.addWidget(self._stats_label)
        bottom_layout.addStretch()

        reuse_btn = QtWidgets.QPushButton("复用此回复")
        reuse_btn.setObjectName("reuseBtn")
        reuse_btn.setToolTip("将选中记录的 AI 回复发送到对话中")
        reuse_btn.clicked.connect(self._on_reuse)
        bottom_layout.addWidget(reuse_btn)

        layout.addWidget(bottom_bar)

    # ----- Data Loading ----------------------------------------------------

    @Slot()
    def _load_history(self):
        self._all_records = self._manager.get_all_records()
        keyword = self._search_input.text().strip()
        if keyword:
            self._filter_and_display(keyword)
        else:
            self._populate_tree(self._all_records)
        self._update_stats()

    def _populate_tree(self, records):
        self._tree.clear()

        for r in reversed(records):
            ts_str = r.get("timestamp", "")
            try:
                dt = datetime.datetime.fromisoformat(ts_str)
                time_display = dt.strftime("%m-%d %H:%M")
            except (ValueError, TypeError):
                time_display = ts_str[:16] if ts_str else "?"

            user_input = r.get("user_input", "")
            reply = r.get("assistant_reply", "")
            tools = ", ".join(r.get("tools_used") or [])
            if r.get("is_shortcut"):
                tools = "⚡" + tools if tools else "⚡"

            user_short = user_input[:40] + ("..." if len(user_input) > 40 else "")
            reply_short = reply[:50] + ("..." if len(reply) > 50 else "")

            item = QtWidgets.QTreeWidgetItem([
                time_display, user_short, reply_short, tools
            ])
            item.setData(0, Qt.UserRole, r)
            self._tree.addTopLevelItem(item)

    def _update_stats(self):
        stats = self._manager.get_stats()
        self._stats_label.setText(
            "共 {} 条 | {} 会话 | Q&A {} | 工具 {}".format(
                stats["total_records"],
                stats["total_sessions"],
                stats["qa_records"],
                stats["tool_records"],
            )
        )

    # ----- Search ----------------------------------------------------------

    @Slot(str)
    def _on_search(self, keyword):
        self._filter_and_display(keyword)

    def _filter_and_display(self, keyword):
        if not keyword:
            self._populate_tree(self._all_records)
            return
        results = self._manager.search(keyword)
        self._populate_tree(list(reversed(results)))

    # ----- Detail View -----------------------------------------------------

    @Slot(QtWidgets.QTreeWidgetItem, QtWidgets.QTreeWidgetItem)
    def _on_item_selected(self, current, previous):
        if current is None:
            self._detail_view.clear()
            return

        record = current.data(0, Qt.UserRole)
        if not record:
            return

        ts = record.get("timestamp", "N/A")
        user = record.get("user_input", "")
        reply = record.get("assistant_reply", "")
        tools = record.get("tools_used") or []
        session = record.get("session_id", "N/A")
        is_shortcut = record.get("is_shortcut", False)

        html = (
            '<div style="color: #d4d4d4; font-size: 13px; line-height: 1.6;">'
            '<div style="color: #666; font-size: 11px; margin-bottom: 8px;">'
            '{ts} · {session} · {type_str}</div>'
            '<div style="background: #1a1a2e; padding: 10px 12px; border-radius: 6px; '
            'border-left: 3px solid #569cd6; margin-bottom: 8px;">'
            '<div style="color: #569cd6; font-size: 11px; font-weight: bold; margin-bottom: 4px;">🧑 用户</div>'
            '<div style="white-space: pre-wrap;">{user}</div></div>'
            '<div style="background: #1a2e1a; padding: 10px 12px; border-radius: 6px; '
            'border-left: 3px solid #4ec9b0;">'
            '<div style="color: #4ec9b0; font-size: 11px; font-weight: bold; margin-bottom: 4px;">🤖 AI</div>'
            '<div style="white-space: pre-wrap;">{reply}</div></div>'
        ).format(
            ts=self._escape(ts),
            session=self._escape(session[:8]),
            type_str="⚡快捷" if is_shortcut else (
                "🔧 " + ", ".join(tools) if tools else "💬 Q&A"
            ),
            user=self._escape(user),
            reply=self._escape(reply),
        )

        if tools:
            html += (
                '<div style="margin-top: 8px; color: #dcdcaa; font-size: 11px;">'
                '🔧 {}</div>'
            ).format(self._escape(", ".join(tools)))

        html += '</div>'
        self._detail_view.setHtml(html)

    @staticmethod
    def _escape(text):
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
        )

    # ----- Actions ---------------------------------------------------------

    @Slot()
    def _on_reuse(self):
        current = self._tree.currentItem()
        if current is None:
            return
        record = current.data(0, Qt.UserRole)
        if record:
            reply = record.get("assistant_reply", "")
            if reply:
                self.reuse_reply.emit(reply)

    @Slot()
    def _on_clear_history(self):
        result = QtWidgets.QMessageBox.question(
            self,
            "确认清除",
            "确定要清除所有历史记录吗？此操作不可撤销。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self._manager.clear_all()
            self._load_history()
            self._detail_view.clear()

    # ----- Public API ------------------------------------------------------

    def refresh(self):
        self._load_history()
