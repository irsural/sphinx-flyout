"""
Расширение Sphinx, содержащее функциональность для интеграции информации о версиях документации
и создания flyout меню с этой информацией.
"""

import logging
from pathlib import Path
from typing import Any, Final, NamedTuple

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import ConfigError

DEFAULT_REF_WHITELIST: Final[list[str]] = ['master']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DATE_FMT: Final = '%Y-%m-%d %H:%M:%S %z'


class Version(NamedTuple):
    name: str
    url: str


def setup(app: Sphinx) -> None:
    app.add_config_value('fmv_flyout_host', '', 'html', str)
    app.add_config_value('fmv_flyout_repository', '', 'html', str)
    app.add_config_value('fmv_flyout_downloads', [], 'html', list)
    app.add_config_value('fmv_current_version', '', 'html')
    app.add_config_value('fmv_flyout_branch_list', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_flyout_tag_list', DEFAULT_REF_WHITELIST, 'html')

    app.connect('config-inited', _add_config_values)
    app.connect('html-page-context', html_page_context)


def html_page_context(
    app: Sphinx, pagename: str, templatename: str, context: dict[str, Any], doctree: None
) -> None:
    try:
        context['current_version'] = app.config.fmv_current_version
        host = _check_protocol(app.config['fmv_flyout_host'])
        context['branches'] = {
            name: host + '/branches/' + name for name in app.config.fmv_flyout_branch_list
        }
        context['tags'] = {
            name: host + '/branches/' + name for name in app.config.fmv_flyout_tag_list
        }
        context['header'] = app.config['fmv_flyout_header']
        context['downloads'] = {
            name: host + '/download/' + name for name in app.config['fmv_flyout_downloads']
        }
        context['repository_link'] = app.config['fmv_flyout_repository']
        theme = context['html_theme'] = app.config.html_theme
        if theme != 'sphinx_rtd_theme':
            logger.warning(
                "Тема %s не поддерживается. Пожалуйста, используйте 'sphinx_rtd_theme'",
                theme,
            )
            return
        logger.debug('Добавляется flyout в %s', pagename)

    except Exception as e:
        errormsg = f'Не удалось добавить flyout: {e}'
        raise ConfigError(errormsg) from e


def _check_protocol(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url


def _add_config_values(app: Sphinx, config: Config) -> None:
    _check_config_values(config)
    config.templates_path.insert(0, str(Path(__file__).parent / '_templates'))
    config.add('fmv_flyout_header', app.config.project, 'html', str)


def _check_config_values(config: Config) -> None:
    necessary_values = [
        'fmv_flyout_host',
    ]
    for value in necessary_values:
        if not config[value]:
            errormsg = f'Параметр {value} не найден в конфигурационном файле'
            raise ConfigError(errormsg)
