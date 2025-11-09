# # /Packages/User/chat_stream.py
# # -------------------------------------------------------------
# #  Streams something into a brand‑new *view* in a freshly opened
# #  window.  It works exactly like the “Build → Run” workflow:
# # This is some example text that I highlighted
# #     • Open a new window ( */Windows → New Window* ).
# #     • Create an empty (scratch) view inside that window.
# #     • Ask the user for a “command string” – just a free‑form text.
# #     • Grab the selected text (or the whole file if nothing is
# #       selected).
# #     • Run a **background thread** that feeds the generator a chunk
# #       at a time into the view.
# #     • The user can kill the process by pressing **`c`** while the
# #       view is focused.
# # -------------------------------------------------------------

# import sublime
# import sublime_plugin
# import threading
# import time
# import json
# import urllib.request
# import random

# ports = ["12899", "12899", "12900", "12901", "12902", "12902", "12902"]

# # --------------------------------------------------------------------
# # 1)  OpenAI API output streamer
# # --------------------------------------------------------------------
# def chat_stream(prompt, system="You are an expert programming agent. Focus on correctness and performance.",
#                 port=None, token="000000000000"):
#     """
#     Yields (is_reasoning, text) for every chunk that contains
#     a delta.content or delta.reasoning_content.

#     When the stream ends (finish_reason == "stop") it returns a list
#     with the four requested metrics:

#     ('cache_n', 'prompt_n', 'prompt_per_second', 'predicted_per_second')
#     """
#     if port is None:
#         port = random.choice(ports)
#     url = 'http://127.0.0.1:{}/v1/chat/completions'.format(port)

#     if type(prompt) is list:
#         if prompt[0]["role"] != "developer":
#             prompt = [{"role": "developer", "content": str(system)}] + prompt
#         body = {
#             "model": "gpt-oss",
#             "reasoning": {"effort": "high"},
#             "messages": prompt,
#             "stream": True
#         }
#     else:
#         body = {
#             "model": "gpt-oss",
#             "reasoning": {"effort": "high"},
#             "messages": [
#                 {"role": "developer", "content": str(system)},
#                 {"role": "user",     "content": str(prompt)}
#             ],
#             "stream": True
#         }

#     data = json.dumps(body).encode("utf-8")
#     req = urllib.request.Request(
#         url,
#         data=data,
#         headers={
#             "Content-Type": "application/json",
#             "Authorization": "Bearer {}".format(token)
#         },
#     )

#     meta = (0, 0, 0.0, 0.0)
#     with urllib.request.urlopen(req) as resp:
#         for raw_line in resp:
#             line = raw_line.decode("utf-8")
#             if not line.startswith("data: "):
#                 continue
#             payload = line[6:].strip()
#             if payload == "[DONE]":
#                 break
#             try:
#                 evt = json.loads(payload)
#             except Exception:
#                 continue

#             for choice in evt.get("choices", []):
#                 delta = choice.get("delta", {})
#                 if not delta:
#                     break
#                 if "content" in delta and delta["content"]:
#                     # normal answer chunk
#                     yield (False, delta["content"].replace("\\n", "\n"))
#                 elif "reasoning_content" in delta and delta["reasoning_content"]:
#                     # reasoning chunk
#                     yield (True, delta["reasoning_content"].replace("\\n", "\n"))

#                 # If we hit the final chunk, grab the timings and exit
#                 if choice.get("finish_reason") == "stop":
#                     times = evt.get("timings", {})
#                     if times:
#                         meta = (
#                             times[k] for k in
#                             ("cache_n", "prompt_n", "prompt_per_second",
#                              "predicted_per_second")
#                             if k in times
#                         )
#                         print(meta)
#                     yield meta
#                     break
#         # The `return` raises StopIteration with `meta` as its value



# # --------------------------------------------------------------------
# # 2)  Worker thread – runs the generator and writes to the view.
# # --------------------------------------------------------------------
# class StreamingTask(threading.Thread):
#     """Background worker that drives the generator and streams data."""
#     # (TODO: Alec, 2025) Write system prompt to file
#     # (TODO: Alec, 2025) Just write start to file and read messages from file?

#     def __init__(self, view: sublime.View, content, user_input,
#                  filename, registry):
#         super().__init__(daemon=True)

#         self.view = view
#         self.content = content
#         self.user_input = user_input
#         self.filename = filename
#         self._cancel = False
#         self.registry = registry   # map view.id() → task
#         if user_input is not None:
#             self.prompt = "File: {}\n```\n{}\n```\n{}" \
#                           .format(filename, content, user_input)
#             self.view.run_command('append', {
#                 'characters':
#                 '# --- User ---\n{}\n# --- Agent ---\n'.format(self.prompt)
#             })
#         else:
#             self.view.run_command('append', {'characters':'\n# --- Agent ---\n'})
#             self.prompt = content

