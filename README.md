# Terminal dotfiles

**English** · [Русский](README.ru.md)

[Clean install](#install-on-a-clean-system) · [Ubuntu migration](#migrate-an-existing-ubuntu-2404-setup) · [Kitty network panel](#kitty-network-panel) · [Local overrides](#local-overrides)

Shared configuration for Kitty, Zsh, Bash, Starship, and zoxide on macOS, Ubuntu 24.04 with GNOME or KDE Plasma, and Debian 13 with KDE Plasma. The setup gives you the same prompt, colors, font, and terminal shortcuts across machines.

## What's included

| Stow package | Path in your home directory | Purpose |
| --- | --- | --- |
| `zsh` | `~/.zshrc`, `~/.config/terminal-dotfiles/ssh.zsh` | Completion, zoxide, Starship, SSH compatibility, and two optional local override files |
| `bash` | `~/.bashrc` | Starship, zoxide, and SSH compatibility in interactive Bash, with private settings in `~/.bashrc.local` |
| `kitty` | `~/.config/kitty/kitty.conf`, `~/.config/kitty/tab_bar.py` | Appearance, tabs, windows, and `Command`/`Super` shortcuts |
| `starship` | `~/.config/starship.toml` | Shared prompt |

zoxide provides `z` and `zi`. Install fzf for interactive selection with `zi`. Each machine keeps its own database of visited directories. You can use the setup without Oh My Zsh, Powerlevel10k, or autojump.

## Install on a clean system

Follow the guide for your platform to install Git, GNU Stow, Kitty, Starship, zoxide, fzf, the Zsh plugins, and the font. The linked platform guides and the rest of the project documentation are in Russian.

[macOS](docs/macos.md) · [Ubuntu GNOME](docs/ubuntu-24.04-gnome.md) · [Ubuntu KDE](docs/ubuntu-24.04-kde.md) · [Debian KDE](docs/debian-13-kde.md)

Run these commands on the same machine after installing the prerequisites.

```sh
mkdir -p "$HOME/work/github.com/levonti"
git clone https://github.com/levonti/terminal-dotfiles.git "$HOME/work/github.com/levonti/terminal-dotfiles"
cd "$HOME/work/github.com/levonti/terminal-dotfiles"
stow --no-folding --simulate --verbose --target="$HOME" zsh kitty starship &&
  stow --no-folding --target="$HOME" zsh kitty starship &&
  sh scripts/install-bash.sh
```

Stow creates five symlinks on a clean system, and the Bash installer adds a sixth. To migrate existing configuration files on Ubuntu 24.04, use the [migration instructions](#migrate-an-existing-ubuntu-2404-setup).

`--no-folding` keeps directories in `$HOME` as ordinary directories, so you can store private files alongside the managed symlinks. [GNU Stow manual](https://www.gnu.org/software/stow/manual/stow.html).

Start `zsh -l` and run `starship --version`, `zoxide --version`, `fzf --version`, `type z`, and `type zi`. Then start `bash` and check that the prompt shows the `bash` label and that `z` and `zi` are still available. Run `exit` to return to Zsh. Check the Kitty version as described in the platform guide. If Zsh is already installed and your default shell is different, follow the guide's shell change step and log in again.

### Update settings

In your clone, switch to `main` with `git switch main` if needed. With `main` tracking `origin/main`, run `git pull`. On Ubuntu, press `Ctrl+Shift+F5` in Kitty to reload the configuration.

Existing Stow symlinks pick up changes to linked files. Run Stow again when the repository adds files or packages.

## Migrate an existing Ubuntu 24.04 setup

If Stow is missing, install it with `sudo apt install stow`. Preview the plan from the root of the clone.

```sh
sh scripts/install.sh --check
```

The preview lists files to back up, links to create, and configs already linked. The installer stops when a target path holds a symlink to another location, a broken symlink, or a directory where a file is expected. It also stops when a parent directory is a symlink. For each path it will change, it checks write and search permissions on the nearest existing parent directory.

The installer targets `~/.zshrc` and `~/.config/kitty`. If `ZDOTDIR` or `KITTY_CONFIG_DIRECTORY` points elsewhere, or Kitty finds a different `kitty.conf` through `XDG_CONFIG_HOME`, the installer prints both paths and stops. Run it with the same environment as Zsh and Kitty. If you set `ZDOTDIR` only inside Zsh, export it before running the check. If you start Kitty with `--config`, compare that path with `~/.config/kitty/kitty.conf`. You can use `STARSHIP_CONFIG` as a local Starship override.

Apply the migration once the check passes.

```sh
sh scripts/install.sh --migrate
```

The installer reruns the checks and moves conflicting Zsh, Kitty, and Starship files into a new private `~/.terminal-dotfiles-backup.*` directory, preserving their relative paths. It also backs up a regular `~/.zshrc.zwc` file so Zsh loads the shared `.zshrc`. It then runs Stow in simulation mode, applies the plan, and verifies all five symlinks.

If a step fails, the installer removes the links created in that run and restores the originals, including `.zshrc.zwc`. If it cannot restore a file, it leaves the file in the backup and prints the backup path. Rerunning a successful migration preserves existing links and backups.

Compare the saved configs with the shared ones and merge the settings you want to keep into your local override files. To install Bash, run `sh scripts/install-bash.sh` separately. [Local overrides](#local-overrides).

## Bash on macOS and Linux

`scripts/install-bash.sh` installs the same Bash package on macOS, Ubuntu, and Debian. If a regular `~/.bashrc` exists, the installer moves it to `~/.bashrc.local` and creates a link to the shared config. The shared config sources the local file before initializing zoxide and Starship. If both a regular `~/.bashrc` and `~/.bashrc.local` exist, the installer stops. You can safely rerun it once the shared link is in place.

The first Stow pass runs in simulation mode, so its simulation warning is expected. The installer reports success after verifying the `~/.bashrc` link. If `.stowrc` enables simulation and the link is missing, the installer restores the original `.bashrc` and exits with an error.

Review `~/.bashrc.local` after migration and remove any duplicate Starship or zoxide initialization. Interactive non-login Bash reads `~/.bashrc`. If you start Bash with `--login`, arrange for your existing `~/.bash_profile` to source `~/.bashrc` when needed. [Bash startup files](https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files.html).

Bash uses the shared left prompt, including the shell label. Displaying Starship's `right_format` in Bash requires Ble.sh 0.4 or later. [Starship documentation](https://starship.rs/advanced-config/#enable-right-prompt).

## Local overrides

The shared `.zshrc` adds the standard user and Homebrew binary directories to `PATH`. It then sources `~/.zshrc.local` before initializing tools and `~/.zshrc.local.post` after the main settings. The shared `.bashrc` sources `~/.bashrc.local` before initializing zoxide and Starship. Kitty loads the optional `~/.config/kitty/kitty.local.conf` at the end of its config. Set `STARSHIP_CONFIG` to use a complete local Starship config. [Local overrides guide (Russian)](docs/local-overrides.md).

## Kubernetes in Zsh

Optional Kubie keeps Kubernetes contexts and namespaces separate across tabs and reads individual kubeconfigs from `~/.kube/configs/`. Select a context in each tab with `kubie ctx`. The menu shows short names in the form `<env>:<cluster>`.

Within a Kubie session, Starship shows the short cluster name and namespace before the current path and Git status. The `☸` icon is green for dev, yellow for test, and red for production. Production uses the red icon without an extra environment label. The indicator stays hidden in the initial shell. [Kubie setup and verification guide (Russian)](docs/kubie.md).

## Kitty tabs

The tab bar uses a flat layout with gaps, a high-contrast active tab, numbers, and compact titles. Use `Command/Super+1…9` to jump to a tab by number, `Command/Super+P` to open the tab list, and `Command/Super+Shift+T` to name the session. On Ubuntu, use `Ctrl+Shift+1…9` to jump to a tab and `Ctrl+Shift+Left/Right` to move between adjacent tabs. The numbered shortcuts override Kitty's pane shortcuts on Ubuntu. [Ubuntu GNOME (Russian)](docs/ubuntu-24.04-gnome.md) · [Ubuntu KDE (Russian)](docs/ubuntu-24.04-kde.md).

Tab titles retain the directory while a program runs (for example, `project htop`) and include the host and command reported by the server over SSH. Kubie tabs show a colored `DEV`, `TEST`, `PROD`, or `?ENV` badge before the cluster and namespace. Starship separates context from the input line and shows Git status counters. [Appearance and prompt options (Russian)](docs/appearance.md) · [Kitty tab settings (Russian)](docs/kitty-tabs.md).

### Kitty network panel

On Ubuntu 24.04, the panel shows local inbound and outbound traffic even with one tab. Install the latest stable Kitty from the official installer. The Ubuntu 24.04 `apt` package (Kitty 0.32.2) lacks the API the panel uses. If you already linked `kitty.conf` and `tab_bar.py` with Stow, updating the clone is enough to update those files. [Linux installation and desktop launcher (Russian)](docs/linux-install.md#3-zoxide-fzf-starship-и-kitty).

```sh
installer_file=$(mktemp) &&
  curl -fsSL https://sw.kovidgoyal.net/kitty/installer.sh -o "$installer_file" &&
  sh "$installer_file" launch=n &&
  rm -f "$installer_file" &&
  "$HOME/.local/kitty.app/bin/kitty" --version
```

Use `"$HOME/.local/kitty.app/bin/kitty"` to start the new version. In a wide Kitty window, look for `Linux`, `↓` and `↑` at the top right.

To enable the panel on this device, including with one tab, run the following command.

```sh
printf '%s\n' 'tab_bar_style custom' 'tab_bar_min_tabs 1' > "$HOME/.config/kitty/terminal-dotfiles-network.conf"
```

To disable it and show the regular tab bar from two tabs onward, run the following command.

```sh
printf '%s\n' 'tab_bar_style fade' 'tab_bar_min_tabs 2' > "$HOME/.config/kitty/terminal-dotfiles-network.conf"
```

Reload Kitty with `Ctrl+Shift+F5` on Linux or `Ctrl+Command+,` on macOS. These commands change only the dedicated override, which Kitty reads after `kitty.local.conf`. Remove it with `rm -f "$HOME/.config/kitty/terminal-dotfiles-network.conf"` to return to the other configuration files. [Network panel guide (Russian)](docs/network-panel.md).

## SSH from Kitty

In interactive Zsh and Bash, the regular `ssh` command uses `TERM=xterm-256color` for every host. On nested SSH connections, each hop inherits that terminal type unless an intermediate host overrides it. Kitty keeps its own local `TERM`. [SSH setup and verification guide (Russian)](docs/ssh.md).

Keep private configs, shell history, the zoxide database, keys, and tokens outside the public repository. The `examples/` directory contains safe sample files.

## Compatibility and testing

The version list records the verified macOS setup and the versions used in the clean-install guides. The target Linux distributions still need on-device validation. GNOME and KDE may capture global `Super` shortcuts before Kitty receives them. See the platform guides for the corresponding desktop settings. [Versions (Russian)](docs/versions.md) · [Kitty shortcuts (Russian)](docs/keybindings.md).
