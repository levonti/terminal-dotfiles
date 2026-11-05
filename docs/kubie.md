# Kubie в zsh

Kubie устанавливается отдельно на рабочих станциях с Kubernetes. Интерактивный zsh находит бинарник в Homebrew или `~/.local/bin` через общий `PATH`. При наличии `KUBIE_ACTIVE` Starship показывает контекст в первой строке prompt. Namespace появляется рядом, когда он задан во временном kubeconfig сессии. [Руководство Kubie](https://github.com/kubie-org/kubie#usage), [модуль Kubernetes в Starship](https://starship.rs/config/#kubernetes).

## Установка

На macOS с Homebrew выполните `brew install kubie`. Формула устанавливает completion, который общий zsh подхватывает через `compinit`. На Linux скачайте `kubie-linux-amd64` для `x86_64` или `kubie-linux-arm64` для `aarch64` из [релиза v0.28.0](https://github.com/kubie-org/kubie/releases/expanded_assets/v0.28.0), сравните вывод `sha256sum` с SHA-256 на странице релиза и установите проверенный файл как `~/.local/bin/kubie` с правами `0755`. Проверьте `kubie --version` в новой вкладке zsh. [Формула Homebrew](https://formulae.brew.sh/formula/kubie).

Из корня репозитория скопируйте образец, если локального файла ещё нет.

```sh
mkdir -p "$HOME/.kube"
(umask 077; cp -n examples/kubie.yaml.example "$HOME/.kube/kubie.yaml")
```

Если файл уже есть, перенесите в него `prompt.disable: true`, сохранив остальные локальные настройки. Этот параметр передаёт отображение контекста Starship. В образце Kubie ищет контексты в `~/.kube/config`. Если kubeconfig лежат отдельно, добавьте их пути в `configs.include` в локальном файле. Храните kubeconfig и список приватных путей вне репозитория. [Настройки Kubie](https://github.com/kubie-org/kubie#settings).

При использовании собственного `STARSHIP_CONFIG` перенесите в него блок `[kubernetes]` из общего TOML и добавьте `$kubernetes` в его `format`. При установке из отдельного бинарника можно подключить completion в `~/.zshrc.local.post` строкой `(( $+commands[kubie] )) && source <(kubie generate-completion zsh)`. [Локальные переопределения](local-overrides.md), [completion Kubie](https://github.com/kubie-org/kubie#autocompletion).

## Проверка в двух вкладках Kitty

1. В обеих вкладках запомните вывод `kubectl config current-context` и состояние переменной `KUBECONFIG` командой `print -r -- "${KUBECONFIG-<unset>}"`. Команда `kubectl config current-context` читает локальный файл.
2. В каждой вкладке выполните `kubie ctx` и выберите разные контексты. Сверьте prompt с `kubie info ctx`. Чтобы проверить namespace, задайте его через `kubie ctx ИМЯ_КОНТЕКСТА -n ИМЯ_NAMESPACE` или выберите через `kubie ns`. Эти команды по умолчанию обращаются к API выбранного кластера за списком namespace. Сверьте имя в prompt с `kubie info ns`.
3. Выполните `exit` в первой вкладке. Проверьте, что исходные контекст и `KUBECONFIG` вернулись, а индикатор исчез. Во второй вкладке должен остаться её собственный контекст. Затем выйдите и во второй вкладке.
