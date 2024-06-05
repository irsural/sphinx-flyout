import collections
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Iterator

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import ConfigError
from sphinx.locale import _
from sphinx.util import i18n as sphinx_i18n

DEFAULT_REF_WHITELIST: list[str] = ['master']
DEFAULT_REMOTE_WHITELIST: list[str] = ['release']
DEFAULT_RELEASED_PATTERN = ''


logger = logging.getLogger(__name__)

DATE_FMT = '%Y-%m-%d %H:%M:%S %z'
Version = collections.namedtuple(
    'Version',
    [
        'name',
        'url',
        'version',
        'release',
    ],
)


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

    @property
    def releases(self) -> list[Version]:
        return [self._dict_to_versionobj(v) for v in self.metadata.values() if v['is_released']]

    @property
    def in_development(self) -> list[Version]:
        return [self._dict_to_versionobj(v) for v in self.metadata.values() if not v['is_released']]

    def __iter__(self) -> Iterator[Version]:
        for item in self.tags:
            yield item
        for item in self.branches:
            yield item

    def __getitem__(self, name: str) -> Version | None:
        v = self.metadata.get(name)
        if v:
            return self._dict_to_versionobj(v)
        return None

    def vhasdoc(self, other_version_name: str) -> bool:
        if self.current_version_name == other_version_name:
            return True

        other_version = self.metadata[other_version_name]
        return self.context['pagename'] in other_version['docnames']


def html_page_context(
    app: Sphinx, pagename: str, templatename: str, context: dict[str, Any], doctree: str
) -> None:
    versioninfo = VersionInfo(app, context, app.config.fmv_metadata, app.config.fmv_current_version)
    _update_flyout_menu(app.config, versioninfo)
    try:
        context['current_version'] = versioninfo[app.config.fmv_current_version]
        context['versions'] = versioninfo
        context['vhasdoc'] = versioninfo.vhasdoc
        host = _check_protocol(app.config['fmv_flyout_host'])
        context['header'] = app.config['fmv_flyout_header']
        context['downloads'] = {
            name: host + '/download/' + name for name in app.config['fmv_flyout_downloads']
        }
        context['repository_link'] = app.config['fmv_flyout_repository']
        context['latest_version'] = versioninfo[app.config.fmv_latest_version]
        context['html_theme'] = app.config.html_theme
        if app.config.html_theme != 'sphinx_rtd_theme':
            logger.warning(
                'Тема %s не поддерживается. Пожалуйста, ' "используйте 'sphinx_rtd_theme'",
                app.config.html_theme,
            )
            return
        logger.info('Writing flyout to %s', pagename)

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
        data = app.config['fmv_metadata'][config['fmv_current_version']]
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
        config['today'] = sphinx_i18n.format_date(
            format=config.today_fmt or _('%b %d, %Y'),
            date=datetime.datetime.strptime(data['creatordate'], DATE_FMT),
            language=config.language,
        )


def _add_config_values(app: Sphinx, config: Config) -> None:
    _check_config_values(config)
    config.templates_path.append(str(Path(__file__).parent / '_templates'))
    config.add('fmv_flyout_header', app.config.project, 'html', str)


def _check_config_values(config: Config) -> None:
    necessary_values = [
        'fmv_flyout_host',
    ]
    for value in necessary_values:
        if not config[value]:
            errormsg = f'Параметр {value} не найден в конфигурационном файле'
            raise ConfigError(errormsg)


def setup(app: Sphinx) -> None:
    app.add_config_value('fmv_flyout_host', '', 'html', str)
    app.add_config_value('fmv_flyout_repository', '', 'html', str)
    app.add_config_value('fmv_flyout_downloads', [], 'html', list)
    app.add_config_value('fmv_metadata', {}, 'html')
    app.add_config_value('fmv_metadata_path', '', 'html')
    app.add_config_value('fmv_current_version', '', 'html')
    app.add_config_value('fmv_latest_version', 'master', 'html')
    app.connect('config-inited', _add_config_values)

    app.add_config_value('fmv_tag_whitelist', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_branch_whitelist', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_flyout_branch_list', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_flyout_tag_list', DEFAULT_REF_WHITELIST, 'html')
    app.add_config_value('fmv_remote_whitelist', DEFAULT_REMOTE_WHITELIST, 'html')
    app.add_config_value('fmv_released_pattern', DEFAULT_RELEASED_PATTERN, 'html')
    app.connect('config-inited', config_inited)