#     def cancel(self):
#         """Ask the thread to stop."""
#         self._cancel = True
#         self.view.settings().set("is_streaming", False)  # TODO(Alec, 2025): clean up stopping logic - should not be needed here

#     def run(self):
#         sublime.status_message("Streaming")
#         self.view.run_command("move_to", {"to": "eof", "extend": False})
#         prev_reasoning = False

#         for i, data in enumerate(chat_stream(self.prompt)):
#             if len(data) == 2:
#                 reasoning, chunk = data
#             else:
#                 cache, prompt, pps, tkps = data
#                 self.view.set_status(
#                     "streamstatus",
#                     "Done. cache: {:1g}, new: {:1g}, tk/s: {:1g}".format(
#                         cache, prompt, tkps)
#                 )
#                 break
#             if self._cancel or not self.view or not self.view.is_valid():
#                 self.view.set_status("streamstatus", "Interrupted")
#                 finished = False
#                 break
#             if reasoning:
#                 if not prev_reasoning:
#                     chunk = "> " + chunk
#                     self.view.run_command(
#                         'append', {'characters': "\n## --- Thinking ---\n"}
#                     )
#                     prev_reasoning = True
#                 chunk = chunk.replace("\n", "\n> ")
#             else:
#                 if prev_reasoning:
#                     self.view.run_command(
#                         'append', {'characters': "\n## --- Response ---\n"}
#                     )
#                     prev_reasoning = False
#             # Fire on the UI thread ----------------------------------
#             sublime.set_timeout(
#                 lambda c=chunk:
#                     self.view.run_command('append', {'characters': c}),
#                 0
#             )

#         # Finalise: wipe the registry entry and set status --------------------
#         sublime.set_timeout(lambda: self._finalize(), 0)

#     def _finalize(self):
#         self.registry.pop(self.view.id(), None)
#         self.view.run_command('append', {'characters': '\n\n# --- User ---\n'})
#         self.view.settings().set("is_streaming", False)


# # --------------------------------------------------------------------
# # 3)  TextInputHandler – Palette asks for a free‑form string.
# # --------------------------------------------------------------------
# class PromptInputHandler(sublime_plugin.TextInputHandler):
#     def placeholder(self):
#         return "Enter command string"

#     # optional – return whatever you last typed
#     def initial_text(self):
#         return ""


# # --------------------------------------------------------------------
# # 4)  Global registry of running tasks
# # --------------------------------------------------------------------
# _active_streamers = {}        # view.id() → StreamingTask


# # --------------------------------------------------------------------
# # 5)  The command that opens a new window, creates a view & starts streaming.
# # --------------------------------------------------------------------
# class AiAgentCodeCommand(sublime_plugin.WindowCommand):
#     """Open a new window → new view → stream output into that view."""

#     def input(self, args):
#         """Show the command‑palette overlay for the command string."""
#         return PromptInputHandler()

#     def run(self, prompt):
#         # Get content to stream – selection or whole file
#         view = self.window.active_view()
#         if not view:
#             sublime.status_message("Nothing to stream – no active view.")
#             return

#         sel = view.sel()
#         if any(not r.empty() for r in sel):
#             content = "```".join(view.substr(r) for r in sel if not r.empty())
#         else:
#             content = view.substr(sublime.Region(0, view.size()))

#         # ------------------------------------------------------------------
#         # 1.  Open a brand‑new window
#         # ------------------------------------------------------------------
#         sublime.run_command('new_tab')
#         new_win = sublime.windows()[-1]       # the window we just created

#         # ------------------------------------------------------------------
#         # 2.  Open a *scratch* view inside that window
#         # ------------------------------------------------------------------
#         stream_view = new_win.new_file()
#         stream_view.set_scratch(True)                 # delete on close
#         stream_view.set_name("Chat {}".format(prompt[:20]))
#         stream_view.settings().set("is_streaming", True)
#         stream_view.settings().set("is_agent_chat", True)

#         #  Markdown syntax if available (fallback to plain‑text)
#         try:
#             stream_view.set_syntax_file(
#                 "Packages/Markdown/Markdown.sublime-syntax")
#         except Exception:
#             pass

#         # Show it (the new file is already focused)
#         new_win.focus_view(stream_view)

#         # ------------------------------------------------------------------
#         # 3.  Start the streaming thread
#         # ------------------------------------------------------------------
#         task = StreamingTask(stream_view, content,
#                              prompt, view.file_name(), _active_streamers)
#         task.start()
#         _active_streamers[stream_view.id()] = task

#         sublime.status_message("Submitting prompt")


# # --------------------------------------------------------------------
# # 6)  Cancel command – bound to `c` while a streaming view has focus.
# # --------------------------------------------------------------------
# class CancelStreamCommand(sublime_plugin.WindowCommand):
#     """Cancels the running streaming task for the active view."""

