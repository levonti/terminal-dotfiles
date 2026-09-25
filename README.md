# Terminal dotfiles

Общая конфигурация Kitty, zsh, Starship и zoxide для macOS, Ubuntu 24.04 GNOME, Ubuntu 24.04 KDE Plasma и Debian 13 KDE Plasma. Цель — одинаковые prompt, цвета, шрифт и сочетания клавиш внутри терминала на разных устройствах.

## Состав

| Пакет Stow | Файл в домашнем каталоге | Назначение |
| --- | --- | --- |
| `zsh` | `~/.zshrc` | completion, zoxide, Starship и два необязательных локальных файла |
| `kitty` | `~/.config/kitty/kitty.conf` | внешний вид, вкладки, окна и сочетания `Command`/`Super` |
| `starship` | `~/.config/starship.toml` | общий prompt |

zoxide использует стандартные команды `z` и `zi`. База посещённых каталогов создаётся на каждом устройстве отдельно. Oh My Zsh, Powerlevel10k и autojump не нужны.

## Установка

1. Установите зависимости по инструкции для [macOS](docs/macos.md), [Ubuntu GNOME](docs/ubuntu-24.04-gnome.md), [Ubuntu KDE](docs/ubuntu-24.04-kde.md) или [Debian KDE](docs/debian-13-kde.md).
2. Клонируйте репозиторий в `~/work/github.com/levonti/terminal-dotfiles`.
3. Перед первой установкой сохраните существующие `~/.zshrc`, `~/.config/kitty/kitty.conf` и `~/.config/starship.toml`, если они есть. Stow сообщит о конфликте, пока эти пути заняты обычными файлами.
4. Из корня клона выполните:

   ```sh
   stow --no-folding --simulate --verbose --target="$HOME" zsh kitty starship
   stow --no-folding --target="$HOME" zsh kitty starship
   ```

`--no-folding` оставляет каталоги в `$HOME` обычными каталогами: рядом с общими ссылками можно хранить приватные файлы. [Руководство GNU Stow](https://www.gnu.org/software/stow/manual/stow.html).

Для получения обновлений выполните `git pull --ff-only` в клоне. Stow создаёт ссылки, поэтому повторять установку при изменении существующих файлов не нужно. Для новых файлов или пакетов выполните Stow ещё раз. Изменения публикуются обычным commit и push.

## Локальные переопределения

Общий `.zshrc` читает `~/.zshrc.local` перед инициализацией инструментов, затем `~/.zshrc.local.post` после основных настроек. Kitty в конце читает необязательный `~/.config/kitty/kitty.local.conf`. Для Starship возможна полная локальная замена через `STARSHIP_CONFIG`. Подробности: [локальные переопределения](docs/local-overrides.md).

Приватные файлы, историю shell, базу zoxide, ключи и токены не добавляйте в публичный репозиторий. Файлы в `examples/` содержат только безопасные образцы.

## Проверка совместимости

[Версии](docs/versions.md) фиксируют проверенную конфигурацию Mac и статус Linux. На GNOME и KDE глобальные сочетания `Super` могут перехватываться до Kitty; соответствующие настройки среды описаны в инструкциях по платформам. [Сочетания Kitty](docs/keybindings.md).
