# Linux: установка с чистого устройства

Эти команды общие для Ubuntu 24.04 GNOME, Ubuntu 24.04 KDE Plasma и Debian 13 KDE Plasma на `amd64` или `arm64`. Выполняйте их в существующем терминале под обычным пользователем с доступом к `sudo`. После установки вернитесь к странице своей графической среды.

## 1. Базовые пакеты

На **Ubuntu 24.04** сначала включите `universe`, где находятся плагины zsh. На Debian 13 этот блок пропустите.

```sh
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository -y universe
```

На **Ubuntu и Debian** установите базовые инструменты:

```sh
sudo apt update
sudo apt install git curl ca-certificates zsh stow zsh-autosuggestions zsh-syntax-highlighting fontconfig
```

## 2. Шрифт MesloLGS NF

Скачайте четыре начертания одной зафиксированной версии шрифта. Shell-фреймворк Powerlevel10k для этого не нужен. [Источник файлов](https://github.com/romkatv/powerlevel10k-media/tree/145eb9fbc2f42ee408dacd9b22d8e6e0e553f83d).

```sh
font_base=https://raw.githubusercontent.com/romkatv/powerlevel10k-media/145eb9fbc2f42ee408dacd9b22d8e6e0e553f83d
mkdir -p "$HOME/.local/share/fonts"
curl -fL "$font_base/MesloLGS%20NF%20Regular.ttf" -o "$HOME/.local/share/fonts/MesloLGS NF Regular.ttf"
curl -fL "$font_base/MesloLGS%20NF%20Bold.ttf" -o "$HOME/.local/share/fonts/MesloLGS NF Bold.ttf"
curl -fL "$font_base/MesloLGS%20NF%20Italic.ttf" -o "$HOME/.local/share/fonts/MesloLGS NF Italic.ttf"
curl -fL "$font_base/MesloLGS%20NF%20Bold%20Italic.ttf" -o "$HOME/.local/share/fonts/MesloLGS NF Bold Italic.ttf"
fc-cache -f "$HOME/.local/share/fonts"
fc-match -f '%{family}\n' 'MesloLGS NF'
```

Последняя команда должна назвать `MesloLGS NF` первым подходящим семейством.

## 3. zoxide, fzf, Starship и Kitty

Установите zoxide 0.9.9 из официального `.deb`, fzf 0.71.0 из официального архива и Starship 1.26.0 в `~/.local/bin`. Пакет fzf в Ubuntu 24.04 имеет версию 0.44, а zoxide требует для `zi` как минимум 0.51; поэтому `apt install fzf` здесь не используется. [zoxide](https://github.com/ajeetdsouza/zoxide/releases/tag/v0.9.9), [fzf](https://github.com/junegunn/fzf/releases/tag/v0.71.0), [документация zoxide](https://github.com/ajeetdsouza/zoxide#installation).

```sh
arch=$(dpkg --print-architecture)
mkdir -p "$HOME/.local/bin" "$HOME/.cache/terminal-dotfiles/downloads"
download_dir="$HOME/.cache/terminal-dotfiles/downloads"
curl -fL "https://github.com/ajeetdsouza/zoxide/releases/download/v0.9.9/zoxide_0.9.9-1_${arch}.deb" -o "$download_dir/zoxide.deb"
sudo dpkg -i "$download_dir/zoxide.deb"
curl -fL "https://github.com/junegunn/fzf/releases/download/v0.71.0/fzf-0.71.0-linux_${arch}.tar.gz" -o "$download_dir/fzf.tar.gz"
tar -xzf "$download_dir/fzf.tar.gz" -C "$HOME/.local/bin" fzf
curl -fsSL https://starship.rs/install.sh | sh -s -- --version v1.26.0 --bin-dir "$HOME/.local/bin" --yes
curl -fL https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin installer=version-0.49.0 launch=n
```

Установщик Kitty кладёт приложение в `~/.local/kitty.app`. Создайте ярлык с **абсолютными** путями к программе и значку: такой ярлык работает и тогда, когда графическая среда не добавляет `~/.local/bin` в `PATH`. [Инструкция Kitty](https://sw.kovidgoyal.net/kitty/binary/).

```sh
mkdir -p "$HOME/.local/share/applications"
ln -s "$HOME/.local/kitty.app/bin/kitty" "$HOME/.local/bin/kitty"
ln -s "$HOME/.local/kitty.app/bin/kitten" "$HOME/.local/bin/kitten"
cp "$HOME/.local/kitty.app/share/applications/kitty.desktop" "$HOME/.local/share/applications/kitty.desktop"
sed -i "s|Icon=kitty|Icon=$HOME/.local/kitty.app/share/icons/hicolor/256x256/apps/kitty.png|g" "$HOME/.local/share/applications/kitty.desktop"
sed -i "s|Exec=kitty|Exec=$HOME/.local/kitty.app/bin/kitty|g" "$HOME/.local/share/applications/kitty.desktop"
```

## 4. Проверка и конфиги

```sh
"$HOME/.local/kitty.app/bin/kitty" --version
"$HOME/.local/bin/starship" --version
zoxide --version
"$HOME/.local/bin/fzf" --version
stow --version
```

Клонируйте репозиторий и установите ссылки по [README](../README.md#установка-с-чистого-устройства). Затем смените shell по умолчанию и войдите в графическую сессию заново:

```sh
chsh -s "$(command -v zsh)"
```

После нового входа откройте Kitty из меню приложений, выполните `echo "$SHELL"`, `type z`, `type zi` и проверьте prompt. Если на устройстве нет `sudo`, выполняйте привилегированные команды от root по правилам этой системы.
