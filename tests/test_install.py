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

    def test_failed_stow_rolls_back_only_this_run(self):
        self.write_originals()
        existing = self.home / ".config/kitty/tab_bar.py"
        source = ROOT / MANAGED[".config/kitty/tab_bar.py"]
        existing.symlink_to(source)
        bin_dir = self.work / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "stow"
        wrapper.write_text(
            f"#!/bin/sh\n{shlex.quote(STOW)} \"$@\" || exit $?\n"
            'if [ "$1" != --simulate ]; then exit 42; fi\n'
        )
        wrapper.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env['PATH']}"

        install = self.run_installer("install.sh", "--migrate")
        self.assertEqual(install.returncode, 42, install.stderr)
        self.assertNotIn("configuration installed", install.stdout)
        for relative, contents in ORIGINALS.items():
            path = self.home / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_text(), contents)
        self.assertEqual(existing.readlink(), source)
        self.assertFalse((self.home / ".config/terminal-dotfiles").exists())
        self.assertFalse((self.home / ".terminal-dotfiles-install.lock").exists())
        self.assertFalse(self.backups())

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
