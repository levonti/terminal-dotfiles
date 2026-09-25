# Terminal dotfiles

Общая конфигурация Kitty, zsh, Starship и zoxide для macOS, Ubuntu 24.04 GNOME, Ubuntu 24.04 KDE Plasma и Debian 13 KDE Plasma. Цель — одинаковые prompt, цвета, шрифт и сочетания клавиш внутри терминала на разных устройствах.

## Состав

| Пакет Stow | Файл в домашнем каталоге | Назначение |
| --- | --- | --- |
| `zsh` | `~/.zshrc`, `~/.config/terminal-dotfiles/ssh.zsh` | completion, zoxide, Starship, маршрутизация SSH и два необязательных локальных файла |
| `kitty` | `~/.config/kitty/kitty.conf` | внешний вид, вкладки, окна и сочетания `Command`/`Super` |
| `starship` | `~/.config/starship.toml` | общий prompt |

zoxide использует стандартные команды `z` и `zi`; для интерактивной команды `zi` устанавливается fzf. База посещённых каталогов создаётся на каждом устройстве отдельно. Oh My Zsh, Powerlevel10k и autojump не нужны.

## Установка с чистого устройства

Сначала выполните инструкцию для [macOS](docs/macos.md), [Ubuntu GNOME](docs/ubuntu-24.04-gnome.md), [Ubuntu KDE](docs/ubuntu-24.04-kde.md) или [Debian KDE](docs/debian-13-kde.md). Она устанавливает Git, Stow, Kitty, Starship, zoxide, fzf, плагины zsh и шрифт. Затем на том же устройстве выполните:

```sh
mkdir -p "$HOME/work/github.com/levonti"
git clone https://github.com/levonti/terminal-dotfiles.git "$HOME/work/github.com/levonti/terminal-dotfiles"
cd "$HOME/work/github.com/levonti/terminal-dotfiles"
stow --no-folding --simulate --verbose --target="$HOME" zsh kitty starship
stow --no-folding --target="$HOME" zsh kitty starship
```

На действительно чистом устройстве Stow создаст три ссылки. Если один из путей уже занят обычным файлом, сохраните его отдельно и повторите Stow; он не перезаписывает такой файл молча. Личные `~/.zshrc.local`, `~/.zshrc.local.post` и `~/.config/kitty/kitty.local.conf` оставьте на месте.

`--no-folding` оставляет каталоги в `$HOME` обычными каталогами: рядом с общими ссылками можно хранить приватные файлы. [Руководство GNU Stow](https://www.gnu.org/software/stow/manual/stow.html).

После установки запустите `zsh -l` и проверьте `starship --version`, `zoxide --version`, `fzf --version`, `type z` и `type zi`. Проверьте версию Kitty по платформенной инструкции. Если shell по умолчанию ещё не zsh, выполните шаг смены shell в инструкции платформы и войдите в систему заново.

Для получения обновлений выполните `git pull --ff-only` в клоне. Stow создаёт ссылки, поэтому повторять установку при изменении существующих файлов не нужно. Для новых файлов или пакетов выполните Stow ещё раз. Изменения публикуются обычным commit и push.

## Локальные переопределения

Общий `.zshrc` сначала добавляет стандартные каталоги пользовательских бинарников и Homebrew в `PATH`, затем читает `~/.zshrc.local` перед инициализацией инструментов и `~/.zshrc.local.post` после основных настроек. Kitty в конце читает необязательный `~/.config/kitty/kitty.local.conf`. Для Starship возможна полная локальная замена через `STARSHIP_CONFIG`. Подробности: [локальные переопределения](docs/local-overrides.md).

## SSH из Kitty

Интерактивная команда `ssh` из Kitty использует совместимый `TERM=xterm-256color` для неизвестных хостов. Полный режим `kitten ssh` включается только для явно перечисленных в приватном списке управляемых назначений. Список по умолчанию пуст. Правила добавления хоста, границы изменений на сервере и проверка описаны в [руководстве по SSH](docs/ssh.md).

Приватные файлы, историю shell, базу zoxide, ключи и токены не добавляйте в публичный репозиторий. Файлы в `examples/` содержат только безопасные образцы.

## Проверка совместимости

[Версии](docs/versions.md) фиксируют проверенную конфигурацию Mac и версии, используемые инструкцией чистой установки. Linux пока не проверялся на самих целевых устройствах. На GNOME и KDE глобальные сочетания `Super` могут перехватываться до Kitty; соответствующие настройки среды описаны в инструкциях по платформам. [Сочетания Kitty](docs/keybindings.md).
