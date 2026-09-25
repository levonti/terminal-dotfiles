# macOS: установка с чистого устройства

Команды рассчитаны на Mac с Apple Silicon или Intel. Откройте стандартный Terminal.app и выполняйте шаги по порядку. Системный `/bin/zsh` уже входит в macOS; Oh My Zsh и Powerlevel10k устанавливать не требуется.

## 1. Homebrew, Git, Stow и плагины zsh

Если Homebrew отсутствует, установите его официальным способом. Установщик может предложить Command Line Tools и пароль администратора. [Документация Homebrew](https://brew.sh/).

```sh
if [ ! -x /opt/homebrew/bin/brew ] && [ ! -x /usr/local/bin/brew ]; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  eval "$(/usr/local/bin/brew shellenv)"
fi
brew install git stow zsh-autosuggestions zsh-syntax-highlighting
```

## 2. Шрифт MesloLGS NF

Скачайте четыре начертания одной зафиксированной версии шрифта в `~/Library/Fonts`. Это только шрифт: shell-фреймворк Powerlevel10k не устанавливается. [Источник файлов](https://github.com/romkatv/powerlevel10k-media/tree/145eb9fbc2f42ee408dacd9b22d8e6e0e553f83d).

```sh
font_base=https://raw.githubusercontent.com/romkatv/powerlevel10k-media/145eb9fbc2f42ee408dacd9b22d8e6e0e553f83d
mkdir -p "$HOME/Library/Fonts"
curl -fL "$font_base/MesloLGS%20NF%20Regular.ttf" -o "$HOME/Library/Fonts/MesloLGS NF Regular.ttf"
curl -fL "$font_base/MesloLGS%20NF%20Bold.ttf" -o "$HOME/Library/Fonts/MesloLGS NF Bold.ttf"
curl -fL "$font_base/MesloLGS%20NF%20Italic.ttf" -o "$HOME/Library/Fonts/MesloLGS NF Italic.ttf"
curl -fL "$font_base/MesloLGS%20NF%20Bold%20Italic.ttf" -o "$HOME/Library/Fonts/MesloLGS NF Bold Italic.ttf"
```

## 3. zoxide, fzf, Starship и Kitty

Первые два инструмента берутся из зафиксированных официальных выпусков. fzf нужен для `zi`. Общий `.zshrc` добавляет `~/.local/bin` в `PATH` до инициализации инструментов. [zoxide](https://github.com/ajeetdsouza/zoxide/releases/tag/v0.9.9), [fzf](https://github.com/junegunn/fzf/releases/tag/v0.71.0).

```sh
case "$(uname -m)" in
  arm64) zoxide_target=aarch64-apple-darwin; fzf_arch=arm64 ;;
  x86_64) zoxide_target=x86_64-apple-darwin; fzf_arch=amd64 ;;
esac
mkdir -p "$HOME/.local/bin" "$HOME/.cache/terminal-dotfiles/downloads"
download_dir="$HOME/.cache/terminal-dotfiles/downloads"
curl -fL "https://github.com/ajeetdsouza/zoxide/releases/download/v0.9.9/zoxide-0.9.9-${zoxide_target}.tar.gz" -o "$download_dir/zoxide.tar.gz"
tar -xzf "$download_dir/zoxide.tar.gz" -C "$HOME/.local/bin" zoxide
curl -fL "https://github.com/junegunn/fzf/releases/download/v0.71.0/fzf-0.71.0-darwin_${fzf_arch}.tar.gz" -o "$download_dir/fzf.tar.gz"
tar -xzf "$download_dir/fzf.tar.gz" -C "$HOME/.local/bin" fzf
curl -fsSL https://starship.rs/install.sh | sh -s -- --version v1.26.0 --bin-dir "$HOME/.local/bin" --yes
curl -fL https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin installer=version-0.49.0 launch=n
```

Starship и Kitty используют параметры версии из своих официальных установщиков: [Starship](https://raw.githubusercontent.com/starship/starship/master/install/install.sh), [Kitty](https://sw.kovidgoyal.net/kitty/binary/).

## 4. Проверка и конфиги

```sh
/Applications/kitty.app/Contents/MacOS/kitty --version
"$HOME/.local/bin/starship" --version
"$HOME/.local/bin/zoxide" --version
"$HOME/.local/bin/fzf" --version
stow --version
```

Затем клонируйте репозиторий и установите ссылки по [README](../README.md#установка-с-чистого-устройства). Если текущий shell не `/bin/zsh`, выполните `chsh -s /bin/zsh` и войдите в macOS заново. Откройте Kitty из Applications, проверьте prompt, `z` и `zi`.

Если на Mac уже есть конфиги, сохраните обычные файлы `~/.zshrc`, `~/.config/kitty/kitty.conf` и `~/.config/starship.toml` перед Stow. Личный `~/.zshrc.local` оставьте на месте.
