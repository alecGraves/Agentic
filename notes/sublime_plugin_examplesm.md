# Sublime text plugin examples

(mostly from sublime_default package - unzip it to view contents)

``` Find in Files output:
Searching 107 files for "test"

~/Downloads/sublime_default/colors.py:
  136  def hue_diff(a, b):
  137      """
  138:     Find the shortest distance hue difference between two HSLA objects
  139  
  140      :param a:
  ...
  157      diff = max - min
  158  
  159:     # Diff the hue in the shortest direction
  160      if diff > 0.5:
  161          diff = math.fmod(min + 1.0 - max, 1.0)

~/Downloads/sublime_default/Fold Syntax Test Results.tmPreferences:
    3  <dict>
    4      <key>scope</key>
    5:     <string>text.syntax-tests</string>
    6      <key>settings</key>
    7      <dict>

~/Downloads/sublime_default/run_syntax_tests.py:
   11  
   12  
   13: class RunSyntaxTestsCommand(sublime_plugin.WindowCommand):
   14      def run(self,
   15              find_all=False,
   16:             syntax='Packages/Default/Syntax Test Results.sublime-syntax',
   17              **kwargs):
   18  
   ..
   42  
   43              if is_syntax(relative_path):
   44:                 tests = []
   45:                 for t in sublime.find_resources('syntax_test_*'):
   46                      lines = sublime.load_binary_resource(t).splitlines()
   47                      if len(lines) == 0:
   ..
   49                      first_line = lines[0]
   50  
   51:                     match = re.match(b'^.*SYNTAX TEST .*"(.*?)"', first_line)
   52                      if not match:
   53                          continue
```

Here is an example of taking user input from the command pallet:

```Python
import sublime_plugin
import math


def try_eval(str):
    try:
        return eval(str, {}, {})
    except Exception:
        return None


def eval_expr(orig, i, expr):
    x = try_eval(orig) or 0

    return eval(expr, {"s": orig, "x": x, "i": i, "math": math}, {})


class ExprInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, view):
        self.view = view

    def placeholder(self):
        return "Expression"

    def initial_text(self):
        if len(self.view.sel()) == 1:
            return self.view.substr(self.view.sel()[0])
        elif self.view.sel()[0].size() == 0:
            return "i + 1"
        elif try_eval(self.view.substr(self.view.sel()[0])) is not None:
            return "x"
        else:
            return "s"

    def preview(self, expr):
        try:
            v = self.view
            s = v.sel()
            count = len(s)
            if count > 5:
                count = 5
            results = [repr(eval_expr(v.substr(s[i]), i, expr)) for i in range(count)]
            if count != len(s):
                results.append("...")
            return ", ".join(results)
        except Exception:
            return ""

    def validate(self, expr):
        try:
            v = self.view
            s = v.sel()
            for i in range(len(s)):
                eval_expr(v.substr(s[i]), i, expr)
            return True
        except Exception:
            return False


class ArithmeticCommand(sublime_plugin.TextCommand):
    def run(self, edit, expr):
        for i in range(len(self.view.sel())):
            s = self.view.sel()[i]
            data = self.view.substr(s)
            self.view.replace(edit, s, str(eval_expr(data, i, expr)))

    def input(self, args):
        return ExprInputHandler(self.view)
```

Here is the entry for it:
```
~/Downloads/sublime_default/Default.sublime-commands:
    1  [
    2:  { "caption": "Arithmetic", "command": "arithmetic" },
    3  
    4   { "caption": "Wrap at Ruler", "command": "wrap_lines" },
```

Here is an example sublime command that modifies (sorts) selected text:
```Python
def shrink_wrap_region(view, region):
    a, b = region.begin(), region.end()

    for a in range(a, b):
        if not view.substr(a).isspace():
            break

    for b in range(b - 1, a, -1):
        if not view.substr(b).isspace():
            b += 1
            break

    return sublime.Region(a, b)


def shrinkwrap_and_expand_non_empty_selections_to_entire_line(v):
    regions = []

    for sel in v.sel():
        if not sel.empty():
            regions.append(v.line(shrink_wrap_region(v, v.line(sel))))
            v.sel().subtract(sel)

    for r in regions:
        v.sel().add(r)

    return [s for s in v.sel() if not s.empty()]


def permute_lines(f, v, e):
    regions = shrinkwrap_and_expand_non_empty_selections_to_entire_line(v)

    if not regions:
        v.sel().add(sublime.Region(0, v.size()))
        regions = shrinkwrap_and_expand_non_empty_selections_to_entire_line(v)

    regions.sort(reverse=True)

    for r in regions:
        txt = v.substr(r)
        lines = txt.split('\n')
        lines = f(lines)

        v.replace(e, r, u"\n".join(lines))


class SortLinesCommand(sublime_plugin.TextCommand):
    def run(self, edit, case_sensitive=False, reverse=False, remove_duplicates=False):
        view = self.view

        if case_sensitive:
            permute_lines(case_sensitive_sort, view, edit)
        else:
            permute_lines(case_insensitive_sort, view, edit)

        if reverse:
            permute_lines(reverse_list, view, edit)

        if remove_duplicates:
            permute_lines(uniquealise_list, view, edit)

```


Here is the .sublime_commands for that:
```
~/Downloads/sublime_default/Default.sublime-commands:
  110   { "caption": "Rot13 Selection", "command": "rot13" },
  111  
  112:  { "caption": "Sort Lines", "command": "sort_lines", "args": {"case_sensitive": false} },
  113:  { "caption": "Sort Lines (Case Sensitive)", "command": "sort_lines", "args": {"case_sensitive": true} },
  114  
  115   { "caption": "Selection: Split into Lines", "command": "split_selection_into_lines" },
  ...
  137   { "caption": "Permute Lines: Shuffle", "command": "permute_lines", "args": {"operation": "shuffle"} },
  138  
  139:  { "caption": "Permute Selections: Sort", "command": "sort_selection", "args": {"case_sensitive": false} },
  140:  { "caption": "Permute Selections: Sort (Case Sensitive)", "command": "sort_selection", "args": {"case_sensitive": true} },
```


