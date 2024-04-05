import collections
import datetime
import logging
import os
import re
import subprocess
import tarfile
import tempfile
from typing import Generator, Iterator

GitRef = collections.namedtuple(
    "GitRef",
    [
        "name",
        "commit",
        "source",
        "is_remote",
        "refname",
        "creatordate",
    ],
)

logger = logging.getLogger(__name__)


def get_toplevel_path(cwd: str = "") -> str:
    cmd = (
        "git",
        "rev-parse",
        "--show-toplevel",
    )
    output = subprocess.check_output(cmd, cwd=cwd).decode()
    return output.rstrip("\n")


def get_all_refs(gitroot: str) -> Iterator[GitRef]:
    cmd = (
        "git",
        "for-each-ref",
        "--format",
        "%(objectname)\t%(refname)\t%(creatordate:iso)",
        "refs",
    )
    output = subprocess.check_output(cmd, cwd=gitroot).decode()
    for line in output.splitlines():
        is_remote = False
        fields = line.strip().split("\t")
        if len(fields) != 3:
            continue

        commit = fields[0]
        refname = fields[1]
        creatordate = datetime.datetime.strptime(
            fields[2], "%Y-%m-%d %H:%M:%S %z"
        )

        # Parse refname
        matchobj = re.match(
            r"^refs/(heads|tags|remotes/[^/]+)/(\S+)$", refname
        )
        if not matchobj:
            continue
        source = matchobj.group(1)
        name = matchobj.group(2)

        if source.startswith("remotes/"):
            is_remote = True

        yield GitRef(name, commit, source, is_remote, refname, creatordate)


def get_refs(
        gitroot: str,
        tag_whitelist: list[str],
        branch_whitelist: list[str],
        remote_whitelist: list[str],
        files: tuple[str, ...] = ()
) -> Generator[GitRef, None, None]:
    for ref in get_all_refs(gitroot):
        if ref.source == "tags":
            if ref.name not in tag_whitelist:
                logger.debug(
                    "Skipping '%s' because tag '%s' doesn't match the "
                    "whitelist pattern",
                    ref.refname,
                    ref.name,
                )
                continue
        elif ref.source == "heads":
            if ref.name not in branch_whitelist:
                logger.debug(
                    "Skipping '%s' because branch '%s' doesn't match the "
                    "whitelist pattern",
                    ref.refname,
                    ref.name,
                )
                continue
        elif ref.is_remote and remote_whitelist is not None:
            remote_name = ref.source.partition("/")[2]
            if remote_name not in remote_whitelist:
                logger.debug(
                    "Skipping '%s' because remote '%s' doesn't match the "
                    "whitelist pattern",
                    ref.refname,
                    remote_name,
                )
                continue
            if ref.name not in branch_whitelist:
                logger.debug(
                    "Skipping '%s' because branch '%s' doesn't match the "
                    "whitelist pattern",
                    ref.refname,
                    ref.name,
                )
                continue
        else:
            logger.debug(
                "Skipping '%s' because its not a branch or tag", ref.refname
            )
            continue

        missing_files = [
            filename
            for filename in files
            if filename != "."
            and not file_exists(gitroot, ref.refname, filename)
        ]
        if missing_files:
            logger.debug(
                "Skipping '%s' because it lacks required files: %r",
                ref.refname,
                missing_files,
            )
            continue

        yield ref


def file_exists(gitroot: str, refname: str, filename: str) -> bool:
    if os.sep != "/":
        # Git requires / path sep, make sure we use that
        filename = filename.replace(os.sep, "/")

    cmd = (
        "git",
        "cat-file",
        "-e",
        f"{refname}:{filename}",
    )
    proc = subprocess.run(
        cmd, cwd=gitroot, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return proc.returncode == 0


def copy_tree(gitroot: str, src: str, dst: str, reference: GitRef, sourcepath: str = ".") -> None:
    with tempfile.SpooledTemporaryFile() as fp:
        cmd = (
            "git",
            "archive",
            "--format",
            "tar",
            reference.commit,
            "--",
            sourcepath,
        )
        subprocess.check_call(cmd, cwd=gitroot, stdout=fp)
        fp.seek(0)
        with tarfile.TarFile(fileobj=fp) as tarfp:
            tarfp.extractall(dst)