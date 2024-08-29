# sphinx-flyout

**sphinx-flyout** - это расширение [Sphinx](https://www.sphinx-doc.org/en/master/)
для автоматической генерации [flyout-меню](https://docs.readthedocs.io/en/stable/flyout-menu.html)

## Использование

### Установка

```bash
pip install git+https://github.com/irsural/sphinx-flyout@master
```

Расширение добавляется в файл конфигурации sphinx (**conf.py**), так же как и другие расширения sphinx:

```python
extensions = [
    ...,
    'sphinx_flyout',
    ...
]
```

### Настройка

У расширения есть 7 параметров, задаваемых переменными в **conf.py**.

#### `sphinx_flyout_header`

Заголовок меню. По умолчанию - название проекта **Sphinx**

#### `sphinx_flyout_git_reference`

Название версии git-репозитория. По умолчанию - текущая ветка

#### `sphinx_flyout_repository_link`

Строка со ссылкой на репозиторий проекта. По умолчанию пустая,
а раздел **Репозиторий** не отображается

#### `sphinx_flyout_host`

Ссылка на хостинг сайта. Автоматически вставляется в нижеупомянутые ссылки.
Обязательный параметр

#### `sphinx_flyout_downloads`

Список с форматами документации проекта, доступными для загрузки
(`html`, `pdf` и т.д.) .

Во время работы расширения ссылки автоматически преобразуются в следующий формат:

`html: sphinx_flyout_host / sphinx_flyout_header / download / html`

По умолчанию пуст, а раздел **Загрузки** не отображается

#### `sphinx_flyout_branches`

Список с названиями собранных веток проекта.

Во время работы расширения ссылки автоматически преобразуются в следующий формат:

`ветка1: sphinx_flyout_host / sphinx_flyout_header / branch / ветка1`

По умолчанию пуст, а раздел **Ветки** не отображается

#### `sphinx_flyout_tags`

Список с названиями собранных тэгов проекта.

Во время работы расширения ссылки автоматически преобразуются в следующий формат:

`тэг1: sphinx_flyout_host / sphinx_flyout_header / tag / тэг1`

По умолчанию пуст, а раздел **Тэги** не отображается

## Пример

Содержимое **conf.py**:

```python
sphinx_flyout_header = "My project"
sphinx_flyout_repository_link = "https://gitea.example.com/my/project"

sphinx_flyout_host = "https://example.com"
sphinx_flyout_downloads = ["html", "pdf"]

sphinx_flyout_tags = ["t2", "release"]
sphinx_flyout_branches = ["b1", "master"]
```

Вид сгенерированного меню:

![flyout](docs/images/menu.png)

Ссылки **Ветки** ведут на `https://example.com/My%20project/branch/b1` и `https://example.com/My%20project/branch/master`

Ссылки **Тэги** ведут на `https://example.com/My%20project/tag/t2` и `https://example.com/My%20project/tag/release`

Ссылки **Загрузки** ведут на `https://example.com/My%20project/download/html` и `https://example.com/My%20project/download/pdf`

Ссылка **Посмотреть** ведёт на `https://gitea.example.com/my/project`
