# -*- coding: utf-8 -*-
"""
LLM Worker - Background thread for LLM API requests.
Runs network I/O off the main Maya thread to prevent UI freezing.
Supports OpenAI-compatible endpoints (OpenAI, DeepSeek, Gemini, Ollama, OpenRouter, etc.).

Supports both streaming (SSE) and non-streaming modes.
Streaming is enabled by default for faster perceived response.
"""

import json
import logging
import time
import traceback
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError

from .qt_compat import QThread, Signal
from . import config

log = logging.getLogger("MayaAIAgent.llm")


# Common HTTP error code explanations
_HTTP_ERROR_HINTS = {
    401: "API Key 无效或已过期，请在设置中检查。",
    402: "账户余额不足，请充值后重试。",
    403: "权限不足，可能是 API Key 没有该模型的访问权限。",
    404: "API 端点或模型名称不存在，请检查 Base URL 和模型名。",
    429: "请求频率过高，请稍后重试。",
    500: "服务端内部错误，请稍后重试。",
    502: "网关错误，服务暂时不可用。",
    503: "服务暂时不可用，请稍后重试。",
}

# Retry configuration
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.5  # seconds — will be multiplied by 2^attempt
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503}


class LLMWorker(QThread):
    """
    Background thread that sends messages to the LLM API
    and emits results via Qt signals.

    Supports streaming (SSE) for real-time text display.
    """

    # Signals for communicating back to main thread
    response_chunk = Signal(str)       # Streaming text chunk (incremental)
    response_finished = Signal(str)    # Full response (JSON with content + reasoning_content)
    tool_calls_received = Signal(str)  # JSON string of tool_calls
    error_occurred = Signal(str)       # Error message
    status_changed = Signal(str)       # Status updates ("thinking", "idle")
    usage_received = Signal(str)       # JSON string of token usage info

    def __init__(self, messages, tools=None, tool_choice="auto",
                 stream=True, parent=None):
        """
        Args:
            messages: List of message dicts [{"role": "...", "content": "..."}]
            tools: Optional list of tool schemas for Function Calling
            tool_choice: "auto" (LLM decides), "none" (force text-only), or a
                         specific tool dict.
            stream: Whether to use streaming (SSE). Default True.
        """
        super().__init__(parent)
        self.messages = messages
        self.tools = tools
        self.tool_choice = tool_choice
        self.stream = stream
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        """Execute LLM request in background thread."""
        self.status_changed.emit("thinking")

        api_key = config.get("OPENAI_API_KEY", "")
        api_base = config.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        model = config.get("OPENAI_MODEL", "gpt-4o")
        max_tokens = int(config.get("OPENAI_MAX_TOKENS", "4096"))

        if not api_key or api_key == "your_api_key_here":
            self.error_occurred.emit(
                "API Key 未配置。请点击右上角设置按钮配置你的 API Key。"
            )
            return

        # Build request payload
        payload = {
            "model": model,
            "messages": self.messages,
            "max_tokens": max_tokens,
        }

        # Attach tools schema if provided
        if self.tools:
            payload["tools"] = self.tools
            payload["tool_choice"] = self.tool_choice

        # Enable streaming
        if self.stream:
            payload["stream"] = True
            # Required for providers to include token usage in stream chunks.
            # Some providers (e.g. older DeepSeek) may not support this; we
            # handle the 400 fallback below.
            payload["stream_options"] = {"include_usage": True}

        url = api_base.rstrip("/") + "/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(api_key),
        }

        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

            last_error = None
            for attempt in range(_MAX_RETRIES):
                if self._is_cancelled:
                    return

                try:
                    req = urllib_request.Request(url, data=data, headers=headers, method="POST")
                    with urllib_request.urlopen(req, timeout=180) as resp:
                        if self._is_cancelled:
                            return
                        if self.stream:
                            self._handle_stream(resp)
                        else:
                            self._handle_non_stream(resp)
                    return  # Success — exit retry loop

                except HTTPError as e:
                    # If 400 and we have stream_options, retry without it
                    if e.code == 400 and "stream_options" in payload:
                        log.debug("Provider rejected stream_options, retrying without it")
                        try:
                            e.read()
                        except Exception:
                            pass
                        del payload["stream_options"]
                        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        continue

                    if e.code in _RETRYABLE_HTTP_CODES and attempt < _MAX_RETRIES - 1:
                        wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                        self.status_changed.emit(
                            "retry ({}/{}) — waiting {:.0f}s...".format(
                                attempt + 1, _MAX_RETRIES, wait))
                        time.sleep(wait)
                        last_error = e
                        continue
                    # Non-retryable or last attempt
                    self._handle_http_error(e)
                    return

                except URLError as e:
                    if attempt < _MAX_RETRIES - 1:
                        wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                        self.status_changed.emit(
                            "retry ({}/{}) — waiting {:.0f}s...".format(
                                attempt + 1, _MAX_RETRIES, wait))
                        time.sleep(wait)
                        last_error = e
                        continue
                    self.error_occurred.emit(
                        "网络连接错误 (重试 {} 次后失败): {}\n请检查 API Base URL 是否正确，或网络是否畅通。".format(
                            _MAX_RETRIES, e.reason
                        )
                    )
                    return

            # Should not reach here, but just in case
            if last_error:
                self.error_occurred.emit("重试 {} 次后仍然失败。".format(_MAX_RETRIES))
        except json.JSONDecodeError as e:
            self.error_occurred.emit("JSON 解析错误: {}\n服务端可能返回了非标准响应。".format(str(e)))
        except Exception:
            self.error_occurred.emit(
                "未知错误:\n{}".format(traceback.format_exc())
            )
        finally:
            self.status_changed.emit("idle")

    def _handle_stream(self, resp):
        """Handle Server-Sent Events (SSE) streaming response."""
        content_chunks = []
        reasoning_chunks = []
        tool_calls_accum = {}  # {index: {"id":..., "type":..., "function": {"name":..., "arguments":...}}}
        usage_info = None

        for raw_line in resp:
            if self._is_cancelled:
                return

            line = raw_line.decode("utf-8", errors="replace").strip()

            if not line:
                continue
            if line.startswith(":"):
                continue  # SSE comment
            if not line.startswith("data: "):
                continue

            data_str = line[6:]  # Remove "data: " prefix

            if data_str == "[DONE]":
                break

            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Some providers include usage in streaming chunks
            chunk_usage = chunk.get("usage")
            if chunk_usage:
                usage_info = chunk_usage

            choices = chunk.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})

            # Content text
            text = delta.get("content")
            if text:
                content_chunks.append(text)
                self.response_chunk.emit(text)

            # Reasoning content (DeepSeek-Reasoner)
            reasoning = delta.get("reasoning_content")
            if reasoning:
                reasoning_chunks.append(reasoning)

            # Tool calls (streamed incrementally)
            tc_deltas = delta.get("tool_calls")
            if tc_deltas:
                for tc_delta in tc_deltas:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {
                            "id": tc_delta.get("id", ""),
                            "type": tc_delta.get("type", "function"),
                            "function": {
                                "name": "",
                                "arguments": "",
                            },
                        }
                    entry = tool_calls_accum[idx]
                    if tc_delta.get("id"):
                        entry["id"] = tc_delta["id"]
                    func_delta = tc_delta.get("function", {})
                    if func_delta.get("name"):
                        entry["function"]["name"] += func_delta["name"]
                    if func_delta.get("arguments"):
                        entry["function"]["arguments"] += func_delta["arguments"]

        # Emit usage info if available
        if usage_info:
            self.usage_received.emit(json.dumps(usage_info, ensure_ascii=False))

        # Assemble final result
        full_content = "".join(content_chunks)
        full_reasoning = "".join(reasoning_chunks)

        if tool_calls_accum:
            tool_calls = [tool_calls_accum[i] for i in sorted(tool_calls_accum.keys())]
            payload = {
                "tool_calls": tool_calls,
                "content": full_content,
                "reasoning_content": full_reasoning,
            }
            self.tool_calls_received.emit(json.dumps(payload, ensure_ascii=False))
        else:
            resp_payload = {
                "content": full_content,
                "reasoning_content": full_reasoning,
            }
            self.response_finished.emit(json.dumps(resp_payload, ensure_ascii=False))

    def _handle_non_stream(self, resp):
        """Handle non-streaming response (original behavior)."""
        body = resp.read().decode("utf-8")
        result = json.loads(body)

        # Emit usage info
        usage_info = result.get("usage")
        if usage_info:
            self.usage_received.emit(json.dumps(usage_info, ensure_ascii=False))

        choices = result.get("choices", [])
        if not choices:
            self.error_occurred.emit("LLM 返回了空的 choices。")
            return

        message = choices[0].get("message", {})

        if self._is_cancelled:
            return

        reasoning_content = message.get("reasoning_content") or ""

        tool_calls = message.get("tool_calls")
        if tool_calls:
            content = message.get("content") or ""
            payload = {
                "tool_calls": tool_calls,
                "content": content,
                "reasoning_content": reasoning_content,
            }
            self.tool_calls_received.emit(json.dumps(payload, ensure_ascii=False))
        else:
            content = message.get("content", "")
            resp_payload = {
                "content": content,
                "reasoning_content": reasoning_content,
            }
            self.response_finished.emit(json.dumps(resp_payload, ensure_ascii=False))

    def _handle_http_error(self, e):
        """Handle HTTP errors with detailed messages."""
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass

        detail = ""
        try:
            err_json = json.loads(error_body)
            err_obj = err_json.get("error", err_json)
            detail = err_obj.get("message", "")
        except Exception:
            detail = error_body[:500] if error_body else ""

        hint = _HTTP_ERROR_HINTS.get(e.code, "")
        msg_parts = ["HTTP 错误 {}: {}".format(e.code, e.reason)]
        if hint:
            msg_parts.append(hint)
        if detail:
            msg_parts.append("详情: {}".format(detail))

        error_msg = "\n".join(msg_parts)
        log.error("LLM API error: %s", error_msg)
        self.error_occurred.emit(error_msg)
