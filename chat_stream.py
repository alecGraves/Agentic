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
#  All API call logic lives in `_chat_stream()` – the single code
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
    settings = sublime.load_settings("agentic.sublime-settings")
    if capability is None:
        capability = settings.get("default_models")
    capable_models = settings.get(capability)
    models = settings.get("models")
    model = random.choice([models[m] for m in capable_models])
    print(model)
    return model


def _chat_stream(messages, model):
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


class StreamingTask(threading.Thread):
    """Background worker – streams into the view"""

    def __init__(self, view, messages, model, registry):
        super().__init__(daemon=True)
        self.view = view
        self.messages = messages
        self.registry = registry
        self._cancel = False
        self.show_reasoning = sublime.load_settings(
            "agentic.sublime-settings").get("show_reasoning")

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

        for chunk in _chat_stream(
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
    task = StreamingTask(view, messages, model, _ACTIVE_STREAMERS)
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

def _rebuild_text(messages):
    parts = []
    for m in messages:
        tag = tag_map.get(m["role"])
        if not tag:
            continue
        parts.append("{}\n{}\n".format(tag, m["content"].strip()))
    return "\n".join(parts)[:-1]


class PromptInputHandler(sublime_plugin.TextInputHandler):
    """Input handler – free‑form prompt for AiAgentCodeCommand"""

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
        new_chat = "# --- System ---\n\n{}\n# --- User ---\n{}\n".format(
            sublime.load_settings("agentic.sublime-settings").get("default_prompt"),
            user_prompt
        )
        view.run_command("append", {"characters": new_chat})
        messages = _build_messages_from_text(new_chat)

        # Start streaming
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
        try:
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        except Exception:
            pass

        start_streaming(view, messages)
        sublime.status_message("Submitting prompt")


class AgentNewChatCommand(sublime_plugin.WindowCommand):
    """Open a new chat window"""

    def run(self):
        view = self.window.active_view()
        if not view:
            return

        view = self.window.new_file()
        # view.set_scratch(True)  # if we make a new chat, save it by default.
        view.set_name("Chat")
        view.settings().set("is_streaming", False)
        view.settings().set("is_agent_chat", True)

        try:
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        except Exception:
            pass

        view.set_name("Chat")
        new_chat = "# --- System ---\n{}\n\n# --- User ---\n".format(
            sublime.load_settings("agentic.sublime-settings").get("default_prompt")
        )
        view.run_command("append", {"characters": new_chat})
        view.run_command("move_to", {"to": "eof", "extend": False})
        return


class AgentCloneChatCommand(sublime_plugin.WindowCommand):
    """Create a new chat from an existing one"""

    def run(self):
        view = self.window.active_view()
        if not view:
            return

        text = view.substr(sublime.Region(0, view.size()))
        messages = _build_messages_from_text(text)

        if messages is None:
            sublime.status_message("Chat data not found")
            self.window.run_command("agent_new_chat")
            return

        view = self.window.new_file()
        view.set_name("Chat")
        view.settings().set("is_streaming", False)
        view.settings().set("is_agent_chat", True)
        try:
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        except Exception:
            pass

        parts = []
        for msg in messages:
            tag = TAG_MAP.get(msg["role"], None)
            if tag is None:
                continue
            parts.append("{}\n{}\n".format(tag, msg["content"].strip()))

        # remove empty/in-progress assistant
        if parts[-1].startswith(TAG_MAP["assistant"]) and len(parts[-1]) < 19:
            parts = parts[:-1]

        cleaned = "\n".join(parts)[:-1]
        view.run_command("append", {"characters": cleaned})
        view.run_command("move_to", {"to": "eof", "extend": False})


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

        parts = []
        for msg in messages:
            tag = TAG_MAP.get(msg["role"], None)
            if tag is None:
                continue
            parts.append("{}\n{}\n".format(tag, msg["content"].strip()))

        cleaned = "\n".join(parts)[:-1]
        view.replace(edit, sublime.Region(0, view.size()), cleaned)
        sublime.status_message("Chat reasoning cleared")


class AgentActionCommand(sublime_plugin.WindowCommand):
    """Run a user-defined action:
    e.g. { "models": "models_high",
           "system": "You are an expert.",
           "prompt": "Turn this code into haiku." }
    """

    def run(self):
        self.actions = self._load_actions()
        if not self.actions:
            sublime.error_message(
                "agentic.sublime-settings contains no actions.\n"
                'Add a JSON array under the key `"actions"`.'
            )
            return

        self.window.show_quick_panel(
            list(self.actions.keys()),
            self.run_action  # callback called with the index chosen by the user
        )

    # ----------  Callback ----------
    def run_action(self, index):
        """Called when the user picks an item (or cancels)."""

        ## 1. Load selected prompt to use for action
        if index == -1:  # user pressed Escape
            return
        action_name = list(self.actions.keys())[index]
        chosen = self.actions[action_name]
        settings = sublime.load_settings("agentic.sublime-settings")
        models_list = chosen["models"]
        system_prompt = chosen["system"]
        prompt = chosen["prompt"]

        # 2. new window + scratch view
        old_view = self.window.active_view()
        view = self.window.new_file()
        # Origami:
        self.window.run_command("create_pane_with_file", {"direction": "right"})

        view.set_scratch(True)
        view.set_name("Chat " + action_name[:12])
        view.settings().set("is_streaming", True)
        view.settings().set("is_agent_chat", True)
        try:
            view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        except Exception:
            pass

        # 3. Load selected text
        sel = old_view.sel()  # store user highlighted (if any)
        if any(not r.empty() for r in sel):  # join multiple selections
            content = "\n...\n".join(old_view.substr(r)
                                     for r in sel if not r.empty())
        else:  # grab entire file
            content = old_view.substr(sublime.Region(0, old_view.size()))
        user_prompt = "File: {}\n```\n{}\n```\n{}".format(
            old_view.file_name(), content, prompt)

        # 4. Write system & user prompts and prepare message
        new_chat = "# --- System ---\n\n{}\n# --- User ---\n{}\n".format(
            system_prompt,
            user_prompt
        )
        view.run_command("append", {"characters": new_chat})
        messages = _build_messages_from_text(new_chat)

        # 5. Call LLM
        model = _pick_model(models_list)
        start_streaming(view, messages, model)
        sublime.status_message("Submitting prompt")

    def _load_actions(self):
        return sublime.load_settings("agentic.sublime-settings").get("actions")

