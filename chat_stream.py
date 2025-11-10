# Packages/AgentChat/chat_plugin.py
# -------------------------------------------------------------
#  Agentic AI plugin: three primary commands
#
#  * AI Agent        – Execute an arbitrary prompt providing a code
#                       snippet or file
#
#  * AI Agent Action – Execute user-defined custom agent action
#                       on a custom code section.
#
#  * AI Agent Chat   – Stream on an existing chat view that already
#                       contains the tags "# --- System ---",
#                       "# --- User ---", "# --- Agent ---".
#                       Run with [ctrl/cmd] + [enter] in a chat file.
#
#  Supplemental chat management commands
#
#  * AI Agent Clear Reasoning  – Erase reasoning output from a chat
#
#  * AI Agent Clone Chat  – Create a copy of the current chat
#
#  * AI Agent New Chat    – Prepare a new chat file
#
#  All API call logic lives in `chat_stream()` – the single code
#  path used by all three commands.
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

CHARS_PER_TOKEN = 4.4  # Based on python+english data

# Registry of ongoing streams: view.id() → StreamingTask
_ACTIVE_STREAMERS = {}

# Tags for chat file
TAG_MAP = {
    "developer": "# --- System ---",
    "user": "# --- User ---",
    "assistant": "# --- Agent ---",
}


def _pick_model(capability=None):
    """Return a random model from the provided model list string"""
    settings = sublime.load_settings("Agentic.sublime-settings")
    if capability is None:
        capability = settings.get("default_models")
    capable_models = settings.get(capability)
    models = settings.get("models")
    model = random.choice([models[m] for m in capable_models])
    print(model)
    return model