Here is an example of commenting (in place highlighted text manipulation)
```Python
class ToggleCommentCommand(sublime_plugin.TextCommand):
    def remove_block_comment(self, view, edit, region):
        scope = view.scope_name(region.begin())

        if region.end() > region.begin() + 1:
            end_scope = view.scope_name(region.end() - 1)
            # Find the common scope prefix. This results in correct behavior in
            # embedded-language situations.
            scope = os.path.commonprefix([scope, end_scope])

        index = scope.rfind(' comment.block.')
        if index == -1:
            return False

        selector = scope[:index + len(' comment.block')]

        whole_region = view.expand_to_scope(region.begin(), selector)

        if not whole_region:
            whole_region = region
        elif whole_region.end() < region.end():
            return False

        block_comments = build_comment_data(view, whole_region.begin())[1]

        for c in block_comments:
            (start, end, disable_indent, ignore_case) = c
            start_region = sublime.Region(whole_region.begin(), whole_region.begin() + len(start))
            end_region = sublime.Region(whole_region.end() - len(end), whole_region.end())

            should_remove = (view.substr(start_region) == start and
                             view.substr(end_region) == end) or \
                            (ignore_case and
                             view.substr(start_region).lower() == start.lower() and
                             view.substr(end_region).lower() == end.lower())

            if should_remove:
                # It's faster to erase the start region first
                view.erase(edit, start_region)

                end_region = sublime.Region(
                    end_region.begin() - start_region.size(),
                    end_region.end() - start_region.size())

                view.erase(edit, end_region)
                return True

        return False

    def remove_line_comment(self, view, edit, region):
        start_positions = [advance_to_first_non_white_space_on_line(
            view, r.begin()) for r in view.lines(region)]
        start_positions = list(filter(
            lambda p: has_non_white_space_on_line(view, p), start_positions))
        if len(start_positions) == 0:
            return False

        line_comments = build_comment_data(view, start_positions[0])[0]

        regions = []
        for pos in start_positions:
            found = False
            for (start, _, ignore_case) in line_comments:
                comment_region = sublime.Region(pos, pos + len(start))

                should_remove = (view.substr(comment_region) == start or
                                 (ignore_case and
                                  view.substr(comment_region).lower() == start.lower()))

                if should_remove:
                    found = True
                    regions.append(comment_region)
                    break
            if not found:
                return False

        for region in reversed(regions):
            view.erase(edit, region)

        return True

    def block_comment_region(self, view, edit, region, variant, enable_indent=False):
        comment_data = build_comment_data(view, region.begin())

        if region.end() > region.begin() + 1:
            if build_comment_data(self.view, region.end() - 1) != comment_data:
                return False

        if len(comment_data[1]) <= variant:
            return False

        (start, end, disable_indent, _) = comment_data[1][variant]

        if enable_indent and not disable_indent:
            min_indent_lines(view, [region])

        if region.empty():
            # Silly buggers to ensure the cursor doesn't end up after the end
            # comment token
            view.replace(edit, sublime.Region(region.end()), 'x')
            view.insert(edit, region.end() + 1, end)
            view.replace(edit, sublime.Region(region.end(), region.end() + 1), '')
            view.insert(edit, region.begin(), start)
        else:
            view.insert(edit, region.end(), end)
            view.insert(edit, region.begin(), start)

        return True

    def line_comment_region(self, view, edit, region, variant):
        lines = view.lines(region)

        # Remove any blank lines from consideration, they make getting the
        # comment start markers to line up challenging
        non_empty_lines = list(filter(
            lambda l: has_non_white_space_on_line(view, l.a), lines))

        # If all the lines are blank however, just comment away
        if len(non_empty_lines) != 0:
            lines = non_empty_lines

        comment_data = build_comment_data(view, lines[0].a)

        if len(comment_data[0]) <= variant:
            # When there's no line comments fall back on the block comment. Only
            # do this for single lines, otherwise we want to fall back on
            # block-comment behavior.
            if len(lines) == 1:
                line = lines[0]
                pt = advance_to_first_non_white_space_on_line(view, line.begin())
                if self.remove_block_comment(view, edit, sublime.Region(pt)):
                    return True

                if self.block_comment_region(view, edit, line, variant, True):
                    return True

            return False

        (start, disable_indent, *_) = comment_data[0][variant]

        if not disable_indent:
            min_indent_lines(view, lines)

        for line in reversed(lines):
            view.insert(edit, line.begin(), start)

        return True

    def run(self, edit, block=False, variant=0):
        for region in self.view.sel():
            if self.remove_block_comment(self.view, edit, region):
                continue

            if self.remove_line_comment(self.view, edit, region):
                continue

            if block:
                if not self.block_comment_region(self.view, edit, region, variant):
                    self.line_comment_region(self.view, edit, region, variant)
            else:
                if not self.line_comment_region(self.view, edit, region, variant):
                    self.block_comment_region(self.view, edit, region, variant)
```


Here is a pane command:

