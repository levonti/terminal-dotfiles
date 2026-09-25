# Debian 13 KDE Plasma

1. Установите базовые пакеты и плагины zsh:

   ```sh
   sudo apt update
   sudo apt install zsh stow zsh-autosuggestions zsh-syntax-highlighting
   ```

2. Установите Kitty 0.49.0, Starship 1.26.0 и zoxide 0.9.9 из подходящих выпусков: [Kitty](https://sw.kovidgoyal.net/kitty/binary/), [Starship](https://starship.rs/guide/#step-1-install-starship), [zoxide](https://github.com/ajeetdsouza/zoxide#installation). Сверьте версии командами `kitty --version`, `starship --version` и `zoxide --version`.
3. Установите `MesloLGS NF`. Клонируйте репозиторий и примените Stow по [README](../README.md#установка). Проверьте запуск через `zsh -l`.
4. В «Параметры системы → Комбинации клавиш» KDE Plasma проверьте сочетания из [таблицы](keybindings.md), прежде всего `Super+Left/Right`. При конфликте измените системное действие, чтобы Kitty получал нужные клавиши.

Личные PATH, алиасы и исключения для этого устройства храните в [локальных файлах](local-overrides.md).
