import argparse
import json
import os
import sys
from itertools import chain
from logging import getLogger
from pathlib import Path
from string import Template
from subprocess import CalledProcessError, check_call
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Tuple, Union

from sphinx.config import Config
from sphinx.errors import ConfigError

from flyout_multiversion import flyout_menu, git

logger = getLogger(__name__)


def load_sphinx_config(
    confpath: str, confoverrides: Dict[str, Any], add_defaults: bool = False
) -> Config:

    current_config = Config.read(
            confpath,
            confoverrides)

    if add_defaults:
        current_config.add('fmv_tag_build_list', [], 'html', str)
        current_config.add(
            'fmv_branch_build_list',
            flyout_menu.DEFAULT_REF_WHITELIST,
            'html',
            str,
        )
    current_config.pre_init_values()
    current_config.init_values()

    return current_config


def get_python_flags() -> List[str]:
    flags: List[Union[Tuple[str, int], Tuple[str, ...]]] = [
        ('-b', sys.flags.bytes_warning),
        ('-d', sys.flags.debug),
        ('-R', sys.flags.hash_randomization),
        ('-E', sys.flags.ignore_environment),
        ('-i', sys.flags.inspect),
        ('-I', sys.flags.isolated),
        ('-S', sys.flags.no_site),
        ('-s', sys.flags.no_user_site),
        ('-O', sys.flags.optimize),
        ('-q', sys.flags.quiet),
        ('-v', sys.flags.verbose),
    ]

    flags.extend([
        ('-X', f'{option}={value}' if value is not True else '-X', f'{option}')
        for option, value in sys._xoptions.items()
    ])

    return [flag for flag, enabled in flags if enabled]


def main(argv: Union[List[str], None] = None) -> int:
    if not argv:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument('sourcedir', help='Путь до исходных файлов документации')
    parser.add_argument('outputdir', help='Путь до папки с готовым')
    parser.add_argument(
        'filenames',
        nargs='*',
        help='Список файлов для пересборки. Игнорируется при указании -a',
    )
    parser.add_argument(
        '-c',
        metavar='PATH',
        dest='confdir',
        help='Путь до конфигурационного файла (conf.py). По умолчанию - тот же, что и SOURCEDIR)',
    )
    parser.add_argument(
        '-D',
        metavar='setting=value',
        action='append',
        dest='define',
        default=[],
        help='Переопределение параметров конфигурационного файла',
    )
    parser.add_argument(
        '--dump-metadata',
        action='store_true',
        help='Сохранить метаданные и выйти',
    )
    args, argv = parser.parse_known_args(argv)

    sourcedir_absolute = os.path.abspath(args.sourcedir)
    confdir_absolute = (
        os.path.abspath(args.confdir) if args.confdir is not None else sourcedir_absolute
    )

    # Переопределение конфигурационных данных
    confoverrides = {}
    for d in args.define:
        key, _, value = d.partition('=')
        confoverrides[key] = value

    # Парсинг конфига
    config = load_sphinx_config(confdir_absolute, confoverrides, add_defaults=True)

    # Получение относительных путей относительно корня git-репозитория
    gitroot = Path(git.get_toplevel_path(cwd=sourcedir_absolute)).resolve()

    logger.debug('Git toplevel path: %s', str(gitroot))
    sourcedir = os.path.relpath(sourcedir_absolute, str(gitroot))
    logger.debug('Source dir (relative to git toplevel path): %s', str(sourcedir))
    confdir = os.path.relpath(confdir_absolute, str(gitroot)) if args.confdir else sourcedir

    logger.debug('Conf dir (relative to git toplevel path): %s', str(confdir))
    conffile = Path(confdir, 'conf.py')

    # Получение веток и тегов Git
    gitrefs = git.get_refs(
        gitroot,
        config.fmv_tag_build_list,
        config.fmv_branch_build_list,
        files=(Path(sourcedir), conffile),
    )

    gitref_list = sorted(gitrefs, key=lambda x: (not x.is_remote, *x))

    with TemporaryDirectory() as tmp:
        # Генерация метаданных
        metadata = {}
        for gitref in gitref_list:
            # Клонирование Git-репозитория
            repopath = Path(tmp, gitref.commit)
            try:
                git.copy_tree(gitroot, repopath, gitref)
            except (OSError, CalledProcessError):
                logger.error(
                    'Не удалось скопировать %s в %s',
                    gitref.refname,
                    repopath,
                )
                continue

            # Поиск файла конфигурации
            confpath = repopath / confdir
            try:
                current_config = load_sphinx_config(str(confpath), confoverrides)
            except (OSError, ConfigError):
                logger.error(
                    'Ошибка загрузки конфигурации %s из %s',
                    gitref.refname,
                    confpath,
                )
                continue

            outputdir = f'{"branches" if gitref.source == "heads" else "tags"}/{gitref.name}'

            current_sourcedir = os.path.join(repopath, sourcedir)
            metadata[gitref.name] = {
                'name': gitref.name,
                'version': current_config.version,
                'release': current_config.release,
                'rst_prolog': current_config.rst_prolog,
                'source': gitref.source,
                'creatordate': gitref.creatordate.strftime(flyout_menu.DATE_FMT),
                'basedir': str(repopath),
                'sourcedir': current_sourcedir,
                'outputdir': os.path.join(os.path.abspath(args.outputdir), outputdir),
                'confdir': str(confpath),
            }

        if args.dump_metadata:
            logger.info(json.dumps(metadata, indent=2))
            return 0

        if not metadata:
            logger.error('Не найдено подходящих веток и тэгов')
            return 2

        # Write Metadata
        metadata_path = os.path.abspath(os.path.join(tmp, 'versions.json'))
        with open(metadata_path, mode='w') as fp:
            json.dump(metadata, fp, indent=2)

        # Run Sphinx
        argv.extend(['-D', f'fmv_metadata_path={metadata_path}'])
        for version_name, data in metadata.items():
            os.makedirs(data['outputdir'], exist_ok=True)

            defines = chain(*(('-D', Template(d).safe_substitute(data)) for d in args.define))

            current_argv = argv.copy()
            current_argv.extend([
                *defines,
                '-D',
                f'fmv_current_version={version_name}',
                '-c',
                confdir_absolute,
                data['sourcedir'],
                data['outputdir'],
                *args.filenames,
            ])
            logger.debug('Запуск sphinx-build %r', current_argv)
            cmd = (
                sys.executable,
                *get_python_flags(),
                '-m',
                'sphinx',
                *current_argv,
            )
            check_call(cmd, cwd=data['basedir'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