```Python
class NewPaneCommand(sublime_plugin.WindowCommand):
    def new_pane(self, window, move_sheet, max_columns):
        cur_sheet = window.active_sheet()

        layout = window.get_layout()
        num_panes = len(layout["cells"])

        cur_index = window.active_group()

        rows = layout["rows"]
        cols = layout["cols"]
        cells = layout["cells"]

        if cells != assign_cells(num_panes, max_columns):
            # Current layout doesn't follow the automatic method, reset everyting
            num_rows, num_cols = rows_cols_for_panes(num_panes + 1, max_columns)
            rows = create_splits(num_rows)
            cols = create_splits(num_cols)
            cells = assign_cells(num_panes + 1, max_columns)
        else:
            # Adjust the current layout, keeping the user selected column widths
            # where possible
            num_cols = len(cols) - 1
            num_rows = len(rows) - 1

            # insert a new row or a new col
            if num_cols < max_columns:
                num_cols += 1
                cols = create_splits(num_cols)
            else:
                num_rows += 1
                rows = create_splits(num_rows)

            cells = assign_cells(num_panes + 1, max_columns)

        window.set_layout({'cells': cells, 'rows': rows, 'cols': cols})
        window.settings().set('last_automatic_layout', cells)

        # Move all the sheets so the new pane is created in the correct location
        for i in reversed(range(0, num_panes - cur_index - 1)):
            current_selection = window.selected_sheets_in_group(cur_index + i + 1)
            window.move_sheets_to_group(window.sheets_in_group(cur_index + i + 1), cur_index + i + 2, select=False)
            window.select_sheets(current_selection)

        if move_sheet:
            transient = window.transient_sheet_in_group(cur_index)
            if transient is not None and cur_sheet.sheet_id == transient.sheet_id:
                # transient sheets may only be moved to index -1
                window.set_sheet_index(cur_sheet, cur_index + 1, -1)
            else:
                selected_sheets = window.selected_sheets_in_group(cur_index)
                window.move_sheets_to_group(selected_sheets, cur_index + 1)
                window.focus_sheet(cur_sheet)
        else:
            window.focus_group(cur_index)

    def run(self, move=True):
        max_columns = self.window.template_settings().get('max_columns', MAX_COLUMNS)
        self.new_pane(self.window, move, max_columns)
```


