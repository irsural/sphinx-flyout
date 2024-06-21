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

DEFAULT_REF_WHITELIST: list[str] = ['master']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DATE_FMT: Final = '%Y-%m-%d %H:%M:%S %z'


def setup(app: Sphinx) -> None:
    app.add_config_value('fmv_flyout_host', '', 'html', str)
    app.add_config_value('fmv_flyout_repository', '', 'html', str)
    app.add_config_value('fmv_flyout_downloads', [], 'html', list)
    app.add_config_value('fmv_metadata', {}, 'html')
    app.add_config_value('fmv_metadata_path', '', 'html')
    app.add_config_value('fmv_current_version', '', 'html')
    app.add_config_value('fmv_latest_version', 'master', 'html')
    app.add_config_value('fmv_flyout_branch_list', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_flyout_tag_list', DEFAULT_REF_WHITELIST, 'html')

    app.connect('config-inited', _add_config_values)
    app.connect('html-page-context', html_page_context)


class Version(NamedTuple):
    name: str
    url: str
    version: str
    release: str


class VersionInfo:
    def __init__(
        self,
        app: Sphinx,
        context: dict[str, Any],
        metadata: dict[str, dict[str, str]],
        current_version_name: str,
    ) -> None:
        self.app = app
        self.context = context
        self.metadata = metadata
        self.current_version_name = current_version_name

    def _dict_to_versionobj(self, v: dict[str, str]) -> Version:
        return Version(
            name=v['name'],
            url=_check_protocol(self.app.config['fmv_flyout_host']) + f'/{v["source"]}/{v["name"]}',
            version=v['version'],
            release=v['release'],
        )

    @property
    def tags(self) -> list[Version]:
        return [
            self._dict_to_versionobj(v) for v in self.metadata.values() if v['source'] == 'tags'
        ]

    @property
    def branches(self) -> list[Version]:
        return [
            self._dict_to_versionobj(v) for v in self.metadata.values() if v['source'] != 'tags'
        ]

    def __getitem__(self, name: str) -> Version | None:
        v = self.metadata.get(name)
        if v:
            return self._dict_to_versionobj(v)
        return None


def html_page_context(
    app: Sphinx, pagename: str, templatename: str, context: dict[str, Any], doctree: None
) -> None:
    versioninfo = VersionInfo(app, context, app.config.fmv_metadata, app.config.fmv_current_version)
    _update_flyout_menu(app.config, versioninfo)
    try:
        context['current_version'] = versioninfo[app.config.fmv_current_version]
        context['versions'] = versioninfo
        host = context['host'] = _check_protocol(app.config['fmv_flyout_host'])
        context['header'] = app.config['fmv_flyout_header']
        context['downloads'] = {
            name: host + '/download/' + name for name in app.config['fmv_flyout_downloads']
        }
        context['repository_link'] = app.config['fmv_flyout_repository']
        context['latest_version'] = versioninfo[app.config.fmv_latest_version]
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


def _update_flyout_menu(config: Config, versioninfo: VersionInfo) -> None:
    for branch in config.fmv_flyout_branch_list:
        if branch not in versioninfo.metadata:
            versioninfo.metadata[branch] = {
                'name': branch,
                'source': 'heads',
                'version': '',
                'release': '',
            }
    for tag in config.fmv_flyout_tag_list:
        if tag not in versioninfo.metadata:
            versioninfo.metadata[tag] = {
                'name': tag,
                'source': 'tags',
                'version': '',
                'release': '',
            }


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
