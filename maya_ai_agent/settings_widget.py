# -*- coding: utf-8 -*-
"""
Settings Widget - Inline settings panel (embedded in sidebar page).
Replaces the old modal SettingsDialog with an in-page configuration view.
"""

from .qt_compat import QtWidgets, QtCore, Qt
from . import config

import json
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# Provider Presets
# ---------------------------------------------------------------------------

PRESETS = [
    {
        "name": "自定义 (Custom)",
        "api_base": "",
        "model": "",
        "placeholder_key": "your-api-key",
        "hint": "手动填写所有字段。",
    },
    {
        "name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "placeholder_key": "sk-...",
        "hint": (
            "获取 Key：https://platform.deepseek.com/api_keys\n"
            "可用模型：deepseek-chat（V3）、deepseek-reasoner（R1）"
        ),
    },
    {
        "name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "placeholder_key": "AIza...",
        "hint": (
            "获取 Key：https://aistudio.google.com/apikey\n"
            "可用模型：gemini-2.5-pro、gemini-2.5-flash、gemini-2.0-flash\n"
            "Gemini 提供 OpenAI 兼容接口，直接使用即可。"
        ),
    },
    {
        "name": "Anthropic Claude",
        "api_base": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-20250514",
        "placeholder_key": "sk-ant-...",
        "hint": (
            "获取 Key：https://console.anthropic.com/settings/keys\n"
            "可用模型：claude-sonnet-4-20250514、claude-opus-4-20250514\n"
            "⚠ 注意：Claude 原生 API 格式与 OpenAI 不同，\n"
            "如需使用请配合 OpenAI 兼容代理（如 LiteLLM / one-api）。"
        ),
    },
    {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "placeholder_key": "sk-...",
        "hint": (
            "获取 Key：https://platform.openai.com/api-keys\n"
            "可用模型：gpt-4o、gpt-4o-mini、o3-mini"
        ),
    },
    {
        "name": "Ollama (本地)",
        "api_base": "http://localhost:11434/v1",
        "model": "qwen2.5:14b",
        "placeholder_key": "ollama",
        "hint": (
            "Ollama 本地部署，无需 API Key（填任意值即可）。\n"
            "先运行: ollama run qwen2.5:14b\n"
            "可用模型取决于你本地拉取了哪些。"
        ),
    },
    {
        "name": "OpenRouter",
        "api_base": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat",
        "placeholder_key": "sk-or-...",
        "hint": (
            "获取 Key：https://openrouter.ai/keys\n"
            "聚合平台，可访问几乎所有主流模型。"
        ),
    },
]


_SETTINGS_STYLE = """
QWidget#SettingsPanel {
    background-color: #1e1e1e;
}

QGroupBox {
    color: #cccccc;
    font-size: 13px;
    font-weight: bold;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #cccccc;
}

QLabel {
    color: #bbbbbb;
    font-size: 12px;
}

QLineEdit {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
    selection-background-color: #264f78;
}

QLineEdit:focus {
    border-color: #0078d4;
}

QComboBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    selection-background-color: #264f78;
}

QSpinBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}

QCheckBox {
    color: #bbbbbb;
    font-size: 12px;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #2d2d2d;
}

QCheckBox::indicator:checked {
    background-color: #0078d4;
    border-color: #0078d4;
}

QPushButton#saveBtn {
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton#saveBtn:hover {
    background-color: #1a8ae8;
}

QPushButton#testBtn {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton#testBtn:hover {
    background-color: #505050;
}

QPushButton#testBtn:disabled {
    color: #666666;
}

QPushButton#applyPresetBtn {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 12px;
}

QPushButton#applyPresetBtn:hover {
    background-color: #505050;
}

QLabel#hintLabel {
    color: #888888;
    font-size: 11px;
    background-color: #252526;
    border-radius: 4px;
    padding: 8px;
}

QLabel#statusMsg {
    color: #4ec9b0;
    font-size: 12px;
    padding: 4px 0;
}
"""


