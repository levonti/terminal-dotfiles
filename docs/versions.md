# Версии компонентов

На исходном Mac при подготовке репозитория были проверены:

| Компонент | Версия |
| --- | --- |
| Kitty | 0.49.0 |
| Starship | 1.26.0 |
| zoxide | 0.9.9 |
| fzf | 0.71.0 |
| zsh | 5.9 |
| Bash | 5.3.9 |
| zsh-autosuggestions | 0.7.1 |
| zsh-syntax-highlighting | 0.8.0 |

Инструкции чистой установки закрепляют версии Kitty, Starship, zoxide, fzf и [четыре файла шрифта](https://github.com/romkatv/powerlevel10k-media/tree/145eb9fbc2f42ee408dacd9b22d8e6e0e553f83d). Плагины zsh устанавливаются из Homebrew или системного APT и могут иметь другие версии. Шрифт в общем `kitty.conf` — `MesloLGS NF`, размер 15 pt.

Ubuntu 24.04 GNOME, Ubuntu 24.04 KDE Plasma и Debian 13 KDE Plasma пока не проверялись на самих целевых устройствах. Их инструкции рассчитаны на `amd64` и `arm64`.
