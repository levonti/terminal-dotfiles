# Ubuntu 24.04 GNOME

Начните с полной [установки Linux с чистого устройства](linux-install.md): она включает Git, Stow, zsh, плагины, Kitty, Starship, zoxide, fzf, шрифт, ярлык приложения и смену shell. В шаге базовых пакетов выполните **блок Ubuntu** для `universe`, затем общий блок. Когда общее руководство направит вас в README, выполните там клонирование и Stow.

В настройках клавиатуры GNOME проверьте системные сочетания `Super+T`, `Super+N`, `Super+W`, `Super+Left/Right` и другие из [таблицы](keybindings.md). Если GNOME перехватывает нужное сочетание, измените системное действие, чтобы событие дошло до Kitty.

Для перехода по номерам вкладок в Kitty используйте `Ctrl+Shift+1…9`. Чтобы использовать `Super+1…9`, освободите эти сочетания в GNOME Shell и Ubuntu Dock. Следующие команды отключают соответствующие системные сочетания запуска и переключения приложений для текущего пользователя. [GNOME Shell](https://github.com/GNOME/gnome-shell/blob/46.0/data/org.gnome.shell.gschema.xml.in) · [Dash to Dock](https://github.com/micheleg/dash-to-dock/blob/master/schemas/org.gnome.shell.extensions.dash-to-dock.gschema.xml).

```sh
for number in 1 2 3 4 5 6 7 8 9; do
  gsettings set org.gnome.shell.keybindings "switch-to-application-$number" '[]'
  gsettings set org.gnome.shell.extensions.dash-to-dock "app-hotkey-$number" '[]'
done
```

Личные настройки храните в [локальных файлах](local-overrides.md), отдельно от публичного клона.