Here is an async exec runner (that opens a new pane) (example of streaming, but from an external process, not in-plugin python code):
```Python
class ProcessListener:
    def on_data(self, proc, data):
        pass

    def on_finished(self, proc):
        pass


class AsyncProcess:
    """
    Encapsulates subprocess.Popen, forwarding stdout to a supplied
    ProcessListener (on a separate thread)
    """

    def __init__(self, cmd, shell_cmd, env, listener, path="", shell=False):
        """ "path" and "shell" are options in build systems """

        if not shell_cmd and not cmd:
            raise ValueError("shell_cmd or cmd is required")

        if shell_cmd and not isinstance(shell_cmd, str):
            raise ValueError("shell_cmd must be a string")

        self.listener = listener
        self.killed = False

        self.start_time = time.time()

        # Hide the console window on Windows
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            # Set temporary PATH to locate executable in cmd
            if path:
                old_path = os.environ["PATH"]
                # The user decides in the build system whether he wants to append
                # $PATH or tuck it at the front: "$PATH;C:\\new\\path",
                # "C:\\new\\path;$PATH"
                os.environ["PATH"] = os.path.expandvars(path)

            proc_env = os.environ.copy()
            proc_env.update(env)
            for k, v in proc_env.items():
                proc_env[k] = os.path.expandvars(v)

            if sys.platform == "win32":
                preexec_fn = None
            else:
                preexec_fn = os.setsid

            if shell_cmd:
                if sys.platform == "win32":
                    # Use shell=True on Windows, so shell_cmd is passed through
                    # with the correct escaping
                    cmd = shell_cmd
                    shell = True
                elif sys.platform == "darwin":
                    # Use a login shell on OSX, otherwise the users expected env
                    # vars won't be setup
                    cmd = ["/usr/bin/env", "bash", "-l", "-c", shell_cmd]
                    shell = False
                elif sys.platform == "linux":
                    # Explicitly use /bin/bash on Linux, to keep Linux and OSX as
                    # similar as possible. A login shell is explicitly not used for
                    # linux, as it's not required
                    cmd = ["/usr/bin/env", "bash", "-c", shell_cmd]
                    shell = False

            self.proc = subprocess.Popen(
                cmd,
                bufsize=0,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo,
                env=proc_env,
                preexec_fn=preexec_fn,
                shell=shell)

        finally:
            # Make sure this is always run, otherwise we're leaving the PATH set
            # permanently
            if path:
                os.environ["PATH"] = old_path

        self.stdout_thread = threading.Thread(
            target=self.read_fileno,
            args=(self.proc.stdout, True)
        )

    def start(self):
        self.stdout_thread.start()

    def start_input_thread(self):
        input_queue = queue.SimpleQueue()

        def write():
            while self.poll():
                text = input_queue.get()
                if text is None:
                    break

                self.proc.stdin.write(text)
                self.proc.stdin.flush()

        threading.Thread(target=write).start()

        return input_queue

    def kill(self):
        if not self.killed:
            self.killed = True
            if sys.platform == "win32":
                # terminate would not kill process opened by the shell cmd.exe,
                # it will only kill cmd.exe leaving the child running
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.Popen(
                    "taskkill /PID %d /T /F" % self.proc.pid,
                    startupinfo=startupinfo)
            else:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.terminate()

    def poll(self):
        return self.proc.poll() is None

    def exit_code(self):
        return self.proc.poll()

    def read_fileno(self, file, execute_finished):
        decoder = \
            codecs.getincrementaldecoder(self.listener.encoding)('replace')

        while True:
            data = decoder.decode(file.read(2**16))
            data = data.replace('\r\n', '\n').replace('\r', '\n')

            if len(data) > 0 and not self.killed:
                self.listener.on_data(self, data)
            else:
                if execute_finished:
                    sublime.set_timeout(lambda: self.listener.on_finished(self))
                break

class ExecCommand(sublime_plugin.WindowCommand, ProcessListener):
    OUTPUT_LIMIT = 2 ** 27

    def __init__(self, window):
        super().__init__(window)

        self.proc = None

        self.errs_by_file = {}
        self.annotation_sets_by_buffer = {}
        self.show_errors_inline = True
        self.input_view = None
        self.output_view = None
        self.input_queue = None

    def run(
            self,
            cmd=None,
            shell_cmd=None,
            file_regex="",
            line_regex="",
            working_dir="",
            encoding="utf-8",
            env={},
            quiet=False,
            kill=False,
            kill_previous=False,
            update_annotations_only=False,
            word_wrap=True,
            interactive=False,
            syntax="Packages/Text/Plain text.tmLanguage",
            path="",
            # Catches "shell"
            **kwargs):

        if update_annotations_only:
            if self.show_errors_inline:
                self.update_annotations()
            return

        if kill:
            if self.proc:
                self.proc.kill()
            return

        if kill_previous and self.proc and self.proc.poll():
            self.proc.kill()

        self.output_view, self.input_view = self.window.find_io_panel("exec")
        if self.output_view is None:
            # Try not to call get_output_panel until the regexes are assigned
            self.output_view, self.input_view = self.window.create_io_panel(
                "exec", self.on_input if interactive else None)

        # Default the to the current files directory if no working directory
        # was given
        if (working_dir == "" and
                self.window.active_view() and
                self.window.active_view().file_name()):
            working_dir = os.path.dirname(self.window.active_view().file_name())

        self.output_view.settings().set("result_file_regex", file_regex)
        self.output_view.settings().set("result_line_regex", line_regex)
        self.output_view.settings().set("result_base_dir", working_dir)
        self.output_view.settings().set("word_wrap", word_wrap)
        self.output_view.settings().set("line_numbers", False)
        self.output_view.settings().set("gutter", False)
        self.output_view.settings().set("scroll_past_end", False)
        self.output_view.assign_syntax(syntax)

        # Call create_output_panel a second time after assigning the above
        # settings, so that it'll be picked up as a result buffer
        self.window.create_io_panel("exec", self.on_input if interactive else None)

        self.encoding = encoding
        self.quiet = quiet

        self.proc = None
        if not self.quiet:
            if shell_cmd:
                print("Running " + shell_cmd)
            elif cmd:
                cmd_string = cmd
                if not isinstance(cmd, str):
                    cmd_string = " ".join(cmd)
                print("Running " + cmd_string)
            sublime.status_message("Building")

        preferences_settings = \
            sublime.load_settings("Preferences.sublime-settings")
        show_panel_on_build = \
            preferences_settings.get("show_panel_on_build", True)
        if show_panel_on_build:
            self.window.run_command("show_panel", {"panel": "output.exec"})

        self.hide_annotations()
        self.show_errors_inline = \
            preferences_settings.get("show_errors_inline", True)

        merged_env = {}

        if path:
            merged_env['PATH'] = path

        merged_env.update(env)
        if self.window.active_view():
            user_env = self.window.active_view().settings().get('build_env')
            if user_env:
                merged_env.update(user_env)

        # Change to the working dir, rather than spawning the process with it,
        # so that emitted working dir relative path names make sense
        if working_dir != "":
            os.chdir(working_dir)

        self.debug_text = ""
        if shell_cmd:
            self.debug_text += "[shell_cmd: " + shell_cmd + "]\n"
        else:
            self.debug_text += "[cmd: " + str(cmd) + "]\n"
        self.debug_text += "[dir: " + str(os.getcwd()) + "]\n"
        if "PATH" in merged_env:
            self.debug_text += "[path: " + str(os.path.expandvars(merged_env["PATH"])) + "]"
        else:
            self.debug_text += "[path: " + str(os.environ["PATH"]) + "]"

        self.output_size = 0
        self.should_update_annotations = False

        try:
            # Forward kwargs to AsyncProcess
            self.proc = AsyncProcess(cmd, shell_cmd, merged_env, self, **kwargs)

            self.proc.start()

            if interactive:
                self.input_queue = self.proc.start_input_thread()
            else:
                self.input_queue = None

        except Exception as e:
            self.write(str(e) + "\n")
            self.write(self.debug_text + "\n")
            if not self.quiet:
                self.write("[Finished]")

        if interactive:
            self.window.focus_view(self.input_view)

    def is_enabled(self, kill=False, **kwargs):
        if kill:
            return (self.proc is not None) and self.proc.poll()
        else:
            return True

    def write(self, characters):
        self.output_view.run_command(
            'append',
            {'characters': characters, 'force': True, 'scroll_to_end': True})

        # Updating annotations is expensive, so batch it to the main thread
        def annotations_check():
            errs = self.output_view.find_all_results_with_text()
            errs_by_file = {}
            for file, line, column, text in errs:
                if file not in errs_by_file:
                    errs_by_file[file] = []
                errs_by_file[file].append((line, column, text))
            self.errs_by_file = errs_by_file

            self.update_annotations()

            self.should_update_annotations = False

        if not self.should_update_annotations:
            if self.show_errors_inline and characters.find('\n') >= 0:
                self.should_update_annotations = True
                sublime.set_timeout(lambda: annotations_check())

    def on_input(self, text):
        if not self.input_view:
            return

        if not self.proc.poll():
            return

        text += '\n'

        self.write(text)
        self.input_queue.put(text.encode(self.encoding))

    def on_data(self, proc, data):
        if proc != self.proc:
            return

        # Truncate past the limit
        if self.output_size >= self.OUTPUT_LIMIT:
            return

        self.write(data)
        self.output_size += len(data)

        if self.output_size >= self.OUTPUT_LIMIT:
            self.write('\n[Output Truncated]\n')

    def on_finished(self, proc):
        if proc != self.proc:
            return

        if self.input_queue is not None:
            # This signals shutdown
            self.input_queue.put(None)
            self.input_queue = None

        if proc.killed:
            self.write("\n[Cancelled]")
        elif not self.quiet:
            elapsed = time.time() - proc.start_time
            if elapsed < 1:
                elapsed_str = "%.0fms" % (elapsed * 1000)
            else:
                elapsed_str = "%.1fs" % (elapsed)

            exit_code = proc.exit_code()
            if exit_code == 0 or exit_code is None:
                self.write("[Finished in %s]" % elapsed_str)
            else:
                self.write("[Finished in %s with exit code %d]\n" %
                           (elapsed_str, exit_code))
                self.write(self.debug_text)

        if proc.killed:
            sublime.status_message("Build cancelled")
        else:
            errs = self.output_view.find_all_results()
            if len(errs) == 0:
                sublime.status_message("Build finished")
            else:
                sublime.status_message("Build finished with %d errors" %
                                       len(errs))

    def update_annotations(self):
        stylesheet = '''
            <style>
                #annotation-error {
                    background-color: color(var(--background) blend(#fff 95%));
                }
                html.dark #annotation-error {
                    background-color: color(var(--background) blend(#fff 95%));
                }
                html.light #annotation-error {
                    background-color: color(var(--background) blend(#000 85%));
                }
                a {
                    text-decoration: inherit;
                }
            </style>
        '''

        for file, errs in self.errs_by_file.items():
            view = self.window.find_open_file(file)
            if view:
                selection_set = []
                content_set = []

                line_err_set = []

                for line, column, text in errs:
                    pt = view.text_point(line - 1, column - 1)
                    if (line_err_set and
                            line == line_err_set[len(line_err_set) - 1][0]):
                        line_err_set[len(line_err_set) - 1][1] += (
                            "<br>" + html.escape(text, quote=False))
                    else:
                        pt_b = pt + 1
                        if view.classify(pt) & sublime.CLASS_WORD_START:
                            pt_b = view.find_by_class(
                                pt,
                                forward=True,
                                classes=(sublime.CLASS_WORD_END))
                        if pt_b <= pt:
                            pt_b = pt + 1
                        selection_set.append(
                            sublime.Region(pt, pt_b))
                        line_err_set.append(
                            [line, html.escape(text, quote=False)])

                for text in line_err_set:
                    content_set.append(
                        '<body>' + stylesheet +
                        '<div class="error" id=annotation-error>' +
                        '<span class="content">' + text[1] + '</span></div>' +
                        '</body>')

                view.add_regions(
                    "exec",
                    selection_set,
                    scope="invalid",
                    annotations=content_set,
                    flags=(sublime.DRAW_SQUIGGLY_UNDERLINE |
                           sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE),
                    on_close=self.hide_annotations)

    def hide_annotations(self):
        for window in sublime.windows():
            for file, errs in self.errs_by_file.items():
                view = window.find_open_file(file)
                if view:
                    view.erase_regions("exec")
                    view.hide_popup()

        view = sublime.active_window().active_view()
        if view:
            view.erase_regions("exec")
            view.hide_popup()

        self.errs_by_file = {}
        self.annotation_sets_by_buffer = {}
        self.show_errors_inline = False


class ExecEventListener(sublime_plugin.EventListener):
    def on_load(self, view):
        w = view.window()
        if w is not None:
            w.run_command('exec', {'update_annotations_only': True})

```


