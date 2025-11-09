# Packages/AgentChat/chat_plugin.py
# -------------------------------------------------------------
#  AI‑Chat plugin – two simple commands
#
#  * AiAgentCodeCommand  – create a brand‑new scratch view, write the system
#                           prompt + user prompt, then start streaming.
#
#  * AgentChatCommand    – stream on an existing chat view that already
#                           contains the tags "# --- System ---",
#                           "# --- User ---", "# --- Agent ---".
#
#  All streaming logic lives in `start_streaming()` – the single code
#  path used by both commands.
#
#  The plugin uses only Python features available in older
#  Sublime Text builds (no f‑string syntax, only .format()).
# -------------------------------------------------------------

import json
import urllib.request
import threading
import random

import sublime
import sublime_plugin

MODELS_HIGH = sublime.load_settings("agentic.sublime-settings").get("models_high")

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are an expert programming agent. Focus on correctness and simplicity."
)

# Registry of ongoing streams: view.id() → StreamingTask
_ACTIVE_STREAMERS = {}


# --------------------------------------------------------------------
# 1)  Streaming generator – talks to the local OpenAI server
# --------------------------------------------------------------------
def chat_stream(messages,
                model):
    """
    Yields `(is_reasoning, text)` for incremental stream chunks.
    At the end yields a 4‑tuple of timing metrics:
        (cache_n, prompt_n, prompt_per_second, predicted_per_second).
    """
    url = model.get("url")
    token = model.get("token")
    body = model.get("options")
    body.update({
        "messages": messages,
        "model": model.get("model"),
        "stream": True,  # required for now
    })

    data = json.dumps(body).encode("utf‑8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(token),
        },
    )

    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode("utf‑8").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                return

            try:
                evt = json.loads(payload)
            except ValueError:
                continue

            for choice in evt.get("choices", []):
                delta = choice.get("delta", {})

                # Harvest content / reasoning tokens
                if "content" in delta and delta["content"]:
                    yield (False, delta["content"])
                elif "reasoning_content" in delta and delta["reasoning_content"]:
                    yield (True, delta["reasoning_content"])
                # Final timing report
                elif not delta and "timings" in evt:
                    t = evt["timings"]
                    yield (t["cache_n"],
                           t["prompt_n"],
                           t["prompt_per_second"],
                           t["predicted_per_second"])
                    if choice.get("finish_reason") == "stop":
                        return
# Actual raw message data at end:
# b'data: {"choices":[{"finish_reason":null,"index":0,"delta":{"content":"!"}}],"created":1762670015,"id":"chatcmpl-mHDb1kfAQIhcvp8kkPeWJsO8gpTIUA3a","model":"gpt-oss","system_fingerprint":"b6925-cd5e3b575","object":"chat.completion.chunk"}\n'
# b'\n'
# b'data: {"choices":[{"finish_reason":"stop","index":0,"delta":{}}],"created":1762670015,"id":"chatcmpl-mHDb1kfAQIhcvp8kkPeWJsO8gpTIUA3a","model":"gpt-oss","system_fingerprint":"b6925-cd5e3b575","object":"chat.completion.chunk","timings":{"cache_n":89,"prompt_n":58,"prompt_ms":23.467,"prompt_per_token_ms":0.40460344827586203,"prompt_per_second":2471.5558017641797,"predicted_n":2188,"predicted_ms":13095.01,"predicted_per_token_ms":5.984922303473492,"predicted_per_second":167.0865467074863}}\n'
# b'\n'
# b'data: [DONE]\n'


# --------------------------------------------------------------------
# 2)  Background worker – streams into the view
# --------------------------------------------------------------------
class StreamingTask(threading.Thread):
    def __init__(self, view, messages, registry):
        super().__init__(daemon=True)
        self.view = view
        self.messages = messages
        self.registry = registry
        self._cancel = False

    def cancel(self):
        self._cancel = True
        self.view.settings().set("is_streaming", False)

    def run(self):
        sublime.status_message("Streaming")
        prev_reasoning = False

        self._write("\n# --- Agent ---\n")
        sublime.set_timeout(
            lambda: self.view.run_command(
                "move_to", {"to": "eof", "extend": False}), 0)

        if self.view.settings().get("agent_model") is None:
            self.view.settings().set(
                "agent_model",
                random.choice(list(MODELS_HIGH.values()))
            )

        for chunk in chat_stream(
                self.messages,
                self.view.settings().get("agent_model")):
            # Normal (2‑tuple) chunk vs. metrics (4‑tuple)
            if isinstance(chunk, tuple) and len(chunk) == 2:
                is_reasoning, text = chunk
            else:
                cache, prompt, pps, tps = chunk
                sublime.status_message("Done. cache:{} new:{} tk/s:{}".format(
                        cache, prompt, int(tps)))
                break

            if self._cancel or not self.view or not self.view.is_valid():
                self.view.set_status("streamstatus", "Interrupted")
                break

            if is_reasoning:
                if not prev_reasoning:  # first reasoning message
                    self._write("\n## --- Thinking ---\n>")
                    prev_reasoning = True
                text = text.replace("\n", "\n> ")
            else:
                if prev_reasoning:
                    self._write("\n## --- Response ---\n")
                    prev_reasoning = False

            self._write(text)

        sublime.set_timeout(self._finalise, 0)

    def _write(self, text):
        sublime.set_timeout(
            lambda c=text: self.view.run_command("append", {"characters": c}),
            0
        )

    def _finalise(self):
        if not self.view.is_valid():
            return
        self.registry.pop(self.view.id(), None)
        self._write("\n# --- User ---\n")
        self.view.settings().set("is_streaming", False)


