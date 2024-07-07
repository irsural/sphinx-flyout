import os
from datetime import datetime
from pathlib import Path
from subprocess import check_call, check_output
from typing import Sequence, Union

import pytest

from flyout_multiversion.errors import GitError
from flyout_multiversion.git import (
    VersionRef,
    _file_exists,
    _get_all_refs,
    copy_tree,
    get_refs,
    get_toplevel_path,
)


@pytest.fixture
def tmp_repo_path(tmp_path: Path) -> Path:
    tmp_repo_path = tmp_path / 'repo'
    tmp_repo_path.mkdir()
    os.chdir(tmp_repo_path)
    check_call(['git', 'init'])
    check_call(['git', 'config', 'user.email', '"test@run.ner'])
    check_call(['git', 'config', 'user.name', '"test_runner'])
    return tmp_repo_path


def create_branch(branchname: str = 'master') -> None:
    check_call(['git', 'branch', branchname])


def create_tag(tagname: str = 'release') -> None:
    check_call(['git', 'tag', tagname])


def create_init_commit() -> None:
    check_call(['git', 'commit', '--allow-empty', '-m', 'Initial commit'])


def add_files(files: Sequence[Union[str, Path]]) -> None:
    check_call(['git', 'add', *files])


def create_commit(message: str = 'Added test files') -> None:
    check_call(['git', 'commit', '-m', message])


def get_commit_hash() -> str:
    return check_output(['git', 'rev-parse', 'HEAD']).decode().strip()


class TestGetToplevelPath:
    def test_get_toplevel_path(self, tmp_repo_path: Path) -> None:
        assert get_toplevel_path() == tmp_repo_path

    def test_get_toplevel_path_with_no_tmp_repo_path(self, tmp_path: Path) -> None:
        path = tmp_path / 'no_repo_dir'
        path.mkdir()
        os.chdir(path)
        with pytest.raises(GitError):
            get_toplevel_path()


def test_get_all_refs(tmp_repo_path: Path) -> None:
    create_init_commit()
    create_branch('test-branch')
    create_tag('test-tag')

    refs = list(_get_all_refs(tmp_repo_path))
    assert len(refs) == 3
    assert any(ref.name == 'master' and ref.source == 'heads' for ref in refs)
    assert any(ref.name == 'test-branch' and ref.source == 'heads' for ref in refs)
    assert any(ref.name == 'test-tag' and ref.source == 'tags' for ref in refs)


class TestGetRefs:
    def test_get_refs(self, tmp_repo_path: Path) -> None:
        create_init_commit()
        create_branch('test-branch')
        create_tag('test-tag')

        tag_whitelist = ['test-tag']
        branch_whitelist = ['test-branch']
        refs = list(get_refs(tmp_repo_path, tag_whitelist, branch_whitelist))
        assert len(refs) == 2
        assert any(ref.name == 'test-branch' and ref.source == 'heads' for ref in refs)
        assert any(ref.name == 'test-tag' and ref.source == 'tags' for ref in refs)

    def test_get_refs_with_empty_repo(self, tmp_repo_path: Path) -> None:
        refs = list(
            get_refs(
                tmp_repo_path,
                [],
                [],
            )
        )
        assert len(refs) == 0


class TestFileExists:
    def test_file_exists(self, tmp_repo_path: Path) -> None:
        (tmp_repo_path / 'test-file').write_text('test content')
        add_files(['test-file'])
        create_commit()

        assert _file_exists(tmp_repo_path, 'master', Path('test-file'))
        assert not _file_exists(tmp_repo_path, 'master', Path('nonexistent-file'))

    def test_file_exists_with_invalid_ref(self, tmp_repo_path: Path) -> None:
        assert not _file_exists(tmp_repo_path, 'invalid-ref', Path('test-file'))


class TestCopyTree:
    def test_copy_tree(self, tmp_repo_path: Path, tmp_path: Path) -> None:
        (tmp_repo_path / 'file1').write_text('content1')
        (tmp_repo_path / 'file2').write_text('content2')
        add_files(['file1', 'file2'])
        create_commit()

        commit_hash = get_commit_hash()
        version_ref = VersionRef(
            name='master',
            commit=commit_hash,
            source='heads',
            is_remote=False,
            refname='refs/heads/master',
            creatordate=datetime.now(),
        )

        dst = tmp_path / 'dst'
        dst.mkdir()
        copy_tree(tmp_repo_path, dst, version_ref)

        assert (dst / 'file1').read_text() == 'content1'
        assert (dst / 'file2').read_text() == 'content2'

    def test_copy_tree_with_subdir(self, tmp_repo_path: Path, tmp_path: Path) -> None:
        sub = tmp_repo_path / 'subdir'
        sub.mkdir()
        (sub / 'file1').write_text('content1')
        (tmp_repo_path / 'file2').write_text('content2')
        add_files(['subdir/file1', 'file2'])
        create_commit()

        commit_hash = get_commit_hash()
        version_ref = VersionRef(
            name='master',
            commit=commit_hash,
            source='heads',
            is_remote=False,
            refname='refs/heads/master',
            creatordate=datetime.now(),
        )

        dst = tmp_path / 'dst'
        dst.mkdir()

        copy_tree(tmp_repo_path, dst, version_ref, sourcepath='subdir')

        assert (dst / 'subdir' / 'file1').read_text() == 'content1'
        assert not (dst / 'file2').exists()

    def test_copy_tree_with_symlink(self, tmp_repo_path: Path, tmp_path: Path) -> None:
        file = tmp_repo_path / 'file'
        file.write_text('content')
        os.symlink(file, tmp_repo_path / 'symlink')
        add_files(['file', 'symlink'])
        create_commit('Add file and symlink')

        commit_hash = get_commit_hash()
        version_ref = VersionRef(
            name='master',
            commit=commit_hash,
            source='heads',
            is_remote=False,
            refname='refs/heads/master',
            creatordate=datetime.now(),
        )

        dst = tmp_path / 'dst'
        dst.mkdir()
        copy_tree(tmp_repo_path, dst, version_ref)

        assert (dst / 'file').read_text() == 'content'
        assert (dst / 'symlink').read_text() == 'content'
        assert (dst / 'symlink').resolve() == (tmp_repo_path / 'file')