#     def run(self):
#         view = self.window.active_view()
#         if not view:
#             return
#         if not view.settings().get('is_streaming'):
#             return
#         task = _active_streamers.get(view.id())
#         if task:
#             task.cancel()
#             sublime.status_message("Streaming cancelled")
#         else:
#             view.settings().set('is_streaming', False)


# class AgentClearReasoningCommand(sublime_plugin.TextCommand):
#     """Clear thinking from agent chat output"""

#     def run(self, edit):
#         view = self.view
#         if not view:
#             return

#         # --------------------------------------------------------------------
#         # If a we are actively streaming to this view, do nothing.
#         # --------------------------------------------------------------------
#         if view.id() in _active_streamers:
#             return

#         # --------------------------------------------------------------------
#         # Extract the raw text and parse the chat history
#         # --------------------------------------------------------------------
#         data = view.substr(sublime.Region(0, view.size()))
#         messages = AgentChatCommand.build_history(data)
#         print(len(messages))
#         print([m['role'] for m in messages])

#         if not messages:
#             sublime.status_message("Chat data not found")
#             return

#         # --------------------------------------------------------------------
#         # Re‑build the cleaned chat text
#         # --------------------------------------------------------------------
#         parts = []

#         tag_map = {
#             'user': '# --- User ---',
#             'assistant': '# --- Agent ---',
#             'developer': '# --- System ---',
#         }

#         for msg in messages:
#             tag = tag_map[msg['role']]
#             # Append the role tag followed by the message content
#             parts.append("{}\n{}\n".format(tag, msg['content']))

#         cleaned_text = "\n".join(parts)
#         # print(cleaned_text)

#         view.replace(edit, sublime.Region(0, view.size()), cleaned_text)
#         # --------------------------------------------------------------------
#         # Replace the entire view contents with the cleaned text
#         # --------------------------------------------------------------------
#         # The built‑in 'replace' command accepts a region (start, end) and the new text.
#         # view.run_command('replace', {
#         #     'region': [0, view.size()],
#         #     'text': cleaned_text
#         # })

#         # --------------------------------------------------------------------
#         # Reset any chat‑specific settings and ensure the syntax is Markdown
#         # --------------------------------------------------------------------
#         view.settings().set("is_streaming", False)

#         sublime.status_message("Chat cleared")


# # --------------------------------------------------------------------
# # 7) Continue current chat
# # --------------------------------------------------------------------
# class AgentChatCommand(sublime_plugin.TextCommand):
#     """Continues an agent chat from a file"""

#     def run(self, edit):
#         view = self.view
#         if not view:
#             return

#         if view.settings().get('is_streaming'):
#             task = _active_streamers.get(view.id())
#             if task:
#                 task.cancel()
#                 sublime.status_message("Streaming cancelled")
#             return

#         data = view.substr(sublime.Region(0, view.size()))
#         messages = self.build_history(data)
#         print(len(messages))
#         print([m['role'] for m in messages])

#         if len(messages) == 0:
#             sublime.status_message("Chat data not found")
#             return

#         view.settings().set("is_streaming", True)
#         view.settings().set("is_agent_chat", True)

#         try:
#             view.set_syntax_file(
#                 "Packages/Markdown/Markdown.sublime-syntax")
#         except Exception:
#             pass

#         task = StreamingTask(view, messages, None, None, _active_streamers)
#         task.start()
#         _active_streamers[view.id()] = task
#         sublime.status_message("Submitting prompt")

#     @staticmethod
#     def build_history(content):
#         # Grab the whole view as a string
#         lines = content.splitlines(True)  # keep line endings

#         messages = []          # list of {"role": ..., "content": ...}
#         current_role = None    # "user" or "assistant"
#         content_lines = []     # temporary buffer for the current block
#         in_reasoning = False   # skip reasoning blocks

#         for line in lines:
#             stripped = line.strip()

#             # Detect the start of a new block
#             if stripped.startswith('# --- '):
#                 # Finalise the previous block
#                 if current_role and content_lines:
#                     msg_content = ''.join(content_lines).rstrip('\n')
#                     messages.append({"role": current_role, "content": msg_content})

#                 # New block role
#                 if 'User' in stripped:
#                     current_role = 'user'
#                 elif 'Agent' in stripped:
#                     current_role = 'assistant'
#                 elif 'System' in stripped:
#                     current_role = 'developer'
#                 else:
#                     current_role = None

#                 in_reasoning = False
#                 content_lines = []
#                 continue

#             # Skip reasoning section headers
#             if stripped.startswith('## --- '):
#                 if 'Thinking' in stripped:
#                     in_reasoning = True
#                 elif 'Response' in stripped:
#                     in_reasoning = False
#                 continue

#             # Skip reasoning content
#             if in_reasoning:
#                 continue

#             # Normal content – append to the current block
#             if current_role:
#                 content_lines.append(line)

#         # Finalise the last block (if any)
#         if current_role:
#             msg_content = ''.join(content_lines).rstrip('\n')
#             messages.append({"role": current_role, "content": msg_content})

#         return messages