# --------------------------------------------------------------------
# 3)  Public helper – start a streaming task on a view
# --------------------------------------------------------------------
def start_streaming(view, messages):
    view.settings().set("is_streaming", True)
    task = StreamingTask(view, messages, _ACTIVE_STREAMERS)
    _ACTIVE_STREAMERS[view.id()] = task
    task.start()


# --------------------------------------------------------------------
# 4)  Parse a view into a list of chat messages
# --------------------------------------------------------------------
def build_messages_from_text(text):
    lines = text.splitlines(True)

    messages = []
    current_role = None
    content_lines = []
    in_reasoning = False

    for line in lines:
        stripped = line.strip()

        # Block start
        if stripped.startswith("# --- "):
            if current_role and content_lines:
                msg = "".join(content_lines).rstrip("\n")
                messages.append({"role": current_role, "content": msg})

            if "System" in stripped:
                current_role = "developer"
            elif "User" in stripped:
                current_role = "user"
            elif "Agent" in stripped:
                current_role = "assistant"
            else:
                current_role = None

            content_lines = []
            continue

        # Reasoning section toggles
        if stripped.startswith("## --- "):
            if "Thinking" in stripped:
                in_reasoning = True
            elif "Response" in stripped:
                in_reasoning = False
            continue

        if in_reasoning:
            continue

        if current_role:
            content_lines.append(line)

    # Finalise the last block
    if current_role:
        msg = "".join(content_lines).rstrip("\n")
        messages.append({"role": current_role, "content": msg})

    return messages


# --------------------------------------------------------------------
# 5)  Input handler – free‑form prompt for AiAgentCodeCommand
# --------------------------------------------------------------------
class PromptInputHandler(sublime_plugin.TextInputHandler):
    def placeholder(self):
        return "Enter command string"

    def initial_text(self):
        return ""


# --------------------------------------------------------------------
# 6)  AiAgentCodeCommand – create a new window and stream
# --------------------------------------------------------------------
class AgentCodeCommand(sublime_plugin.WindowCommand):
    def input(self, args):
        return PromptInputHandler()

    def run(self, prompt):
        # New window + scratch view
        old_view = self.window.active_view()
        view = self.window.new_file()
        # Origami:
        self.window.run_command("create_pane_with_file", {"direction": "right"})
        view.set_scratch(True)
        view.set_name("Chat " + prompt[:12])
        view.settings().set("is_streaming", True)
        view.settings().set("is_agent_chat", True)
        try:
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        except Exception:
            pass

        sel = old_view.sel()
        if any(not r.empty() for r in sel):
            content = "\n...\n".join(old_view.substr(r)
                                     for r in sel if not r.empty())
        else:
            content = old_view.substr(sublime.Region(0, old_view.size()))
        user_prompt = "File: {}\n```\n{}\n```\n{}".format(
            old_view.file_name(), content, prompt)

        # Write system & user prompts to the new view
        new_chat = "# --- System ---\n{}\n# --- User ---\n{}\n".format(
            SYSTEM_PROMPT, user_prompt
        )
        view.run_command("append", {"characters": new_chat})
        messages = build_messages_from_text(new_chat)

        # Start streaming
        start_streaming(view, messages)
        sublime.status_message("Submitting prompt")


# --------------------------------------------------------------------
# 7)  AgentChatCommand – stream on an existing chat view
# --------------------------------------------------------------------
class AgentChatCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return

        if view.settings().get("is_streaming"):
            task = _ACTIVE_STREAMERS.get(view.id())
            if task:
                task.cancel()
                sublime.status_message("Streaming cancelled")
            return

        text = view.substr(sublime.Region(0, view.size()))
        messages = build_messages_from_text(text)
        if not messages:
            sublime.status_message("Chat data not found")
            # make new file
            view = self.window.new_file()
            view.set_name("Chat")
            new_chat = "# --- System ---\n{}\n# --- User ---\n".format(
                SYSTEM_PROMPT
            )
            view.run_command("append", {"characters": new_chat})
            view.run_command("move_to", {"to": "eof", "extend": False})
            view.settings().set("is_streaming", False)
            view.settings().set("is_agent_chat", True)
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
            return

        view.settings().set("is_streaming", True)
        view.settings().set("is_agent_chat", True)
        try:
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        except Exception:
            pass

        start_streaming(view, messages)
        sublime.status_message("Submitting prompt")


# --------------------------------------------------------------------
# 8)  Cancel stream command
# --------------------------------------------------------------------
class CancelStreamCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view or not view.settings().get("is_streaming"):
            return
        task = _ACTIVE_STREAMERS.get(view.id())
        if task:
            task.cancel()
            sublime.status_message("Streaming cancelled")
        else:
            view.settings().set("is_streaming", False)


# --------------------------------------------------------------------
# 9)  Clear reasoning sections from a finished chat
# --------------------------------------------------------------------
class AgentClearReasoningCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        if view.id() in _ACTIVE_STREAMERS:
            return

        text = view.substr(sublime.Region(0, view.size()))
        messages = build_messages_from_text(text)
        if not messages:
            sublime.status_message("Chat data not found")
            return

        tag_map = {
            "developer": "# --- System ---",
            "user": "# --- User ---",
            "assistant": "# --- Agent ---",
        }

        parts = []
        for msg in messages:
            tag = tag_map.get(msg["role"], "# --- Unknown ---")
            parts.append("{}\n{}\n".format(tag, msg["content"]))

        cleaned = "\n".join(parts)
        view.replace(edit, sublime.Region(0, view.size()), cleaned)
        sublime.status_message("Chat cleared")
