import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from flyout_multiversion.errors import GitError
from flyout_multiversion.git import (
    VersionRef,
    copy_tree,
    file_exists,
    get_all_refs,
    get_refs,
    get_toplevel_path,
)


@pytest.fixture
def tmp_repo_path(tmp_path: Path) -> Path:
    tmp_repo_path = tmp_path / "repo"
    tmp_repo_path.mkdir()
    os.chdir(tmp_repo_path)
    subprocess.check_call(["git", "init"])
    return tmp_repo_path


class TestGetToplevelPath:

    def test_get_toplevel_path(self, tmp_repo_path: Path) -> None:
        assert get_toplevel_path() == str(tmp_repo_path)

    def test_get_toplevel_path_with_no_tmp_repo_path(self, tmp_path: Path) -> None:
        path = tmp_path / "no_repo_dir"
        path.mkdir()
        os.chdir(path)
        with pytest.raises(GitError):
            get_toplevel_path()


def test_get_all_refs(tmp_repo_path: Path) -> None:
    subprocess.check_call(["git", "commit", "--allow-empty", "-m", "Initial commit"])
    subprocess.check_call(["git", "branch", "test-branch"])
    subprocess.check_call(["git", "tag", "test-tag"])

    refs = list(get_all_refs(str(tmp_repo_path)))
    assert len(refs) == 3
    assert any(ref.name == "master" and ref.source == "heads" for ref in refs)
    assert any(ref.name == "test-branch" and ref.source == "heads" for ref in refs)
    assert any(ref.name == "test-tag" and ref.source == "tags" for ref in refs)


class TestGetRefs:

    def test_get_refs(self, tmp_repo_path: Path) -> None:
        subprocess.check_call(["git", "commit", "--allow-empty", "-m", "Initial commit"])
        subprocess.check_call(["git", "branch", "test-branch"])
        subprocess.check_call(["git", "tag", "test-tag"])

        tag_whitelist = ["test-tag"]
        branch_whitelist = ["test-branch"]
        remote_whitelist: list[str] = []
        refs = list(get_refs(str(tmp_repo_path), tag_whitelist, branch_whitelist, remote_whitelist))
        assert len(refs) == 2
        assert any(ref.name == "test-branch" and ref.source == "heads" for ref in refs)
        assert any(ref.name == "test-tag" and ref.source == "tags" for ref in refs)

    def test_get_refs_with_empty_repo(self, tmp_repo_path: Path) -> None:
        refs = list(get_refs(str(repo), [], [], []))
        assert len(refs) == 0


class TestFileExists:
    def test_file_exists(self, tmp_repo_path: Path) -> None:
        (tmp_repo_path / "test-file").write_text("test content")
        subprocess.check_call(["git", "add", "test-file"])
        subprocess.check_call(["git", "commit", "-m", "Add test file"])

        assert file_exists(str(tmp_repo_path), "master", "test-file")
        assert not file_exists(str(tmp_repo_path), "master", "nonexistent-file")

    def test_file_exists_with_invalid_ref(self, tmp_repo_path: Path) -> None:
        assert not file_exists(str(tmp_repo_path), "invalid-ref", "test-file")


class TestCopyTree:
    def test_copy_tree(self, tmp_repo_path: Path, tmp_path: Path) -> None:
        (tmp_repo_path / "file1").write_text("content1")
        (tmp_repo_path / "file2").write_text("content2")
        subprocess.check_call(["git", "add", "file1", "file2"])
        subprocess.check_call(["git", "commit", "-m", "Add test files"])

        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        version_ref = VersionRef(
            name="master",
            commit=commit_hash,
            source="heads",
            is_remote=False,
            refname="refs/heads/master",
            creatordate=datetime.now(),
        )

        dst = (tmp_path / "dst")
        dst.mkdir()
        copy_tree(str(tmp_repo_path), str(dst), version_ref)

        assert (dst / "file1").read_text() == "content1"
        assert (dst / "file2").read_text() == "content2"

    def test_copy_tree_with_subdir(self, tmp_repo_path: Path, tmp_path: Path) -> None:
        sub = tmp_repo_path / "subdir"
        sub.mkdir()
        (sub / "file1").write_text("content1")
        (tmp_repo_path / "file2").write_text("content2")
        subprocess.check_call(["git", "add", "subdir/file1", "file2"])
        subprocess.check_call(["git", "commit", "-m", "Add test files"])

        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        version_ref = VersionRef(
            name="master",
            commit=commit_hash,
            source="heads",
            is_remote=False,
            refname="refs/heads/master",
            creatordate=datetime.now(),
        )

        dst = tmp_path / "dst"
        dst.mkdir()

        copy_tree(str(tmp_repo_path), str(dst), version_ref, sourcepath="subdir")

        assert (dst / "subdir" / "file1").read_text() == "content1"
        assert not (dst / "file2").exists()

    def test_copy_tree_with_symlink(self, tmp_repo_path: Path, tmp_path: Path) -> None:
        file = tmp_repo_path / "file"
        file.write_text("content")
        os.symlink(file, tmp_repo_path / "symlink")
        subprocess.check_call(["git", "add", "file", "symlink"])
        subprocess.check_call(["git", "commit", "-m", "Add file and symlink"])

        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        version_ref = VersionRef(
            name="master",
            commit=commit_hash,
            source="heads",
            is_remote=False,
            refname="refs/heads/master",
            creatordate=datetime.now(),
        )

        dst = tmp_path / "dst"
        dst.mkdir()
        copy_tree(str(tmp_repo_path), str(dst), version_ref)

        assert (dst / "file").read_text() == "content"
        assert (dst / "symlink").readlink() == (tmp_repo_path / "file")
