import logging
import re
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterator, NamedTuple

from flyout_multiversion.errors import GitError


class VersionRef(NamedTuple):
    name: str
    commit: str
    source: str
    is_remote: bool
    refname: str
    creatordate: datetime


logger = logging.getLogger(__name__)


def get_toplevel_path(cwd: Path | None = None) -> Path:
    """
    Возвращает путь к корневой директории Git-репозитория.

    :param cwd: Путь к текущей рабочей директории
    :return: Путь к корневой директории Git-репозитория
    """
    cmd = (
        'git',
        'rev-parse',
        '--show-toplevel',
    )
    try:
        output = subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT).decode()
        return Path(output.rstrip('\n'))
    except subprocess.CalledProcessError as err:
        errormsg = f'Running {cmd} in {cwd} resulted in following error:\n{err.output.decode()}'
        raise GitError(errormsg) from err


def _get_all_refs(gitroot: Path) -> Iterator[VersionRef]:
    """
    Итерируется по ссылкам (ref) в Git-репозитории.

    :param gitroot: Путь к корневой директории Git-репозитория
    :return: Ссылки Git-репозитория в формате VersionRef
    """
    cmd = (
        'git',
        'for-each-ref',
        '--format',
        '%(objectname)\t%(refname)\t%(creatordate:iso)',
        'refs',
    )
    try:
        output = subprocess.check_output(cmd, cwd=gitroot, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as err:
        errormsg = (
            f'Running {cmd} in {gitroot} resulted in following error:\n{err.output.decode()}'
        )
        raise GitError(errormsg) from err
    for line in output.splitlines():
        is_remote = False
        fields = line.strip().split('\t')
        if len(fields) != 3:
            continue

        commit = fields[0]
        refname = fields[1]
        creatordate = datetime.strptime(fields[2], '%Y-%m-%d %H:%M:%S %z')

        # Parse refname
        matchobj = re.match(r'^refs/(heads|tags|remotes/[^/]+)/(\S+)$', refname)
        if not matchobj:
            continue
        source = matchobj.group(1)
        name = matchobj.group(2)

        if source.startswith('remotes/'):
            is_remote = True

        yield VersionRef(name, commit, source, is_remote, refname, creatordate)


def get_refs(
    gitroot: Path,
    tag_whitelist: list[str],
    branch_whitelist: list[str],
    remote_whitelist: list[str],
    files: tuple[str | Path, ...] = (),
) -> Iterator[VersionRef]:
    """
    Итерируется по отфильтрованным ссылкам (refs) в Git-репозитории.

    :param gitroot: Путь к корневой директории Git-репозитория
    :param tag_whitelist: Список разрешенных тегов
    :param branch_whitelist: Список разрешенных веток
    :param remote_whitelist: Список разрешенных удаленных репозиториев
    :param files: Кортеж обязательных файлов
    :return: Итератор с объектами VersionRef, представляющими отфильтрованные ссылки
    """
    for ref in _get_all_refs(gitroot):
        if ref.source == 'tags':
            if ref.name not in tag_whitelist:
                logger.debug(
                    "Skipping '%s' because tag '%s' doesn't match the whitelist pattern",
                    ref.refname,
                    ref.name,
                )
                continue
        elif ref.source == 'heads':
            if ref.name not in branch_whitelist:
                logger.debug(
                    "Skipping '%s' because branch '%s' doesn't match the whitelist pattern",
                    ref.refname,
                    ref.name,
                )
                continue
        elif ref.is_remote and remote_whitelist is not None:
            remote_name = ref.source.partition('/')[2]
            if remote_name not in remote_whitelist:
                logger.debug(
                    "Skipping '%s' because remote '%s' doesn't match the whitelist pattern",
                    ref.refname,
                    remote_name,
                )
                continue
            if ref.name not in branch_whitelist:
                logger.debug(
                    "Skipping '%s' because branch '%s' doesn't match the whitelist pattern",
                    ref.refname,
                    ref.name,
                )
                continue
        else:
            logger.debug("Skipping '%s' because its not a branch or tag", ref.refname)
            continue

        missing_files = [
            filename
            for filename in files
            if filename != '.' and not _file_exists(gitroot, ref.refname, Path(filename))
        ]
        if missing_files:
            logger.debug(
                "Skipping '%s' because it lacks required files: %r",
                ref.refname,
                missing_files,
            )
            continue

        yield ref


def _file_exists(gitroot: Path, refname: str, file: Path) -> bool:
    """
    Проверяет, существует ли файл в указанной ссылке (ref) в Git-репозитории.

    :param gitroot: Путь к корневой директории Git-репозитория
    :param refname: Имя ссылки (ref)
    :param filename: Имя файла
    :return: True, если файл существует, иначе False
    """
    filename = file.as_posix()

    cmd = (
        'git',
        'cat-file',
        '-e',
        f'{refname}:{filename}',
    )
    proc = subprocess.run(cmd, cwd=gitroot, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.returncode == 0


def copy_tree(gitroot: Path, dst: Path, reference: VersionRef, sourcepath: str = '.') -> None:
    """
    Копирует содержимое указанной ссылки (ref) из Git-репозитория в целевую директорию.

    :param gitroot: Путь к корневой директории Git-репозитория
    :param dst: Путь к целевой директории
    :param reference: Объект VersionRef, представляющий ссылку (ref)
    :param sourcepath: Путь к исходной директории (по умолчанию ".")
    """
    with tempfile.SpooledTemporaryFile() as fp:
        cmd = (
            'git',
            'archive',
            '--format',
            'tar',
            reference.commit,
            '--',
            sourcepath,
        )
        try:
            subprocess.check_call(cmd, cwd=gitroot, stdout=fp, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            errormsg = (
                f'Running {cmd} in {gitroot} resulted in following error:\n'
                f'{err.output.decode()}'
            )
            raise GitError(errormsg) from err
        fp.seek(0)
        with tarfile.TarFile(fileobj=fp) as tarfp:
            tarfp.extractall(dst)
