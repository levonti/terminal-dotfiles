# Ubuntu 24.04 GNOME

1. Установите базовые пакеты и плагины zsh:

   ```sh
   sudo apt update
   sudo apt install zsh stow zsh-autosuggestions zsh-syntax-highlighting
   ```

2. Установите Kitty 0.49.0, Starship 1.26.0 и zoxide 0.9.9. Выберите соответствующие выпуски из [Kitty](https://sw.kovidgoyal.net/kitty/binary/), [Starship](https://starship.rs/guide/#step-1-install-starship) и [zoxide](https://github.com/ajeetdsouza/zoxide#installation). Дистрибутивные пакеты могут иметь другие версии; сверяйте `kitty --version`, `starship --version` и `zoxide --version`.
3. Установите шрифт `MesloLGS NF`, используемый в общем `kitty.conf`.
4. Клонируйте репозиторий и установите ссылки по [README](../README.md#установка). Сначала проверьте shell командой `zsh -l`; менять shell по умолчанию можно после проверки.
5. В настройках клавиатуры GNOME проверьте системные сочетания `Super+T`, `Super+N`, `Super+W`, `Super+Left/Right` и другие из [таблицы](keybindings.md). Если GNOME перехватывает нужное сочетание, измените системное действие, чтобы событие дошло до Kitty.

Личные настройки храните в [локальных файлах](local-overrides.md), отдельно от публичного клона.
