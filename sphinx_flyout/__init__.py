import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import ConfigError
from sphinx.util import logging

logger = logging.getLogger(__name__)


def setup(app: Sphinx) -> None:
    app.add_config_value('sphinx_flyout_git_reference', _get_git_branch(app), 'html')
    app.add_config_value('sphinx_flyout_host', '', 'html', str)
    app.add_config_value('sphinx_flyout_repository_link', '', 'html', str)
    app.add_config_value('sphinx_flyout_tags', [], 'html', list)
    app.add_config_value('sphinx_flyout_branches', [], 'html', list)
    app.add_config_value('sphinx_flyout_downloads', [], 'html', list)
    app.connect('config-inited', _check_config_values)
    app.connect('config-inited', _add_config_values)
    app.connect('html-page-context', add_flyout_to_context)


def _check_config_values(app: Sphinx, config: Config) -> None:
    if not config.sphinx_flyout_host:
        errormsg = 'Обязательный параметр sphinx_flyout_host не установлен'
        raise ConfigError(errormsg)


def _add_config_values(app: Sphinx, config: Config) -> None:
    config.templates_path.append(str(Path(__file__).parent / '_templates'))
    config.add('sphinx_flyout_header', app.config.project, 'html', str)


def _get_git_branch(app: Sphinx) -> str:
    process = subprocess.run(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, cwd=app.srcdir
    )
    if process.returncode == 0:
        return process.stdout.decode().strip()
    else:
        logger.warning(
            'Не удалось получить имя текущей ветки git: %s', process.stderr.decode('utf-8')
        )
        return ''


def add_flyout_to_context(
    app: Sphinx, pagename: str, templatename: str, context: dict[str, Any], doctree: Any
) -> None:
    try:
        if app.config.html_theme != 'sphinx_rtd_theme':
            logger.warning(
                "Тема %s не поддерживается. Пожалуйста, используйте 'sphinx_rtd_theme'",
                app.config.html_theme,
            )
            return
        logger.info('Writing flyout to %s', pagename)
        context['current_version'] = app.config.sphinx_flyout_git_reference
        host = app.config.sphinx_flyout_host
        if not host.startswith(('http://', 'https://')):
            host = 'https://' + host
        project_url = urllib.parse.quote(app.config.sphinx_flyout_header)
        context['header'] = app.config.sphinx_flyout_header
        context['downloads'] = _make_links_relate_to_host(
            host, project_url, 'download', app.config.sphinx_flyout_downloads
        )
        if app.config.sphinx_flyout_repository_link:
            context['repository_link'] = app.config.sphinx_flyout_repository_link
        context['tags'] = _make_links_relate_to_host(
            host,
            project_url,
            'tag',
            app.config.sphinx_flyout_tags,
        )
        context['branches'] = _make_links_relate_to_host(
            host,
            project_url,
            'branch',
            app.config.sphinx_flyout_branches,
        )
    except Exception as e:
        errormsg = 'Не удалось добавить flyout'
        raise ConfigError(errormsg) from e


def _make_links_relate_to_host(
    host: str, project: str, section: str, links: list[str]
) -> dict[str, str]:
    new_links = {}
    for link in links:
        new_links[link] = f'{host}/{project}/{section}/{link}'
    return new_links
