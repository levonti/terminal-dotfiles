from kube_fixture import install
import base64
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
BASH_SHELLS = list(dict.fromkeys(str(Path(p).resolve()) for p in (shutil.which("bash"), "/bin/bash") if p and Path(p).exists()))
SHELLS = BASH_SHELLS + (["zsh"] if shutil.which("zsh") else [])
sys.path.insert(0, str(ROOT / "kitty/.config/kitty"))
import tab_bar as tabs


def hook_block(shell):
    source = (ROOT / ("zsh/.zshrc" if shell == "zsh" else "bash/.bashrc")).read_text()
    block = source[source.index("# Publish "):]
    return block[:block.index("# Use compatible terminfo")] if shell == "zsh" else block


class TitleTests(unittest.TestCase):
    def setUp(self):
        tabs._remote_locations.clear()

    def test_paths_commands_and_remote_identity(self):
        cases = {
            "~": "~", "~/": "~", "/": "/", "~/work/project/": "project",
            "/srv/My Project": "My Project", "…/work/проект": "проект",
            "user@host: ~/work/project": "host:project",
            "host: ~": "host:~", "root@host: /srv/project": "root@host:project",
            "host: tmux new -s work": "host:tmux", "btop": "btop",
            "k8s: dev:example/app": "k8s:dev:example/app",
            "": "shell", "hi\x1b\nthere": "hithere",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(tabs.compact_title(source), expected)

    def render(self, title, name="", context="", active=True, remote=False,
               cwd="/work/project", at_prompt=True, argv=None, owner=None, kubie=True, reported="",
               metadata=True, kube_env=None, formatter=None, kube_category="", kube_namespace="", limit=0):
        state = dict(v=1, pid=os.getpid() if owner is None else owner,
                     phase="prompt" if at_prompt else "running", cwd=cwd,
                     context=context if kubie else "", command=(argv or [title])[0] if not at_prompt else "")
        if kube_env is not None:
            state["kube_env"] = kube_env
        if kube_category:
            state.update(kube_category=kube_category, kube_namespace=kube_namespace)
        window = SimpleNamespace(id=1, user_vars={"terminal_dotfiles_state": json.dumps(state)} if metadata else {},
            child_is_remote=remote, get_cwd_of_child=lambda: cwd, at_prompt=at_prompt,
            child=SimpleNamespace(pid=os.getpid(), foreground_environ={},
                                  foreground_cmdline=argv or ["zsh"]),
            screen=SimpleNamespace(last_reported_cwd=reported), last_cmd_cmdline=title)
        tab = SimpleNamespace(name=name, active_window=window)
        module = ModuleType("kitty.fast_data_types")
        module.get_boss = lambda: SimpleNamespace(tab_for_id=lambda _: tab)
        module.wcswidth = len
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": module}):
            return tabs.draw_title({"title": title, "tab_id": 1, "index": 3, "is_active": active, "fmt": formatter,
                                    "max_title_length": limit})

    def test_focus_preserves_label(self):
        for title in ("user@host: ~/project", "root@host: ~", "~", "~/project"):
            self.assertEqual(self.render(title, active=True), self.render(title, active=False))

    def test_explicit_names_are_verbatim_and_override_context(self):
        self.assertEqual(self.render("kubie ctx", name="Deploy: production console",
                                     context="[☸ DEV example::default]", kube_env="DEV"), "Deploy: production console")

    def test_context_survives_running_commands_and_clears_after_exit(self):
        self.assertEqual(self.render("htop", context="[☸ DEV example::app]", kube_env="DEV", at_prompt=False, argv=["htop"]),
                         "DEV example::app htop")
        # Simulate returning to a parent which never loaded the new hooks.
        self.assertEqual(self.render("~", context="[☸ DEV example::app]", kubie=False), "project")

    def test_exited_metadata_owner_is_rejected_even_in_another_kubie_shell(self):
        with patch.object(tabs.os, "getsid", side_effect=ProcessLookupError):
            self.assertEqual(self.render("~", context="[☸ example::app]", kube_env="PROD"), "project")

    def test_unscoped_legacy_metadata_is_rejected(self):
        window = SimpleNamespace(child_is_remote=False, child=SimpleNamespace(foreground_environ={"KUBIE_ACTIVE": "1"}),
                                 user_vars={"terminal_dotfiles_kubie": "k8s: dev:example/app"})
        self.assertEqual(tabs.kubie_label(window), "")

    def test_local_commands_keep_directory_without_exposing_arguments(self):
        self.assertEqual(self.render("htop --sort PERCENT_CPU", at_prompt=False, argv=["/bin/htop"]), "project htop")
        self.assertEqual(self.render("curl secret-argument", at_prompt=False, argv=["curl", "secret-argument"]), "project curl")
        self.assertEqual(self.render("~", cwd=str(Path.home())), "~")

    def test_preexec_title_before_command_start_marker_already_shows_command(self):
        self.assertEqual(self.render("htop", at_prompt=True, argv=["zsh"], metadata=False), "project htop")

    def test_kubie_prompt_ignores_wrapper_and_foreground_environment(self):
        self.assertEqual(self.render("kubie ctx", context="[☸ example::app]", argv=["kubie"]),
                         "[☸ example::app]")

    def test_actual_program_overrides_stale_bash_history_hint(self):
        state = dict(v=1, pid=os.getpid(), phase="running", cwd="/work/project", context="", command="kubie")
        window = SimpleNamespace(id=1, child_is_remote=False, at_prompt=False,
            user_vars={"terminal_dotfiles_state": json.dumps(state)},
            child=SimpleNamespace(pid=os.getpid(), foreground_cmdline=["/bin/htop"]))
        self.assertEqual(tabs.window_title(window, "kubie ctx", tabs.shell_state(window)), "project htop")

    def test_different_terminal_session_is_rejected(self):
        with patch.object(tabs.os, "getsid", side_effect=[10, 20]):
            self.assertEqual(self.render("~", context="[☸ other]"), "project")

    def test_legacy_kubernetes_snapshot_keeps_the_colored_icon(self):
        title = "[☸ example::app]"
        for background in ((136, 192, 208), (37, 44, 58)):
            for color in ((191, 97, 106), (163, 190, 140), (235, 203, 139), (180, 142, 173)):
                formatter = SimpleNamespace(fg=SimpleNamespace(tab="\x1b[38;2;23;27;36m"),
                    bg=SimpleNamespace(tab=f"\x1b[48;2;{background[0]};{background[1]};{background[2]}m"))
                raw = f"[\x1b[1;38;2;{color[0]};{color[1]};{color[2]}m☸\x1b[0m example::app]"
                styled = tabs.kubernetes_title({"context": raw}, formatter)
                self.assertEqual(tabs.plain_title(styled), title)
                self.assertIn("☸" + formatter.fg.tab + " example::app", styled)
                self.assertNotIn("48;", styled)
                icon_color = tabs.sgr_rgb(styled.split("☸", 1)[0], 38)
                self.assertGreaterEqual(tabs.contrast(icon_color, background), 3)

    def test_kubernetes_badge_keeps_the_environment_without_color_and_restores_tab_colors(self):
        for environment, context, cluster, color in (
            ("DEV", "[☸ DEV prod-simulator::app]", "prod-simulator", "a3be8c"),
            ("TEST", "[☸ TEST example::app]", "example", "ebcb8b"),
            ("PROD", "[☸ DEV sandbox::app]", "DEV sandbox", "ed8796"),
            ("?ENV", "[☸ ? ENV example::app]", "example", "c1a7d5"),
        ):
            expected = f"{environment} {cluster}::app"
            rgb = bytes.fromhex(color)
            fill = f"\x1b[48:2::{rgb[0]}:{rgb[1]}:{rgb[2]}m"
            text = "\x1b[38:2::23:27:36m"
            self.assertGreaterEqual(tabs.contrast(rgb, (23, 27, 36)), 4.5)
            for background in ("136:192:208", "37:44:58"):
                formatter = SimpleNamespace(fg=SimpleNamespace(_171b24=text, tab="\x1b[38:2::185:195:212m"),
                    bg=SimpleNamespace(tab=f"\x1b[48:2::{background}m", **{"_" + color: fill}))
                result = self.render("~", context=context, kube_env=environment, formatter=formatter)
                self.assertEqual(tabs.plain_title(result), expected)
                self.assertTrue(result.startswith(fill + text + "\x1b[1m" + environment + "\x1b[22m" + formatter.bg.tab + formatter.fg.tab + " "))
            self.assertEqual(self.render("~", context=context, kube_env=environment), expected)

    def test_kubernetes_badge_preserves_nonstandard_starship_text(self):
        self.assertEqual(self.render("~", context="kube example/app", kube_env="TEST"), "TEST kube example/app")
        self.assertEqual(self.render("~", context="[☸ example::app]", kube_env=[]), "[☸ example::app]")

    def test_bounded_template_preserves_category_and_literal_alias(self):
        api = ModuleType("kitty.tab_bar")
        api.truncate_line = lambda value, width: value[:width - 1] + "…"
        with patch.dict(sys.modules, {"kitty.tab_bar": api}):
            for limit, expected in ((10, "PROD"), (15, "PROD PUBLIC"), (40, "PROD PUBLIC [☸ core::app]")):
                with self.subTest(limit=limit):
                    self.assertEqual(self.render("~", context="[☸ core::app]", kube_env="PROD",
                                                 kube_category="PUBLIC", limit=limit), expected)
            for environment in (None, 42):
                self.assertEqual(self.render("~", context="core01", kube_env=environment,
                                             kube_category="PUBLIC", limit=15), "core01")

    def test_narrow_kubie_title_keeps_complete_badges_before_cluster_and_namespace(self):
        fast = ModuleType("kitty.fast_data_types")
        fast.wcswidth = len
        api = ModuleType("kitty.tab_bar")
        api.truncate_line = lambda value, width: value[:width - 1] + "…"
        state = dict(context="core / east / long-namespace", kube_env="UAT", kube_color="88c0d0",
                     kube_category="PUBLIC", kube_namespace="long-namespace")
        title = " 3 " + tabs.kubernetes_title(state, None) + " htop"
        self.assertEqual(title, " 3 UAT PUBLIC core / east / long-namespace htop")
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast, "kitty.tab_bar": api}):
            for width, expected in (
                (6, " 3 UAT"),
                (12, " 3 UAT"),
                (13, " 3 UAT PUBLIC"),
                (18, " 3 UAT PUBLIC cor…"),
                (25, " 3 UAT PUBLIC core / east"),
                (30, " 3 UAT PUBLIC core / east htop"),
                (34, " 3 UAT PUBLIC core / east / … htop"),
                (35, " 3 UAT PUBLIC core / east / l… htop"),
            ):
                with self.subTest(width=width):
                    result = tabs.fit_kubernetes_title(title, width, state, "htop")
                    self.assertEqual(result, expected)
                    self.assertLessEqual(len(result), width)
            command = "longer-than-the-full-tab-width-executable"
            self.assertEqual(tabs.fit_kubernetes_title(title.removesuffix("htop") + command, 42, state, command),
                             " 3 UAT PUBLIC core / east / long-namespace")

    def test_return_to_parent_invalidates_same_frame_cache(self):
        child = SimpleNamespace(pid=os.getpid(), pid_for_cwd=101, foreground_cmdline=["zsh"])
        window = SimpleNamespace(id=1, child=child, child_is_remote=False, at_prompt=True,
            user_vars={"terminal_dotfiles_state": json.dumps(dict(v=1, pid=os.getpid(), phase="prompt",
                       cwd="/work/project", context="[☸ DEV example::app]", command=""))},
            get_cwd_of_child=lambda: "/work/project")
        tab = SimpleNamespace(name="", active_window=window)
        fast = ModuleType("kitty.fast_data_types")
        fast.get_boss = lambda: SimpleNamespace(tab_for_id=lambda _: tab)
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast}), patch.object(tabs, "monotonic", return_value=10), patch.object(tabs.os, "getsid", side_effect=[1, 1, ProcessLookupError]):
            self.assertEqual(tabs.draw_title({"tab_id": 1, "title": "~"}), "[☸ DEV example::app]")
            child.pid_for_cwd = 100
            self.assertEqual(tabs.draw_title({"tab_id": 1, "title": "~"}), "project")

    def test_remote_commands_keep_last_remote_directory_and_ignore_local_kubie(self):
        self.assertEqual(self.render("user@host: /srv/project", remote=True), "host:project")
        self.assertEqual(self.render("user@host: htop -d 5", remote=True,
                                     context="[☸ DEV local::app]", kube_env="DEV"), "host:project htop")
        self.assertEqual(self.render("htop", remote=True), "host:project htop")
        self.assertEqual(self.render("user@host: /srv/project", remote=True), "host:project")

    def test_remote_reported_path_and_change_of_host(self):
        self.assertEqual(self.render("root@host: htop", remote=True, reported="file://host/srv/project"), "root@host:project htop")
        self.assertEqual(self.render("user@other: htop", remote=True), "other htop")

    def test_remote_combined_title(self):
        self.assertEqual(self.render("user@host: /srv/project · htop", remote=True), "host:project htop")

    def test_new_local_session_discards_remote_location(self):
        self.render("user@host: /srv/old", remote=True)
        self.render("~", kubie=False)
        self.assertEqual(self.render("user@host: htop", remote=True), "host htop")

    def test_long_titles_keep_the_running_command_visible(self):
        fast = ModuleType("kitty.fast_data_types")
        fast.wcswidth = len
        api = ModuleType("kitty.tab_bar")
        api.truncate_line = lambda text, width: text[:max(0, width - 1)] + "…"
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast, "kitty.tab_bar": api}):
            for width in (12, 20, 28, 40):
                result = tabs.fit_title(" 1 host:very-long-project-name-for-testing htop", width)
                self.assertLessEqual(len(result), width)
                self.assertTrue(result.startswith(" 1 "))
                self.assertTrue(result.endswith(" htop"))
            host = "worker-test-long-name.example.invalid"
            result = tabs.fit_title(f" 2 ssh {host}", 39)
            self.assertEqual(result, f" 2 ssh {host[:31]}…")

    def test_kubernetes_badge_survives_narrow_titles_with_a_long_suffix(self):
        fast = ModuleType("kitty.fast_data_types")
        fast.wcswidth = len
        api = ModuleType("kitty.tab_bar")

        def truncate_line(text, width):
            # Keep formatting sequences intact and count only visible cells.
            parts = re.split(r"(\x1b\[[0-9;:]*m)", text)
            for index in range(0, len(parts), 2):
                if len(parts[index]) >= width:
                    return "".join(parts[:index]) + parts[index][:width - 1] + "…"
                width -= len(parts[index])
            return text + "…"

        api.truncate_line = truncate_line
        title = " 3 \x1b[48:2::237:135:150m\x1b[38:2::23:27:36mPROD\x1b[48:2::136:192:208m core01::app project long-command"
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast, "kitty.tab_bar": api}):
            for width in (7, 8, 11, 12, 16, 20):
                result = tabs.fit_title(title, width)
                self.assertLessEqual(len(re.sub(r"\x1b\[[0-9;:]*m", "", result)), width)
                self.assertTrue(tabs.plain_title(result).startswith("3 PROD"))