Here are pane manipulation examples:
```Python
class PaneCommand(sublime_plugin.WindowCommand):
    """Abstract base class for commands."""

    def get_layout(self):
        layout = self.window.layout()
        rows = layout["rows"]
        cols = layout["cols"]
        cells = layout["cells"]
        return rows, cols, cells

    def get_cells(self):
        return self.get_layout()[2]

    def adjacent_cell(self, direction):
        cells = self.get_cells()
        current_cell = cells[self.window.active_group()]
        adjacent_cells = cells_adjacent_to_cell_in_direction(cells, current_cell, direction)
        rows, cols, _ = self.get_layout()

        if direction in ("left", "right"):
            MIN, MAX, fields = YMIN, YMAX, rows
        else:  # up or down
            MIN, MAX, fields = XMIN, XMAX, cols

        cell_overlap = []
        for cell in adjacent_cells:
            start = max(fields[cell[MIN]], fields[current_cell[MIN]])
            end = min(fields[cell[MAX]], fields[current_cell[MAX]])
            overlap = end - start  # / (fields[cell[MAX]] - fields[cell[MIN]])
            cell_overlap.append(overlap)

        if len(cell_overlap) != 0:
            cell_index = cell_overlap.index(max(cell_overlap))
            return adjacent_cells[cell_index]
        return None

    def duplicated_views(self, original_group, duplicating_group):
        original_views = self.window.views_in_group(original_group)
        original_buffers = {v.buffer_id() for v in original_views}
        potential_dupe_views = self.window.views_in_group(duplicating_group)
        return [pd for pd in potential_dupe_views if pd.buffer_id() in original_buffers]

    def travel_to_pane(self, direction, create_new_if_necessary=False, destroy_old_if_empty=False):
        adjacent_cell = self.adjacent_cell(direction)
        if adjacent_cell:
            cells = self.get_cells()
            new_group_index = cells.index(adjacent_cell)
            self.window.focus_group(new_group_index)
            if destroy_old_if_empty:
                self.destroy_pane(opposite_direction(direction), True)
        elif create_new_if_necessary:
            self.create_pane(direction, True, destroy_old_if_empty)

    def carry_file_to_pane(self, direction, create_new_if_necessary=False, destroy_old_if_empty=False):
        view = self.window.active_view()
        if view is None:
            # If we're in an empty group, there's no active view
            return
        window = self.window
        self.travel_to_pane(direction, create_new_if_necessary)

        active_group = window.active_group()
        views_in_group = window.views_in_group(active_group)
        window.set_view_index(view, active_group, len(views_in_group))
        sublime.set_timeout(lambda: window.focus_view(view))

        if destroy_old_if_empty:
            self.destroy_pane(opposite_direction(direction), True)

    def clone_file_to_pane(self, direction, create_new_if_necessary=False):
        window = self.window
        view = window.active_view()
        if view is None:
            # If we're in an empty group, there's no active view
            return
        group, original_index = window.get_view_index(view)
        window.run_command("clone_file")

        # If we move the cloned file's tab to the left of the original's,
        # then when we remove it from the group, focus will fall to the
        # original view.
        new_view = window.active_view()
        if new_view is None:
            return
        window.set_view_index(new_view, group, original_index)

        # Fix the new view's selection and viewport
        new_sel = new_view.sel()
        new_sel.clear()
        for s in view.sel():
            new_sel.add(s)
        sublime.set_timeout(lambda: new_view.set_viewport_position(view.viewport_position(), False), 0)

        self.carry_file_to_pane(direction, create_new_if_necessary)

    def reorder_panes(self, leave_files_at_position=True):
        old_index = self.window.active_group()
        on_done = partial(self._on_reorder_done, old_index, leave_files_at_position)
        view = self.window.show_input_panel("enter new index", str(old_index + 1), on_done, None, None)
        view.sel().clear()
        view.sel().add(sublime.Region(0, view.size()))

    def _on_reorder_done(self, old_index, leave_files_at_position, text):
        try:
            new_index = int(text) - 1
        except ValueError:
            return

        rows, cols, cells = self.get_layout()

        if new_index < 0 or new_index >= len(cells):
            return

        cells[old_index], cells[new_index] = cells[new_index], cells[old_index]

        if leave_files_at_position:
            old_files = self.window.views_in_group(old_index)
            new_files = self.window.views_in_group(new_index)
            for position, v in enumerate(old_files):
                self.window.set_view_index(v, new_index, position)
            for position, v in enumerate(new_files):
                self.window.set_view_index(v, old_index, position)

        layout = {"cols": cols, "rows": rows, "cells": cells}  # type: sublime.Layout
        self.window.set_layout(layout)

    def resize_panes(self, orientation, mode):
        rows, cols, cells = self.get_layout()

        if orientation == "cols":
            data = cols
            min1 = YMIN
            max1 = YMAX
            min2 = XMIN
            max2 = XMAX
        elif orientation == "rows":
            data = rows
            min1 = XMIN
            max1 = XMAX
            min2 = YMIN
            max2 = YMAX
        else:
            raise Exception('Unsupported orientation "{}"'.format(orientation))

        relevant_index = set()

        if mode == "BEFORE":
            current_cell = cells[self.window.active_group()]
            relevant_index.add(current_cell[min2])

        elif mode == "AFTER":
            current_cell = cells[self.window.active_group()]
            relevant_index.add(current_cell[max2])

        elif mode == "NEAREST":
            current_cell = cells[self.window.active_group()]
            relevant_index.update((current_cell[min2], current_cell[max2]))

        elif mode == "RELEVANT":
            current_cell = cells[self.window.active_group()]
            min_val1 = current_cell[min1]
            max_val1 = current_cell[max1]
            for c in cells:
                min_val2 = c[min1]
                max_val2 = c[max1]
                if min_val1 >= max_val2 or min_val2 >= max_val1:
                    continue
                relevant_index.update((c[min2], c[max2]))

        elif mode == "ALL":
            relevant_index.update(range(len(data)))

        relevant_index.difference_update((0, len(data) - 1))  # dont show the first and last value (it's always 0 and 1)
        relevant_index =  ed(relevant_index)

        text = ", ".join(str(data[i]) for i in relevant_index)
        on_done = partial(self._on_resize_panes, orientation, cells, relevant_index, data)
        on_update = partial(self._on_resize_panes_update, orientation, cells, relevant_index, data)
        on_cancle = partial(self._on_resize_panes, orientation, cells, relevant_index, data, text)
        view = self.window.show_input_panel(orientation, text, on_done, on_update, on_cancle)
        view.sel().clear()
        view.sel().add(sublime.Region(0, view.size()))

    def _on_resize_panes_get_layout(self, orientation, cells, relevant_index, orig_data, text):
        rows, cols, _ = self.get_layout()

        input_data = [float(x) for x in text.split(",")]
        if any(d > 1.0 for d in input_data):
            return {"cols": cols, "rows": rows, "cells": cells}

        cells = copy.deepcopy(cells)
        data = copy.deepcopy(orig_data)
        for i, d in zip(relevant_index, input_data):
            data[i] = d

        data = sorted(enumerate(data), key=lambda x: x[1])  # sort such that you can swap grid lines
        indexes, data = map(list, zip(*data))  # indexes are also sorted

        revelant_cell_entries = []
        if orientation == "cols":
            revelant_cell_entries = [XMIN, XMAX]
        elif orientation == "rows":
            revelant_cell_entries = [YMIN, YMAX]

        # change the cell boundaries according to the sorted indexes
        for cell in cells:
            for j in revelant_cell_entries:
                for new, old in enumerate(indexes):
                    if new != old and cell[j] == new:
                        cell[j] = old
                        break

        if orientation == "cols":
            if len(cols) == len(data):
                cols = data
        elif orientation == "rows":
            if len(rows) == len(data):
                rows = data

        return {"cols": cols, "rows": rows, "cells": cells}

    def _on_resize_panes_update(self, orientation, cells, relevant_index, orig_data, text):
        layout = self._on_resize_panes_get_layout(orientation, cells, relevant_index, orig_data, text)
        self.window.set_layout(layout)

    def _on_resize_panes(self, orientation, cells, relevant_index, orig_data, text):
        layout = self._on_resize_panes_get_layout(orientation, cells, relevant_index, orig_data, text)
        self.window.set_layout(layout)

    def zoom_pane(self, fraction):
        fraction_horizontal = fraction_vertical = .9

        if isinstance(fraction, float) or isinstance(fraction, int):
            fraction_horizontal = fraction_vertical = fraction
        elif isinstance(fraction, list) and len(fraction) == 2:
            if isinstance(fraction[0], float) or isinstance(fraction[0], int):
                fraction_horizontal = fraction[0]
            if isinstance(fraction[1], float) or isinstance(fraction[1], int):
                fraction_vertical = fraction[1]

        fraction_horizontal = min(1, max(0, fraction_horizontal))
        fraction_vertical = min(1, max(0, fraction_vertical))

        window = self.window
        rows, cols, cells = self.get_layout()
        current_cell = cells[window.active_group()]

        current_col = current_cell[0]
        num_cols = len(cols) - 1

        # TODO: the sizes of the unzoomed panes are calculated incorrectly if the
        #       unzoomed panes have a split that overlaps the zoomed pane.
        current_col_width = 1 if num_cols == 1 else fraction_horizontal
        other_col_width = 0 if num_cols == 1 else (1 - current_col_width) / (num_cols - 1)

        cols = [0.0]
        for i in range(num_cols):
            cols.append(cols[i] + (current_col_width if i == current_col else other_col_width))

        current_row = current_cell[1]
        num_rows = len(rows) - 1

        current_row_height = 1 if num_rows == 1 else fraction_vertical
        other_row_height = 0 if num_rows == 1 else (1 - current_row_height) / (num_rows - 1)
        rows = [0.0]
        for i in range(num_rows):
            rows.append(rows[i] + (current_row_height if i == current_row else other_row_height))

        layout = {"cols": cols, "rows": rows, "cells": cells}  # type: sublime.Layout
        window.set_layout(layout)

    def unzoom_pane(self):
        window = self.window
        rows, cols, cells = self.get_layout()

        num_cols = len(cols) - 1
        col_width = 1.0 / num_cols

        cols = [0.0]
        for i in range(num_cols):
            cols.append(cols[i] + col_width)

        num_rows = len(rows) - 1
        row_height = 1.0 / num_rows

        rows = [0.0]
        for i in range(num_rows):
            rows.append(rows[i] + row_height)

        layout = {"cols": cols, "rows": rows, "cells": cells}  # type: sublime.Layout
        window.set_layout(layout)

    def toggle_zoom(self, fraction):
        rows, cols, cells = self.get_layout()
        equal_spacing = True

        num_cols = len(cols) - 1
        col_width = 1 / num_cols

        for i, c in enumerate(cols):
            if c != i * col_width:
                equal_spacing = False
                break

        num_rows = len(rows) - 1
        row_height = 1 / num_rows

        for i, r in enumerate(rows):
            if r != i * row_height:
                equal_spacing = False
                break

        if equal_spacing:
            self.zoom_pane(fraction)
        else:
            self.unzoom_pane()

    def create_pane(self, direction, give_focus=False, destroy_old_if_empty=False):
        window = self.window
        rows, cols, cells = self.get_layout()
        current_group = window.active_group()

        old_cell = cells.pop(current_group)
        new_cell = []

        if direction in ("up", "down"):
            cells = push_down_cells_after(cells, old_cell[YMAX])
            rows.insert(old_cell[YMAX], (rows[old_cell[YMIN]] + rows[old_cell[YMAX]]) / 2)
            new_cell = [old_cell[XMIN], old_cell[YMAX], old_cell[XMAX], old_cell[YMAX] + 1]
            old_cell = [old_cell[XMIN], old_cell[YMIN], old_cell[XMAX], old_cell[YMAX]]

        elif direction in ("right", "left"):
            cells = push_right_cells_after(cells, old_cell[XMAX])
            cols.insert(old_cell[XMAX], (cols[old_cell[XMIN]] + cols[old_cell[XMAX]]) / 2)
            new_cell = [old_cell[XMAX], old_cell[YMIN], old_cell[XMAX] + 1, old_cell[YMAX]]
            old_cell = [old_cell[XMIN], old_cell[YMIN], old_cell[XMAX], old_cell[YMAX]]

        if new_cell:
            if direction in ("left", "up"):
                focused_cell = new_cell
                unfocused_cell = old_cell
            else:
                focused_cell = old_cell
                unfocused_cell = new_cell
            cells.insert(current_group, focused_cell)
            cells.append(unfocused_cell)
            layout = {"cols": cols, "rows": rows, "cells": cells}  # type: sublime.Layout
            window.set_layout(layout)

            if give_focus:
                self.travel_to_pane(direction, False, destroy_old_if_empty)

    def destroy_current_pane(self):
        # Out of the four adjacent panes, one was split to create this pane.
        # Find out which one, move to it, then destroy this pane.
        cells = self.get_cells()

        current = cells[self.window.active_group()]

        target_dir = None
        for dir in ("up", "right", "down", "left"):
            c = self.adjacent_cell(dir)
            if not c:
                continue
            if dir in ("up", "down"):
                if c[XMIN] == current[XMIN] and c[XMAX] == current[XMAX]:
                    target_dir = dir
            elif dir in ("left", "right"):
                if c[YMIN] == current[YMIN] and c[YMAX] == current[YMAX]:
                    target_dir = dir
        if target_dir:
            self.travel_to_pane(target_dir)
            self.destroy_pane(opposite_direction(target_dir))

    def destroy_pane(self, direction, only_on_empty=False):
        if direction == "self":
            self.destroy_current_pane()
            return

        window = self.window
        rows, cols, cells = self.get_layout()
        current_group = window.active_group()

        cell_to_remove = None
        current_cell = cells[current_group]

        adjacent_cells = cells_adjacent_to_cell_in_direction(cells, current_cell, direction)
        if len(adjacent_cells) == 1:
            cell_to_remove = adjacent_cells[0]

        if cell_to_remove:
            active_view = window.active_view()
            group_to_remove = cells.index(cell_to_remove)
            has_content = len(window.sheets_in_group(group_to_remove)) > 0
            if only_on_empty and has_content:
                return

            dupe_views = self.duplicated_views(current_group, group_to_remove)
            for d in dupe_views:
                window.focus_view(d)
                window.run_command('close')
            if active_view:
                window.focus_view(active_view)

            cells.remove(cell_to_remove)
            if direction == "up":
                rows.pop(cell_to_remove[YMAX])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, "down")
                for cell in adjacent_cells:
                    cells[cells.index(cell)][YMIN] = cell_to_remove[YMIN]
                cells = pull_up_cells_after(cells, cell_to_remove[YMAX])
            elif direction == "right":
                cols.pop(cell_to_remove[XMIN])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, "left")
                for cell in adjacent_cells:
                    cells[cells.index(cell)][XMAX] = cell_to_remove[XMAX]
                cells = pull_left_cells_after(cells, cell_to_remove[XMIN])
            elif direction == "down":
                rows.pop(cell_to_remove[YMIN])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, "up")
                for cell in adjacent_cells:
                    cells[cells.index(cell)][YMAX] = cell_to_remove[YMAX]
                cells = pull_up_cells_after(cells, cell_to_remove[YMIN])
            elif direction == "left":
                cols.pop(cell_to_remove[XMAX])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, "right")
                for cell in adjacent_cells:
                    cells[cells.index(cell)][XMIN] = cell_to_remove[XMIN]
                cells = pull_left_cells_after(cells, cell_to_remove[XMAX])

            layout = {"cols": cols, "rows": rows, "cells": cells}  # type: sublime.Layout
            window.set_layout(layout)

    def pull_file_from_pane(self, direction):
        adjacent_cell = self.adjacent_cell(direction)

        if adjacent_cell:
            cells = self.get_cells()
            group_index = cells.index(adjacent_cell)

            view = self.window.active_view_in_group(group_index)

            if view:
                active_group_index = self.window.active_group()
                views_in_group = self.window.views_in_group(active_group_index)
                self.window.set_view_index(view, active_group_index, len(views_in_group))


class TravelToPaneCommand(PaneCommand, WithSettings):
    def run(self, direction, create_new_if_necessary=None, destroy_old_if_empty=None):
        if create_new_if_necessary is None:
            create_new_if_necessary = self.settings().get('create_new_pane_if_necessary')
        if destroy_old_if_empty is None:
            destroy_old_if_empty = self.settings().get('destroy_empty_panes')
        self.travel_to_pane(direction, create_new_if_necessary, destroy_old_if_empty)


class CarryFileToPaneCommand(PaneCommand, WithSettings):
    def run(self, direction, create_new_if_necessary=None, destroy_old_if_empty=None):
        if create_new_if_necessary is None:
            create_new_if_necessary = self.settings().get('create_new_pane_if_necessary')
        if destroy_old_if_empty is None:
            destroy_old_if_empty = self.settings().get('destroy_empty_panes')
        self.carry_file_to_pane(direction, create_new_if_necessary, destroy_old_if_empty)


class CloneFileToPaneCommand(PaneCommand, WithSettings):
    def run(self, direction, create_new_if_necessary=None):
        if create_new_if_necessary is None:
            create_new_if_necessary = self.settings().get('create_new_pane_if_necessary')
        self.clone_file_to_pane(direction, create_new_if_necessary)


class CreatePaneWithFileCommand(PaneCommand):
    def run(self, direction):
        self.create_pane(direction)
        self.pull_file_from_pane(opposite_direction(direction))


class CreatePaneWithClonedFileCommand(PaneCommand):
    def run(self, direction):
        self.create_pane(direction)
        self.clone_file_to_pane(direction)


class PullFileFromPaneCommand(PaneCommand):
    def run(self, direction):
        self.pull_file_from_pane(direction)


class ZoomPaneCommand(PaneCommand):
    def run(self, fraction=None):
        self.zoom_pane(fraction)


class UnzoomPaneCommand(PaneCommand):
    def run(self):
        self.unzoom_pane()


class ToggleZoomPaneCommand(PaneCommand):
    def run(self, fraction=None):
        self.toggle_zoom(fraction)


class CreatePaneCommand(PaneCommand):
    def run(self, direction, give_focus=False):
        self.create_pane(direction, give_focus)


class DestroyPaneCommand(PaneCommand):
    def run(self, direction):
        self.destroy_pane(direction)


class ResizePaneCommand(PaneCommand):
    def run(self, orientation, mode=None):
        if mode is None:
            mode = "NEAREST"
        self.resize_panes(orientation, mode)


class ReorderPaneCommand(PaneCommand):
    def run(self):
        self.reorder_panes()

```