def chat_stream(messages, model):
    """
    Query an OpenAI server given messages and a model configuration.
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
    })
    stream = body["stream"]

    data = json.dumps(body).encode("utf‑8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(token),
        },
    )

    if not stream:
        resp = urllib.request.urlopen(req)
        resp = [json.loads(str(r.decode("utf‑8").strip())) for r in resp][0]
        m = resp["choices"][0]["message"]
        if "reasoning_content" in m:
            yield (True, m["reasoning_content"])
        if "content" in m:
            yield (False, m["content"])
        if "timings" in resp:
            t = resp["timings"]
            yield (t["cache_n"],
                   t["prompt_n"],
                   t["prompt_per_second"],
                   t["predicted_per_second"])
        return

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


class AgentStreamingTask(threading.Thread):
    """Background worker – streams into the view"""

    def __init__(self, view, messages, model, registry):
        super().__init__(daemon=True)
        self.view = view
        self.messages = messages
        self.registry = registry
        self._cancel = False
        if model:
            self.view.settings().set("agent_model", model)
        self.show_reasoning = sublime.load_settings(
            "Agentic.sublime-settings").get("show_reasoning")

    def cancel(self):
        self._cancel = True
        self.view.settings().set("is_streaming", False)

    def run(self):
        sublime.status_message("Streaming")
        prev_reasoning = False

        self._write("\n\n# --- Agent ---\n")
        sublime.set_timeout(
            lambda: self.view.run_command(
                "move_to", {"to": "eof", "extend": False}), 0)

        if self.view.settings().get("agent_model") is None:
            self.view.settings().set(
                "agent_model",
                _pick_model()
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
                if not self.show_reasoning:
                    continue
                if not prev_reasoning:  # first reasoning message
                    self._write("\n## --- Thinking ---\n>")
                    prev_reasoning = True
                text = text.replace("\n", "\n> ")
            else:
                if prev_reasoning:
                    self._write("\n\n## --- Response ---\n")
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
        self._write("\n\n# --- User ---\n")
        self.view.settings().set("is_streaming", False)


def start_streaming(view, messages, model=None):
    """Public helper – start a streaming task on a view"""
    view.settings().set("is_streaming", True)
    task = AgentStreamingTask(view, messages, model, _ACTIVE_STREAMERS)
    _ACTIVE_STREAMERS[view.id()] = task
    task.start()


def _build_messages_from_text(text):
    """Parse a view into a list of chat messages"""
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


def _rebuild_text(messages, strip_active=False):
    """Reconstructs chat text from message list"""
    if not messages:
        return ""
    parts = []
    for m in messages:
        tag = TAG_MAP.get(m["role"])
        if not tag:
            continue
        parts.append("{}\n{}\n".format(tag, m["content"].strip()))
    if strip_active and parts[-1].startswith(TAG_MAP["assistant"]) \
            and len(parts[-1]) < 19:
        parts = parts[:-1]
    return "\n".join(parts)[:-1]


def _create_chat(window, name, initial="",
                 temporary=True, create_pane=True, pane_dir="right"):
    view = window.new_file()
    if create_pane:
        window.set_layout({
            "cols":  [0.0, 0.5, 1.0],
            "rows":  [0.0, 1.0],
            "cells": [[0, 0, 1, 1],  # left group
                      [1, 0, 2, 1]]  # right group
        })
        right_group = window.num_groups() - 1
        window.set_view_index(view, right_group, 0)  # move file
        window.focus_group(right_group)
        # # Origami:
        # window.run_command("create_pane_with_file", {"direction": pane_dir})
    if temporary:
        view.set_scratch(True)
    view.set_name(name)
    view.settings().set("is_agent_chat", True)
    view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
    if initial:
        view.run_command("append", {"characters": initial})
        sublime.set_timeout(
            lambda: view.run_command("move_to", {"to": "eof", "extend": False}),
            0)
    return view


def _read_selection(view):
    """Load user-selected data or file"""
    sel = view.sel()
    if any(not r.empty() for r in sel):
        content = "\n...\n".join(view.substr(r)
                                 for r in sel if not r.empty())
    else:  # load entire file:
        content = view.substr(sublime.Region(0, view.size()))
    return content


class PromptInputHandler(sublime_plugin.TextInputHandler):
    """Input handler – free‑form prompt for AgentCodeCommand"""

    def placeholder(self):
        return "Enter command string"

    def initial_text(self):
        return ""


class AgentCodeCommand(sublime_plugin.WindowCommand):
    """Start a new chat based on highlighted text"""
    def input(self, args):
        return PromptInputHandler()

    def run(self, prompt):
        # New window + scratch view
        old = self.window.active_view()

        content = _read_selection(old)
        user_prompt = "File: {}\n```\n{}\n```\n{}".format(
            old.file_name(), content, prompt)
        new_chat = "# --- System ---\n{}\n\n# --- User ---\n{}\n".format(
            sublime.load_settings("Agentic.sublime-settings").get("default_prompt"),
            user_prompt
        )

        view = _create_chat(self.window, "Chat " + prompt[:12],
                            initial=new_chat)

        messages = _build_messages_from_text(new_chat)

        # Start agent
        start_streaming(view, messages)
        sublime.status_message("Submitting prompt")


class AgentChatCommand(sublime_plugin.WindowCommand):
    """Interact with an existing chat file"""
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
        messages = _build_messages_from_text(text)
        if not messages:
            sublime.status_message("Chat data not found")
            self.window.run_command("agent_new_chat")
            return

        view.settings().set("is_streaming", True)
        view.settings().set("is_agent_chat", True)
        view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")

        start_streaming(view, messages)
        sublime.status_message("Submitting prompt")


class AgentNewChatCommand(sublime_plugin.WindowCommand):
    """Open a new chat window"""
    def run(self):
        if not self.window.active_view():
            return
        new_chat = "# --- System ---\n{}\n\n# --- User ---\n".format(
            sublime.load_settings("Agentic.sublime-settings").get("default_prompt")
        )
        view = _create_chat(self.window, "Chat", new_chat, create_pane=False)


class AgentCloneChatCommand(sublime_plugin.WindowCommand):
    """Create a new chat from an existing one"""
    def run(self):
        view = self.window.active_view()
        if not view:
            return
        text = view.substr(sublime.Region(0, view.size()))
        messages = _build_messages_from_text(text)
        if not messages:
            sublime.status_message("Chat data not found")
            self.window.run_command("agent_new_chat")
            return
        cleaned = _rebuild_text(messages, strip_active=True)
        view = _create_chat(self.window, "Chat", cleaned, create_pane=False)


class CancelStreamCommand(sublime_plugin.WindowCommand):
    """Cancel an active stream command"""
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


class AgentClearReasoningCommand(sublime_plugin.TextCommand):
    """Clear reasoning sections from a finished chat"""
    def run(self, edit):
        view = self.view
        if view.id() in _ACTIVE_STREAMERS:
            return
        text = view.substr(sublime.Region(0, view.size()))
        messages = _build_messages_from_text(text)
        if not messages:
            sublime.status_message("Chat data not found")
            return
        cleaned = _rebuild_text(messages)
        view.replace(edit, sublime.Region(0, view.size()), cleaned)
        sublime.status_message("Chat reasoning cleared")


class AgentActionCommand(sublime_plugin.WindowCommand):
    """Run a user-defined action - see Agentic.sublime-settings"""
    def run(self):
        self.actions = self._load_actions()
        if not self.actions:
            sublime.error_message(
                "Agentic.sublime-settings contains no actions.\n"
                'Add a JSON array under the key `"actions"`.'
            )
            return

        self.window.show_quick_panel(
            list(self.actions.keys()),
            self.run_action  # callback called with the index chosen by the user
        )

    def run_action(self, index):
        """Called when the user picks an item (or cancels)."""
        if index == -1:  # user pressed Escape
            return
        action_name = list(self.actions.keys())[index]
        chosen = self.actions[action_name]
        settings = sublime.load_settings("Agentic.sublime-settings")
        models_list = chosen["models"]
        system_prompt = chosen["system"]
        prompt = chosen["prompt"]

        old = self.window.active_view()
        content = _read_selection(old)
        user_prompt = "File: {}\n```\n{}\n```\n{}".format(
            old.file_name(), content, prompt)
        new_chat = "# --- System ---\n{}\n\n# --- User ---\n{}\n".format(
            system_prompt, user_prompt)

        view = _create_chat(self.window, "Chat " + action_name[:12], new_chat)

        messages = _build_messages_from_text(new_chat)
        model = _pick_model(models_list)
        start_streaming(view, messages, model)
        sublime.status_message("Submitting prompt")

    def _load_actions(self):
        return sublime.load_settings("Agentic.sublime-settings").get("actions")