class LayoutTests(unittest.TestCase):
    snapshot = ([(59, 1_000_000, 250_000), (60, 0, 0)], 1_000_000, 250_000, "ready")

    def test_network_panel_survives_tab_alignment(self):
        class Screen:
            def __init__(self, columns):
                self.columns = columns
                self.cursor = SimpleNamespace(x=0, fg=0, bg=0, bold=False, italic=False)
                self.row = " " * columns

            def draw(self, value):
                start = self.cursor.x
                self.cursor.x += len(value)
                self.row = (self.row[:start] + value + self.row[self.cursor.x:])[:self.columns]

            def insert_characters(self, count):
                start = self.cursor.x
                self.row = (self.row[:start] + " " * count + self.row[start:])[:self.columns]

        def extent(start, end):
            return SimpleNamespace(x=SimpleNamespace(start=start, end=end),
                                   shifted=lambda x: extent(start + x, end + x))

        fast = ModuleType("kitty.fast_data_types")
        fast.wcswidth = len
        api = ModuleType("kitty.tab_bar")
        api.apply_title_template = lambda draw_data, tab, index: f" {index} {tab.title} "
        api.draw_attributed_string = lambda value, screen: screen.draw(value)
        api.draw_tab_with_fade = self.fail
        utils = ModuleType("kitty.utils")
        utils.color_as_int = int
        modules = {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast,
                   "kitty.tab_bar": api, "kitty.utils": utils}
        draw_data = SimpleNamespace(os_window_id=1, tab_bar_edge="top", max_tab_title_length=40,
                                    tab_bg=lambda _: 0, tab_fg=lambda _: 0, default_bg=0)
        tab = SimpleNamespace(title="project")
        tab._replace = lambda **_: tab
        for alignment, factor in (("center", 2), ("end", 1)):
            for columns, expected_panel_width in ((120, 45), (50, 27), (30, 0)):
                with self.subTest(alignment=alignment, columns=columns):
                    screen = Screen(columns)
                    bar = SimpleNamespace(tab_bar_align=alignment, last_laid_out_tabs=(tab,))
                    fast.get_boss = lambda: SimpleNamespace(os_window_map={1: SimpleNamespace(tab_bar=bar)})

                    def align():
                        # Kitty inserts cells before the entire rendered row.
                        end = bar.tab_extents[-1].x.end
                        shift = (columns - end) // factor
                        screen.cursor.x = 0
                        screen.insert_characters(shift)
                        bar.tab_extents = tuple(te.shifted(x=shift) for te in bar.tab_extents)

                    bar.align = align
                    with patch.dict(sys.modules, modules), patch.object(tabs.sys, "platform", "linux"), \
                            patch.object(tabs, "get_monitor", return_value=SimpleNamespace(snapshot=lambda: self.snapshot)):
                        tabs.draw_tab(draw_data, screen, tab, 0, columns, 1, True, SimpleNamespace(for_layout=True))
                        self.assertIs(bar.align, align)
                        screen.cursor.x = 0
                        end = tabs.draw_tab(draw_data, screen, tab, 0, columns, 1, True, SimpleNamespace(for_layout=False))

                    bar.tab_extents = (extent(0, end),)
                    bar.align()
                    self.assertIs(bar.align, align)
                    hit = bar.tab_extents[0].x
                    self.assertEqual(screen.row[hit.start:hit.end], " 1 project")
                    if expected_panel_width:
                        panel_start = columns - expected_panel_width
                        self.assertTrue(screen.row[panel_start:].startswith(" Linux ↓"))
                        self.assertIn("↑", screen.row[panel_start:])
                        self.assertEqual(hit.start, (panel_start - end - 2) // factor)
                        self.assertLess(hit.end, panel_start - 1)
                    else:
                        self.assertEqual(hit.start, (columns - end) // factor)
                        self.assertNotIn("Linux", screen.row)

    def test_tabs_take_priority_at_eight_tabs_in_requested_sizes(self):
        desired = [14, 16, 12, 20, 18, 10, 24, 23]
        for columns in (80, 120, 160):
            for platform in ("darwin", "linux"):
                with self.subTest(columns=columns, platform=platform):
                    _, panel = tabs.format_panel(self.snapshot, max(0, columns - sum(desired) - 1), 60, platform)
                    widths = tabs.allocate_widths(desired, columns - panel - 1)
                    self.assertTrue(all(w >= 8 for w in widths))
                    self.assertLessEqual(sum(widths) + panel + 1, columns)
                    self.assertEqual(widths, tabs.allocate_widths(desired, columns - 1))

    def test_panel_uses_only_spare_space_and_shrinks_in_three_stages(self):
        for platform, expected in (("darwin", (0, 25, 43)), ("linux", (0, 27, 45))):
            widths = [tabs.format_panel(self.snapshot, budget, 60, platform)[1] for budget in (20, 30, 50)]
            self.assertEqual(tuple(widths), expected)

    def test_old_119_120_boundary_has_no_effect(self):
        desired = [12] * 8
        for columns in (119, 120):
            _, panel = tabs.format_panel(self.snapshot, columns - sum(desired) - 1, 60, "darwin")
            self.assertEqual(panel, 0)
            self.assertEqual(tabs.allocate_widths(desired, columns - 1), desired)

    def test_root_priority_does_not_starve_other_tabs(self):
        widths = tabs.allocate_widths([28] * 8, 100, (2,))
        self.assertEqual(widths[2], 28)
        self.assertTrue(all(w >= 8 for w in widths))
        self.assertEqual(sum(widths), 100)


class ShellMetadataTests(unittest.TestCase):
    def run_hook(self, shell, active="1", failing=False, array=False, context=None, quoted_directory=False,
                 custom_kubeconfig=False, kubie_available=True):
        # Exercise the complete registration block without loading private rc files.
        block = hook_block(shell)
        with TemporaryDirectory() as directory:
            install(directory)
            binary = Path(directory) / "starship"
            binary.write_text("#!/bin/sh\n" + ("exit 1\n" if failing else
                              'case "$*" in "module kubernetes") printf "\\033[32m[☸ DEV example::app]\\033[0m ";; *) exit 90;; esac\n'))
            if context is not None:
                binary.write_text(f'#!/bin/sh\nexec {shutil.which("starship")} "$@"\n')
            binary.chmod(0o755)
            if kubie_available:
                kubie = Path(directory) / "kubie"
                kubie.write_text(f'#!/bin/sh\n[ "$*" = "info ctx" ] || exit 90\nprintf "%s\\n" "{context or "dev:example"}"\n')
                kubie.chmod(0o755)
            config = Path(directory) / "kubeconfig"
            config.write_text(f'apiVersion: v1\nkind: Config\ncurrent-context: {context or "dev:example"}\n'
                              f'contexts:\n- name: {context or "dev:example"}\n  context:\n    cluster: example\n'
                              '    user: example\n    namespace: app\nclusters:\n- name: example\n'
                              '  cluster:\n    server: https://example.invalid\nusers:\n- name: example\n  user: {}\n')
            source = Path(directory) / '.kube/configs/lab/dev/fixture.yaml'
            source.parent.mkdir(parents=True)
            source.write_text(config.read_text())
            (Path(directory) / '.kube/kubie.yaml').write_text('configs:\n  include: ["~/.kube/configs/**/*.yaml"]\n')
            if failing or not kubie_available:
                (Path(directory) / '.config/terminal-dotfiles/kube-environment').unlink()
            env = {**os.environ, "HOME": directory, "KITTY_WINDOW_ID": "42", "KUBIE_ACTIVE": active,
                   "PATH": f"{directory}:/usr/bin:/bin", "SSH_TTY": "", "SSH_CONNECTION": "", "TERM": "dumb",
                   "STARSHIP_CONFIG": str(ROOT / "starship/.config/starship.toml"), "KUBECONFIG": str(config),
                   "KUBIE_KUBECONFIG": str(config.with_suffix(".kubie") if custom_kubeconfig else config)}
            cwd = Path(directory) / 'quoted"path\\name' if quoted_directory else ROOT
            if quoted_directory:
                cwd.mkdir()
            prefix = 'PROMPT_COMMAND=("printf preserved")\n' if array else 'PROMPT_COMMAND="printf preserved"\n'
            script = prefix + block + "\n" + block + "\n_terminal_dotfiles_kubie_title\n"
            if shell == "zsh":
                script += 'print -r -- "${precmd_functions[*]}"\n'
            else:
                script += 'printf "%s\\n" "${PROMPT_COMMAND[*]}"\n'
            result = subprocess.run([shell, "-fc" if shell == "zsh" else "--noprofile", *(
                [] if shell == "zsh" else ["--norc", "-c"]), script],
                env=env, cwd=cwd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_both_shells_publish_context_and_register_once(self):
        for shell in SHELLS:
            output = self.run_hook(shell)
            value = re.search(r"SetUserVar=terminal_dotfiles_state=([^\a]+)\a", output)[1]
            state = json.loads(base64.b64decode(value))
            self.assertGreater(state["pid"], 0)
            self.assertEqual(tabs.plain_title(state["context"]), "dev:example / app")
            self.assertEqual(state["kube_env"], "DEV")
            self.assertEqual(state["kube_category"], "LAB")
            self.assertEqual(state["kube_namespace"], "app")
            self.assertEqual(state["phase"], "prompt")
            self.assertEqual(output.count("_terminal_dotfiles_kubie_title"), 1)

    def test_context_name_does_not_override_directory(self):
        for shell in SHELLS:
            output = self.run_hook(shell, context="prod:arbitrary")
            value = re.search(r"SetUserVar=terminal_dotfiles_state=([^\a]+)\a", output)[1]
            state = json.loads(base64.b64decode(value))
            self.assertEqual(state["kube_env"], "DEV")
            self.assertEqual(state["context"], "prod:arbitrary / app")

    def test_outer_shell_and_failed_reads_clear_stale_context(self):
        for shell in SHELLS:
            for options in ({"active": ""}, {"failing": True}):
                output = self.run_hook(shell, **options)
                value = re.search(r"SetUserVar=terminal_dotfiles_state=([^\a]+)\a", output)[1]
                state = json.loads(base64.b64decode(value))
                self.assertEqual(state["context"], "")
                self.assertEqual(state["kube_env"], "")
                self.assertEqual(state["kube_category"], "")
                self.assertEqual(state["kube_namespace"], "")

    def test_unverified_environment_keeps_starship_context_without_badge(self):
        for shell in SHELLS:
            for options in ({"custom_kubeconfig": True}, {"kubie_available": False}):
                output = self.run_hook(shell, **options)
                value = re.search(r"SetUserVar=terminal_dotfiles_state=([^\a]+)\a", output)[1]
                state = json.loads(base64.b64decode(value))
                self.assertEqual(state["kube_env"], "")
                self.assertEqual(state["context"], "")

    def test_bash_preserves_scalar_and_array_prompt_commands(self):
        for shell in BASH_SHELLS:
            for array in (False, True):
                self.assertIn("printf preserved", self.run_hook(shell, array=array))

    def test_snapshot_escapes_directory_quotes_and_backslashes(self):
        for shell in SHELLS:
            output = self.run_hook(shell, quoted_directory=True)
            value = re.search(r"SetUserVar=terminal_dotfiles_state=([^\a]+)\a", output)[1]
            self.assertTrue(json.loads(base64.b64decode(value))["cwd"].endswith('quoted"path\\name'))

    def test_protocol_is_not_registered_in_remote_shells(self):
        for shell in SHELLS:
            probe = '(( $+functions[_terminal_dotfiles_publish_state] ))' if shell == "zsh" else 'declare -F _terminal_dotfiles_publish_state >/dev/null'
            script = hook_block(shell) + f'\nif {probe}; then printf installed; else printf absent; fi\n'
            env = {**os.environ, "KITTY_WINDOW_ID": "42", "SSH_CONNECTION": "fixture", "PATH": "/usr/bin:/bin"}
            args = [shell, "-fc", script] if shell == "zsh" else [shell, "--noprofile", "--norc", "-c", script]
            result = subprocess.run(args, env=env, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout, "absent")


class MetadataLifecycleTests(unittest.TestCase):
    def test_real_shell_exit_invalidates_metadata_without_parent_refresh(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), TemporaryDirectory() as directory:
                helper = Path(directory) / ".config/terminal-dotfiles"
                helper.mkdir(parents=True)
                starship = helper / "kube-environment"
                starship.write_text("#!/bin/sh\nprintf 'DEV\\ta3be8c\\t[☸ DEV example::app]\\n'\n")
                starship.chmod(0o755)
                script = hook_block(shell) + "\n_terminal_dotfiles_kubie_title\nbuiltin read -r line\n"
                env = {**os.environ, "HOME": directory, "KITTY_WINDOW_ID": "42", "KUBIE_ACTIVE": "1",
                       "SSH_TTY": "", "SSH_CONNECTION": "", "PATH": f"{directory}:/usr/bin:/bin"}
                args = [shell, "-fc", script] if shell == "zsh" else [shell, "--noprofile", "--norc", "-c", script]
                proc = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    output = b""
                    deadline = monotonic() + 3
                    while b"\a" not in output and monotonic() < deadline:
                        if select.select([proc.stdout], [], [], 0.1)[0]:
                            output += os.read(proc.stdout.fileno(), 4096)
                    value = re.search(rb"SetUserVar=terminal_dotfiles_state=([^\a]+)\a", output)
                    self.assertIsNotNone(value)
                    decoded = base64.b64decode(value[1]).decode()
                    window = SimpleNamespace(child_is_remote=False,
                        child=SimpleNamespace(pid=proc.pid),
                        user_vars={"terminal_dotfiles_state": decoded})
                    self.assertEqual(tabs.kubie_label(window), "[☸ DEV example::app]")
                    proc.stdin.close()
                    proc.wait(timeout=3)
                    # The parent never sends a clear; the exited PID is enough.
                    self.assertEqual(tabs.kubie_label(window), "")
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        stream.close()


if __name__ == "__main__":
    unittest.main()