Here is an example of building (and cancelling with c):
```
~/Downloads/sublime_default/Main.sublime-menu:
  784                   { "command": "show_overlay", "args": {"overlay": "command_palette"}, "caption": "Command Palette…" },
  785                   { "command": "show_overlay", "args": {"overlay": "command_palette", "text": "Snippet: "}, "caption": "Snippets…" },
  786:                  { "caption": "-", "id": "build" },
  787                   {
  788:                          "caption": "Build System",
  789                           "mnemonic": "u",
  790                           "children":
  791                           [
  792:                                  { "command": "set_build_system", "args": { "file": "" }, "caption": "Automatic", "checkbox": true },
  793                                   { "caption": "-" },
  794:                                  { "command": "set_build_system", "args": {"index": 0}, "checkbox": true },
  795:                                  { "command": "set_build_system", "args": {"index": 1}, "checkbox": true },
  796:                                  { "command": "set_build_system", "args": {"index": 2}, "checkbox": true },
  797:                                  { "command": "set_build_system", "args": {"index": 3}, "checkbox": true },
  798:                                  { "command": "set_build_system", "args": {"index": 4}, "checkbox": true },
  799:                                  { "command": "set_build_system", "args": {"index": 5}, "checkbox": true },
  800:                                  { "command": "set_build_system", "args": {"index": 6}, "checkbox": true },
  801:                                  { "command": "set_build_system", "args": {"index": 7}, "checkbox": true },
  802:                                  { "command": "set_build_system", "args": {"index": 8}, "checkbox": true },
  803:                                  { "command": "set_build_system", "args": {"index": 9}, "checkbox": true },
  804:                                  { "command": "set_build_system", "args": {"index": 10}, "checkbox": true },
  805:                                  { "command": "set_build_system", "args": {"index": 11}, "checkbox": true },
  806                                   { "caption": "-" },
  807:                                  { "command": "$build_systems" },
  808                                   { "caption": "-" },
  809:                                  { "command": "new_build_system", "caption": "New Build System…" }
  810                           ]
  811                   },
  812:                  { "command": "build", "mnemonic": "B" },
  813:                  { "command": "build", "args": {"select": true}, "caption": "Build With…" },
  814:                  { "command": "cancel_build", "caption": "Cancel Build", "mnemonic": "C" },
  815                   {
  816:                          "caption": "Build Results",
  817                           "mnemonic": "R",
  818                           "children":
  819                           [
  820:                                  { "command": "show_panel", "args": {"panel": "output.exec"}, "caption": "Show Build Results", "mnemonic": "S" },
  821                                   { "command": "next_result", "mnemonic": "N" },
  822                                   { "command": "prev_result", "caption": "Previous Result", "mnemonic": "P" }
  823                           ]
  824                   },
  825:                  { "command": "toggle_save_all_on_build", "caption": "Save All on Build", "mnemonic": "A", "checkbox": true },
  826                   { "caption": "-", "id": "macros" },
  827                   { "command": "toggle_record_macro", "mnemonic": "M" },
```
