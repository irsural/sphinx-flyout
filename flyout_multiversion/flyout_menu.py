"""
Расширение Sphinx, содержащее функциональность для интеграции информации о версиях документации
и создания flyout меню с этой информацией.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, NamedTuple
from typing_extensions import Final
from urllib.parse import quote

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import ConfigError
from sphinx.locale import _
from sphinx.util import i18n

DEFAULT_REF_WHITELIST: Final[List[str]] = ['master']

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
    app.add_config_value('fmv_metadata', {}, 'html')
    app.add_config_value('fmv_metadata_path', '', 'html')
    # flyout_tag_list и flyout_branch_list - списки уже собранных веток и тегов
    # они не собираются, ссылки на них просто добавляются в flyout
    app.add_config_value('fmv_flyout_branch_list', [], 'html')
    app.add_config_value('fmv_flyout_tag_list', [], 'html')
    # tag_build_list и branch_build_list - списки собираемых веток и тегов
    app.add_config_value('fmv_branch_build_list', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_tag_build_list', [], 'html')

    # fmv_flyout_header добавляется в _add_config_values
    # чтобы указать app.config.project в качестве значения по умолчанию, т.к.
    # до события config-inited app.config.project = Python,
    # а setup происходит раньше чем config-inited
    app.connect('config-inited', _add_config_values)
    app.connect('html-page-context', html_page_context)


def html_page_context(
    app: Sphinx, pagename: str, templatename: str, context: Dict[str, Any], doctree: None
) -> None:
    _update_flyout_menu(app.config)
    try:
        theme = app.config.html_theme
        if theme != 'sphinx_rtd_theme':
            logger.warning(
                "Тема %s не поддерживается. Пожалуйста, используйте 'sphinx_rtd_theme'",
                theme,
            )
            return

        context['current_version'] = app.config.fmv_current_version
        host = _check_protocol(app.config.fmv_flyout_host)
        project_url = host + '/' + quote(app.config.project)
        context['branches'] = {
            name: f'{project_url}/branches/{name}' for name in app.config.fmv_flyout_branch_list
        }
        context['tags'] = {
            name: f'{project_url}/tags/{name}' for name in app.config.fmv_flyout_tag_list
        }
        context['header'] = app.config.fmv_flyout_header
        context['downloads'] = {
            name: f'{project_url}/download/{name}' for name in app.config.fmv_flyout_downloads
        }
        context['repository_link'] = app.config.fmv_flyout_repository
        logger.debug('Добавляется flyout в %s', pagename)

    except Exception as e:
        errormsg = f'Не удалось добавить flyout: {e}'
        raise ConfigError(errormsg) from e


def _update_flyout_menu(config: Config) -> None:
    for branch in config.fmv_branch_build_list:
        if branch not in config.fmv_flyout_branch_list:
            config.fmv_flyout_branch_list.append(branch)
    for tag in config.fmv_tag_build_list:
        if tag not in config.fmv_flyout_tag_list:
            config.fmv_flyout_tag_list.append(tag)
    return


def config_inited(app: Sphinx, config: Config) -> None:
    if not config['fmv_metadata']:
        if not config['fmv_metadata_path']:
            return

        with open(config['fmv_metadata_path']) as f:
            metadata = json.load(f)

        config['fmv_metadata'] = metadata

    if not config['fmv_current_version']:
        return

    try:
        data = app.config.fmv_metadata[config.fmv_current_version]
    except KeyError:
        return

    app.connect('html-page-context', html_page_context)

    # Restore config values
    old_config = Config.read(data['confdir'])
    old_config.pre_init_values()
    old_config.init_values()
    config['version'] = data['version']
    config['release'] = data['release']
    config['rst_prolog'] = data['rst_prolog']
    config['today'] = old_config.today
    if not config['today']:
        config['today'] = i18n.format_date(
            format=config.today_fmt or _('%b %d, %Y'),
            date=datetime.strptime(data['creatordate'], DATE_FMT),
            language=config.language,
        )


def _check_protocol(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url


def _add_config_values(app: Sphinx, config: Config) -> None:
    _check_config_values(config)
    config.templates_path.insert(0, str(Path(__file__).parent / '_templates'))
    config.add('fmv_flyout_header', app.config.project, 'html', str)


def _check_config_values(config: Config) -> None:
    required = [
        'fmv_flyout_host',
    ]
    for value in required:
        if not config[value]:
            errormsg = f'Параметр {value} не найден в конфигурационном файле'
            raise ConfigError(errormsg)
