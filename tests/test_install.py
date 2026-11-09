"""Exercise the installers against disposable home directories."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
STOW = shutil.which("stow")
ZSH = shutil.which("zsh")
MANAGED = {
    ".zshrc": "zsh/.zshrc",
    ".config/terminal-dotfiles/ssh.zsh": "zsh/.config/terminal-dotfiles/ssh.zsh",
    ".config/kitty/kitty.conf": "kitty/.config/kitty/kitty.conf",
    ".config/kitty/tab_bar.py": "kitty/.config/kitty/tab_bar.py",
    ".config/starship.toml": "starship/.config/starship.toml",
}
ORIGINALS = {
    ".zshrc": "previous zsh configuration\n",
    ".config/kitty/kitty.conf": "previous kitty configuration\n",
    ".config/starship.toml": "previous starship configuration\n",
}


@unittest.skipUnless(STOW, "GNU Stow is required")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        fixture = TemporaryDirectory(prefix="dotfiles install ")
        self.addCleanup(fixture.cleanup)
        self.work = Path(fixture.name).resolve()
        self.home = self.work / "home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home))
        for variable in ("ZDOTDIR", "KITTY_CONFIG_DIRECTORY", "XDG_CONFIG_HOME", "KITTY_WINDOW_ID"):
            self.env.pop(variable, None)

    def write_originals(self):
        for relative, contents in ORIGINALS.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)

    def run_installer(self, name, *args):
        return subprocess.run(
            ["sh", str(ROOT / "scripts" / name), *args],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def backups(self):
        return sorted(self.home.glob(".terminal-dotfiles-backup.*"))

    def fail_stow_after_apply(self):
        bin_dir = self.work / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "stow"
        wrapper.write_text(
            f"#!/bin/sh\n{shlex.quote(STOW)} \"$@\" || exit $?\n"
            'if [ "$1" != --simulate ]; then exit 42; fi\n'
        )
        wrapper.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env['PATH']}"
        return bin_dir

    def test_check_and_migration_preserve_originals_and_local_files(self):
        self.write_originals()
        local = self.home / ".zshrc.local"
        local.write_text("personal settings\n")
        (self.home / ".stowrc").write_text("--simulate\n--adopt\n")
        (self.work / ".stowrc").write_text("--ignore=.*\n")

        preview = self.run_installer("install.sh", "--check")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(preview.stdout.count("Back up and link:"), 3)
        self.assertFalse(self.backups())
        for relative, contents in ORIGINALS.items():
            self.assertEqual((self.home / relative).read_text(), contents)
            self.assertFalse((self.home / relative).is_symlink())
        self.assertFalse((self.home / ".config/terminal-dotfiles").exists())

        install = self.run_installer("install.sh", "--migrate")
        self.assertEqual(install.returncode, 0, install.stderr)
        backup, = self.backups()
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        for relative, contents in ORIGINALS.items():
            self.assertEqual((backup / relative).read_text(), contents)
        for relative, source in MANAGED.items():
            link = self.home / relative
            self.assertTrue(link.is_symlink(), relative)
            self.assertEqual(link.resolve(), ROOT / source)
        self.assertEqual(local.read_text(), "personal settings\n")

        repeated = self.run_installer("install.sh", "--migrate")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(repeated.stdout.count("Already linked:"), 5)
        self.assertEqual(self.backups(), [backup])

    def test_foreign_symlink_blocks_migration_before_backup(self):
        self.write_originals()
        link = self.home / ".config/kitty/tab_bar.py"
        link.symlink_to(self.work / "outside")

        install = self.run_installer("install.sh", "--migrate")
        self.assertNotEqual(install.returncode, 0)
        self.assertIn(str(link), install.stderr)
        self.assertEqual(link.readlink(), self.work / "outside")
        self.assertFalse(self.backups())
        self.assertEqual((self.home / ".zshrc").read_text(), ORIGINALS[".zshrc"])

    @unittest.skipUnless(ZSH, "Zsh is required to exercise compiled startup files")
    def test_migration_backs_up_compiled_rc_and_zsh_loads_shared_config(self):
        rc = self.home / ".zshrc"
        compiled = self.home / ".zshrc.zwc"
        rc.write_text("typeset -g INSTALL_TEST_RC=compiled\n")
        subprocess.run(
            [ZSH, "-fc", 'zcompile "$1" "$2"', "zsh", str(compiled), str(rc)],
            env=self.env,
            check=True,
            timeout=10,
        )
        rc.write_text(ORIGINALS[".zshrc"])
        newer = max(compiled.stat().st_mtime, (ROOT / "zsh/.zshrc").stat().st_mtime) + 10
        os.utime(compiled, (newer, newer))
        compiled_contents = compiled.read_bytes()
        self.env["TERM"] = "xterm-256color"

        def start_zsh(command):
            result = subprocess.run(
                [ZSH, "-ic", command], cwd=self.work, env=self.env,
                stdin=subprocess.DEVNULL, start_new_session=True,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        start_zsh('[[ ${INSTALL_TEST_RC-} == compiled ]]')
        preview = self.run_installer("install.sh", "--check")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn(str(compiled), preview.stdout)
        self.assertEqual(compiled.read_bytes(), compiled_contents)

        install = self.run_installer("install.sh", "--migrate")
        self.assertEqual(install.returncode, 0, install.stderr)
        backup, = self.backups()
        self.assertEqual((backup / compiled.name).read_bytes(), compiled_contents)
        self.assertFalse(compiled.exists())
        start_zsh('[[ -z ${INSTALL_TEST_RC-} && ${aliases[k]-} == kubectl ]]')

    def test_alternate_zsh_and_kitty_directories_block_migration(self):
        self.write_originals()
        xdg_kitty = self.home / "xdg/kitty"
        xdg_kitty.mkdir(parents=True)
        (xdg_kitty / "kitty.conf").write_text("existing configuration\n")
        original_env = self.env.copy()

        for variable, value, expected, active in (
            ("ZDOTDIR", self.work, self.home, self.work),
            ("KITTY_CONFIG_DIRECTORY", self.work, self.home / ".config/kitty", self.work),
            ("XDG_CONFIG_HOME", "~/xdg", self.home / ".config/kitty", xdg_kitty),
        ):
            self.env = dict(original_env, **{variable: str(value)})
            for mode in ("--check", "--migrate"):
                with self.subTest(variable=variable, mode=mode):
                    result = self.run_installer("install.sh", mode)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(variable, result.stderr)
                    self.assertIn(str(expected), result.stderr)
                    self.assertIn(str(active), result.stderr)
                    self.assertEqual((self.home / ".zshrc").read_text(), ORIGINALS[".zshrc"])
                    self.assertFalse(self.backups())

    def test_check_accepts_default_config_paths(self):
        self.env.update(ZDOTDIR=str(self.home), XDG_CONFIG_HOME=str(self.work / "xdg"))
        result = self.run_installer("install.sh", "--check")
        self.assertEqual(result.returncode, 0, result.stderr)

        xdg_kitty = self.work / "xdg/kitty"
        xdg_kitty.mkdir(parents=True)
        (xdg_kitty / "kitty.conf").touch()
        self.env["KITTY_CONFIG_DIRECTORY"] = "~/.config/kitty/"
        result = self.run_installer("install.sh", "--check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_read_only_parent_fails_before_moving_originals(self):
        self.write_originals()
        for relative in (".config/kitty", ".config"):
            directory = self.home / relative
            directory.chmod(0o500)
            try:
                if os.access(directory, os.W_OK):
                    self.skipTest("Current user can write to a mode-0500 directory")
                for mode in ("--check", "--migrate"):
                    with self.subTest(directory=relative, mode=mode):
                        result = self.run_installer("install.sh", mode)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(f"Need write and search permissions on {directory}", result.stderr)
                        self.assertEqual((self.home / ".zshrc").read_text(), ORIGINALS[".zshrc"])
                        self.assertFalse(self.backups())
            finally:
                directory.chmod(0o700)

    def test_failed_stow_rolls_back_only_this_run(self):
        self.write_originals()
        compiled = self.home / ".zshrc.zwc"
        compiled.write_bytes(b"compiled configuration")
        existing = self.home / ".config/kitty/tab_bar.py"
        source = ROOT / MANAGED[".config/kitty/tab_bar.py"]
        existing.symlink_to(source)
        self.fail_stow_after_apply()

        install = self.run_installer("install.sh", "--migrate")
        self.assertEqual(install.returncode, 42, install.stderr)
        self.assertNotIn("configuration installed", install.stdout)
        for relative, contents in ORIGINALS.items():
            path = self.home / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_text(), contents)
        self.assertEqual(existing.readlink(), source)
        self.assertEqual(compiled.read_bytes(), b"compiled configuration")
        self.assertFalse((self.home / ".config/terminal-dotfiles").exists())
        self.assertFalse((self.home / ".terminal-dotfiles-install.lock").exists())
        self.assertFalse(self.backups())

    def test_rollback_preserves_a_concurrently_created_config(self):
        self.write_originals()
        rc = self.home / ".zshrc"
        bin_dir = self.fail_stow_after_apply()
        for program in ("mv", "perl"):
            wrapper = bin_dir / program
            executable = shlex.quote(shutil.which(program))
            wrapper.write_text(
                "#!/bin/sh\n"
                "for destination do :; done\n"
                f'if [ "$destination" = {shlex.quote(str(rc))} ]; then\n'
                '  printf "%s\\n" "new configuration" > "$destination"\n'
                "fi\n"
                f'exec {executable} "$@"\n'
            )
            wrapper.chmod(0o755)

        install = self.run_installer("install.sh", "--migrate")
        self.assertEqual(install.returncode, 42, install.stderr)
        self.assertEqual(rc.read_text(), "new configuration\n")
        backup, = self.backups()
        self.assertEqual((backup / rc.name).read_text(), ORIGINALS[rc.name])
        self.assertIn(f"Cannot restore {rc}", install.stderr)
        self.assertIn(str(backup), install.stderr)
        kitty_config = ".config/kitty/kitty.conf"
        self.assertEqual((self.home / kitty_config).read_text(), ORIGINALS[kitty_config])

    def test_rollback_preserves_a_file_that_replaces_an_installed_link(self):
        self.write_originals()
        rc = self.home / ".zshrc"
        replacement = self.work / "replacement rc"
        replacement.write_text("replacement configuration\n")
        replacement_inode = replacement.stat().st_ino
        bin_dir = self.fail_stow_after_apply()
        for program in ("rm", "perl"):
            wrapper = bin_dir / program
            executable = shlex.quote(shutil.which(program))
            wrapper.write_text(
                "#!/bin/sh\n"
                "previous=\n"
                "last=\n"
                'for argument do previous=$last; last=$argument; done\n'
                f'target={shlex.quote(str(rc))}\n'
                'if { [ "$previous" = "$target" ] || [ "$last" = "$target" ]; } && [ -L "$target" ]; then\n'
                f'  mv -f {shlex.quote(str(replacement))} "$target" || exit $?\n'
                "fi\n"
                f'exec {executable} "$@"\n'
            )
            wrapper.chmod(0o755)

        install = self.run_installer("install.sh", "--migrate")
        self.assertEqual(install.returncode, 42, install.stderr)
        self.assertFalse(replacement.exists())
        self.assertFalse(rc.is_symlink())
        self.assertEqual(rc.read_text(), "replacement configuration\n")
        self.assertEqual(rc.stat().st_ino, replacement_inode)
        backup, = self.backups()
        self.assertEqual((backup / rc.name).read_text(), ORIGINALS[rc.name])
        self.assertIn(str(backup), install.stderr)
        self.assertFalse(list(self.home.rglob(".terminal-dotfiles-rollback.*")))

    def test_bash_rejects_simulated_success_and_restores_original(self):
        bashrc = self.home / ".bashrc"
        bashrc.write_text("previous bash configuration\n")
        stowrc = self.home / ".stowrc"
        stowrc.write_text("--simulate\n")

        install = self.run_installer("install-bash.sh")
        self.assertNotEqual(install.returncode, 0)
        self.assertIn("expected ~/.bashrc symlink", install.stderr)
        self.assertNotIn("configuration installed", install.stdout)
        self.assertFalse(bashrc.is_symlink())
        self.assertEqual(bashrc.read_text(), "previous bash configuration\n")
        self.assertFalse((self.home / ".bashrc.local").exists())

        stowrc.unlink()
        retry = self.run_installer("install-bash.sh")
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertTrue(bashrc.is_symlink())
        self.assertEqual(bashrc.resolve(), ROOT / "bash/.bashrc")
        self.assertEqual((self.home / ".bashrc.local").read_text(), "previous bash configuration\n")
