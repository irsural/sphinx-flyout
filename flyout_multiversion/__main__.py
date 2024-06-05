import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from itertools import chain
from logging import getLogger
from multiprocessing import Process, Queue
from pathlib import Path
from string import Template
from subprocess import CalledProcessError, check_call
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from sphinx.config import Config
from sphinx.errors import ConfigError
from typing_extensions import Never

from flyout_multiversion import _sphinx, git

logger = getLogger(__name__)


@contextmanager
def working_dir(path: str) -> Iterator[Never]:
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield  # type: ignore[misc]
    finally:
        os.chdir(prev_cwd)


def load_sphinx_config_worker(
    q: 'Queue[Config | Exception]', confpath: str, confoverrides: dict[str, Any], add_defaults: bool
) -> None:
    try:
        with working_dir(confpath):
            current_config = Config.read(
                confpath,
                confoverrides,
            )

        if add_defaults:
            current_config.add('fmv_tag_whitelist', _sphinx.DEFAULT_REF_WHITELIST, 'html', str)
            current_config.add(
                'fmv_branch_whitelist',
                _sphinx.DEFAULT_REF_WHITELIST,
                'html',
                str,
            )
            current_config.add(
                'fmv_remote_whitelist',
                _sphinx.DEFAULT_REMOTE_WHITELIST,
                'html',
                str,
            )
            current_config.add(
                'fmv_released_pattern',
                _sphinx.DEFAULT_RELEASED_PATTERN,
                'html',
                str,
            )
            current_config.add('fmv_prefer_remote_refs', False, 'html', bool)
        current_config.pre_init_values()
        current_config.init_values()
    except Exception as err:
        q.put(err)
        return

    q.put(current_config)


def load_sphinx_config(
    confpath: str, confoverrides: dict[str, Any], add_defaults: bool = False
) -> Config:
    q: 'Queue[Config | Exception]' = Queue()
    proc = Process(
        target=load_sphinx_config_worker,
        args=(q, confpath, confoverrides, add_defaults),
    )
    proc.start()
    proc.join()
    result = q.get_nowait()
    if isinstance(result, Exception):
        raise result
    return result


def get_python_flags() -> list[str]:
    flags: list[tuple[str, int] | tuple[str, ...]] = [
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


def main(argv: list[str] | None = None) -> int:
    if not argv:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument('sourcedir', help='path to documentation source files')
    parser.add_argument('outputdir', help='path to output directory')
    parser.add_argument(
        'filenames',
        nargs='*',
        help='a list of specific files to rebuild. Ignored if -a is specified',
    )
    parser.add_argument(
        '-c',
        metavar='PATH',
        dest='confdir',
        help=('path where configuration file (conf.py) is located ' '(default: same as SOURCEDIR)'),
    )
    parser.add_argument(
        '-D',
        metavar='setting=value',
        action='append',
        dest='define',
        default=[],
        help='override a setting in configuration file',
    )
    parser.add_argument(
        '--dump-metadata',
        action='store_true',
        help='dump generated metadata and exit',
    )
    args, argv = parser.parse_known_args(argv)

    sourcedir_absolute = os.path.abspath(args.sourcedir)
    confdir_absolute = (
        os.path.abspath(args.confdir) if args.confdir is not None else sourcedir_absolute
    )

    # Conf-overrides
    confoverrides = {}
    for d in args.define:
        key, _, value = d.partition('=')
        confoverrides[key] = value

    # Parse config
    config = load_sphinx_config(confdir_absolute, confoverrides, add_defaults=True)

    # Get relative paths to root of git repository
    gitroot = Path(git.get_toplevel_path(cwd=sourcedir_absolute)).resolve()

    logger.debug('Git toplevel path: %s', str(gitroot))
    sourcedir = os.path.relpath(sourcedir_absolute, str(gitroot))
    logger.debug('Source dir (relative to git toplevel path): %s', str(sourcedir))
    confdir = os.path.relpath(confdir_absolute, str(gitroot)) if args.confdir else sourcedir

    logger.debug('Conf dir (relative to git toplevel path): %s', str(confdir))
    conffile = Path(confdir, 'conf.py')

    # Get git references
    gitrefs = git.get_refs(
        gitroot,
        config.fmv_tag_whitelist,
        config.fmv_branch_whitelist,
        config.fmv_remote_whitelist,
        files=(Path(sourcedir), conffile),
    )

    # Order git refs
    if config.fmv_prefer_remote_refs:
        gitref_list = sorted(gitrefs, key=lambda x: (not x.is_remote, *x))
    else:
        gitref_list = sorted(gitrefs, key=lambda x: (x.is_remote, *x))

    with TemporaryDirectory() as tmp:
        # Generate Metadata
        metadata = {}
        outputdirs = set()
        for gitref in gitref_list:
            # Clone Git repo
            repopath = Path(tmp, gitref.commit)
            try:
                git.copy_tree(gitroot, repopath, gitref)
            except (OSError, CalledProcessError):
                logger.error(
                    'Failed to copy git tree for %s to %s',
                    gitref.refname,
                    repopath,
                )
                continue

            # Find config
            confpath = repopath / confdir
            try:
                current_config = load_sphinx_config(str(confpath), confoverrides)
            except (OSError, ConfigError):
                logger.error(
                    'Failed load config for %s from %s',
                    gitref.refname,
                    confpath,
                )
                continue

            # Ensure that there are not duplicate output dirs
            outputdir = f'{gitref.source}/{gitref.name}'
            outputdirs.add(outputdir)

            current_sourcedir = os.path.join(repopath, sourcedir)
            metadata[gitref.name] = {
                'name': gitref.name,
                'version': current_config.version,
                'release': current_config.release,
                'rst_prolog': current_config.rst_prolog,
                'is_released': bool(re.match(config.fmv_released_pattern, gitref.refname)),
                'source': gitref.source,
                'creatordate': gitref.creatordate.strftime(_sphinx.DATE_FMT),
                'basedir': repopath,
                'sourcedir': current_sourcedir,
                'outputdir': os.path.join(os.path.abspath(args.outputdir), outputdir),
                'confdir': confpath,
            }

        if args.dump_metadata:
            logger.info(json.dumps(metadata, indent=2))
            return 0

        if not metadata:
            logger.error('No matching refs found!')
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
            logger.debug('Running sphinx-build with args: %r', current_argv)
            cmd = (
                sys.executable,
                *get_python_flags(),
                '-m',
                'sphinx',
                *current_argv,
            )
            env = os.environ.copy()
            env.update({
                'SPHINX_MULTIVERSION_NAME': data['name'],
                'SPHINX_MULTIVERSION_VERSION': data['version'],
                'SPHINX_MULTIVERSION_RELEASE': data['release'],
                'SPHINX_MULTIVERSION_SOURCEDIR': data['sourcedir'],
                'SPHINX_MULTIVERSION_OUTPUTDIR': data['outputdir'],
                'SPHINX_MULTIVERSION_CONFDIR': data['confdir'],
            })
            check_call(cmd, cwd=data['basedir'], env=env)

    return 0


if __name__ == '__main__':
    sys.exit(main())