class SettingsWidget(QtWidgets.QWidget):
    """Inline settings panel that replaces the modal dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPanel")
        self.setStyleSheet(_SETTINGS_STYLE)
        self._build_ui()
        self._load_current()

    def _build_ui(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: none; }")

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        # --- Title ---
        title = QtWidgets.QLabel("设置")
        title.setStyleSheet("color: #cccccc; font-size: 16px; font-weight: bold; padding-bottom: 4px;")
        layout.addWidget(title)

        # --- Preset Group ---
        preset_group = QtWidgets.QGroupBox("快速预设")
        preset_layout = QtWidgets.QVBoxLayout(preset_group)
        preset_layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("服务商:"))
        self.preset_combo = QtWidgets.QComboBox()
        for p in PRESETS:
            self.preset_combo.addItem(p["name"])
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        row.addWidget(self.preset_combo, stretch=1)

        apply_btn = QtWidgets.QPushButton("应用")
        apply_btn.setObjectName("applyPresetBtn")
        apply_btn.clicked.connect(self._apply_preset)
        row.addWidget(apply_btn)
        preset_layout.addLayout(row)

        self.hint_label = QtWidgets.QLabel("")
        self.hint_label.setObjectName("hintLabel")
        self.hint_label.setWordWrap(True)
        self.hint_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        preset_layout.addWidget(self.hint_label)

        layout.addWidget(preset_group)

        # --- API Config Group ---
        api_group = QtWidgets.QGroupBox("API 配置")
        api_layout = QtWidgets.QFormLayout(api_group)
        api_layout.setSpacing(10)
        api_layout.setLabelAlignment(Qt.AlignRight)

        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        api_layout.addRow("API Key:", self.api_key_edit)

        self.api_base_edit = QtWidgets.QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.openai.com/v1")
        api_layout.addRow("Base URL:", self.api_base_edit)

        self.model_edit = QtWidgets.QLineEdit()
        self.model_edit.setPlaceholderText("gpt-4o")
        api_layout.addRow("模型名称:", self.model_edit)

        self.max_tokens_spin = QtWidgets.QSpinBox()
        self.max_tokens_spin.setRange(256, 128000)
        self.max_tokens_spin.setValue(4096)
        self.max_tokens_spin.setSingleStep(256)
        api_layout.addRow("最大 Tokens:", self.max_tokens_spin)

        layout.addWidget(api_group)

        # --- Options ---
        self.show_key_cb = QtWidgets.QCheckBox("显示 API Key")
        self.show_key_cb.toggled.connect(self._toggle_key_visibility)
        layout.addWidget(self.show_key_cb)

        # --- Token Usage Group ---
        usage_group = QtWidgets.QGroupBox("Token 用量统计")
        usage_layout = QtWidgets.QVBoxLayout(usage_group)
        usage_layout.setSpacing(6)

        # Current round
        self._usage_current_label = QtWidgets.QLabel("本次请求: —")
        self._usage_current_label.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        usage_layout.addWidget(self._usage_current_label)

        # Session total
        self._usage_session_label = QtWidgets.QLabel("本轮累计: 0")
        self._usage_session_label.setStyleSheet("color: #4ec9b0; font-size: 13px; font-weight: bold;")
        usage_layout.addWidget(self._usage_session_label)

        # All-time total (persisted)
        self._usage_alltime_label = QtWidgets.QLabel("历史总计: 0")
        self._usage_alltime_label.setStyleSheet("color: #dcdcaa; font-size: 13px; font-weight: bold;")
        usage_layout.addWidget(self._usage_alltime_label)

        # Breakdown bar
        self._usage_detail_label = QtWidgets.QLabel(
            "Prompt: — | Completion: — | Total: —"
        )
        self._usage_detail_label.setStyleSheet("color: #888888; font-size: 11px;")
        self._usage_detail_label.setWordWrap(True)
        usage_layout.addWidget(self._usage_detail_label)

        layout.addWidget(usage_group)

        # Load persisted all-time total
        self._alltime_tokens = int(config.get("ALLTIME_TOKENS", "0"))
        self._usage_alltime_label.setText(
            "历史总计: {} tokens".format(self._alltime_tokens)
        )

        # --- Save & Test buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        self._status_msg = QtWidgets.QLabel("")
        self._status_msg.setObjectName("statusMsg")
        btn_row.addWidget(self._status_msg)

        test_btn = QtWidgets.QPushButton("测试连接")
        test_btn.setObjectName("testBtn")
        test_btn.clicked.connect(self._on_test_connection)
        btn_row.addWidget(test_btn)

        save_btn = QtWidgets.QPushButton("保存设置")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        scroll.setWidget(content)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._on_preset_changed(0)

    # ----- Preset Logic -----------------------------------------------------

    def _on_preset_changed(self, index):
        if 0 <= index < len(PRESETS):
            self.hint_label.setText(PRESETS[index]["hint"])

    def _apply_preset(self):
        index = self.preset_combo.currentIndex()
        if index < 0 or index >= len(PRESETS):
            return
        preset = PRESETS[index]
        if preset["api_base"]:
            self.api_base_edit.setText(preset["api_base"])
        if preset["model"]:
            self.model_edit.setText(preset["model"])
        self.api_key_edit.setPlaceholderText(preset["placeholder_key"])

    def _toggle_key_visibility(self, checked):
        self.api_key_edit.setEchoMode(
            QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
        )

    # ----- Load / Save ------------------------------------------------------

    def _load_current(self):
        cfg = config.load_config(force_reload=True)
        api_key = cfg.get("OPENAI_API_KEY", "")
        if api_key == "your_api_key_here":
            api_key = ""
        self.api_key_edit.setText(api_key)

        api_base = cfg.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.api_base_edit.setText(api_base)

        model = cfg.get("OPENAI_MODEL", "gpt-4o")
        self.model_edit.setText(model)

        self.max_tokens_spin.setValue(int(cfg.get("OPENAI_MAX_TOKENS", "4096")))

        self._auto_select_preset(api_base)

    def _auto_select_preset(self, api_base):
        api_base_lower = api_base.lower().rstrip("/")
        for i, preset in enumerate(PRESETS):
            if preset["api_base"] and preset["api_base"].lower().rstrip("/") == api_base_lower:
                self.preset_combo.setCurrentIndex(i)
                return
        self.preset_combo.setCurrentIndex(0)

    def reload_config(self):
        """Public method called when switching to the settings tab."""
        self._load_current()
        self._status_msg.setText("")

    def _on_save(self):
        api_key = self.api_key_edit.text().strip()
        api_base = self.api_base_edit.text().strip()
        model = self.model_edit.text().strip()
        max_tokens = self.max_tokens_spin.value()

        if not api_base:
            api_base = "https://api.openai.com/v1"
        if not model:
            model = "gpt-4o"

        data = {
            "OPENAI_API_KEY": api_key,
            "OPENAI_API_BASE": api_base,
            "OPENAI_MODEL": model,
            "OPENAI_MAX_TOKENS": str(max_tokens),
        }
        config.save_config(data)

        if not api_key:
            self._status_msg.setStyleSheet("color: #dcdcaa; font-size: 12px;")
            self._status_msg.setText("✓ 已保存（API Key 为空，对话前请填写）")
        else:
            self._status_msg.setStyleSheet("color: #4ec9b0; font-size: 12px;")
            self._status_msg.setText("✓ 已保存")

        # Auto-clear status after 3s
        QtCore.QTimer.singleShot(3000, lambda: self._status_msg.setText(""))

    def _on_test_connection(self):
        """Test API connectivity with a minimal request."""
        api_key = self.api_key_edit.text().strip()
        api_base = self.api_base_edit.text().strip() or "https://api.openai.com/v1"
        model = self.model_edit.text().strip() or "gpt-4o"

        if not api_key:
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("请先填写 API Key")
            return

        self._status_msg.setStyleSheet("color: #888888; font-size: 12px;")
        self._status_msg.setText("测试连接中...")
        # Force UI repaint
        QtWidgets.QApplication.processEvents()

        url = api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(api_key),
        }

        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib_request.Request(url, data=data, headers=headers, method="POST")
            with urllib_request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                model_used = result.get("model", model)
                self._status_msg.setStyleSheet("color: #4ec9b0; font-size: 12px;")
                self._status_msg.setText("✓ 连接成功 (model: {})".format(model_used))
        except HTTPError as e:
            hints = {
                401: "API Key 无效",
                403: "权限不足",
                404: "端点/模型不存在",
                429: "请求过快",
            }
            hint = hints.get(e.code, "HTTP {}".format(e.code))
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("✗ 连接失败: {}".format(hint))
        except URLError as e:
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("✗ 网络错误: {}".format(e.reason))
        except Exception as e:
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("✗ 错误: {}".format(str(e)[:80]))

        QtCore.QTimer.singleShot(8000, lambda: self._status_msg.setText(""))

    # ----- Token Usage (called externally by ChatWidget) --------------------

    def update_usage(self, prompt_tokens, completion_tokens, total_tokens, session_total):
        """Update the token usage display. Called by ChatWidget._on_usage."""
        self._usage_current_label.setText(
            "本次请求: {} tokens".format(total_tokens)
        )
        self._usage_session_label.setText(
            "本轮累计: {} tokens".format(session_total)
        )
        self._usage_detail_label.setText(
            "Prompt: {} | Completion: {} | Total: {}".format(
                prompt_tokens, completion_tokens, total_tokens
            )
        )
        # Update all-time total (persisted)
        self._alltime_tokens += total_tokens
        self._usage_alltime_label.setText(
            "历史总计: {} tokens".format(self._alltime_tokens)
        )
        # Persist
        config.save_config({"ALLTIME_TOKENS": str(self._alltime_tokens)})

    def reset_usage(self):
        """Reset the token usage display (e.g. on new conversation)."""
        self._usage_current_label.setText("本次请求: —")
        self._usage_session_label.setText("本轮累计: 0")
        self._usage_detail_label.setText("Prompt: — | Completion: — | Total: —")
        # Note: alltime total is NOT reset here — it's cumulative
