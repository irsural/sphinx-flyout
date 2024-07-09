import random
from pathlib import Path
from subprocess import check_call
from typing import List

import pytest
from test_flyout_multiversion_git import add_files, create_commit, tmp_repo_path

from flyout_multiversion.__main__ import main as build_multiversion


@pytest.fixture
def setup_sample_repo_with_refs(tmp_repo_path: Path, branches: List[str], tags: List[str]) -> Path:
    create_master(tmp_repo_path, branches, tags)
    for branch in branches:
        create_new_branch(branch)
    for tag in tags:
        random_branch = random.choice(branches + ['master'])
        switch(random_branch)
        create_new_tag(tag)
        create_post_tag_commit(tag, random_branch)
    switch('master')
    return tmp_repo_path


def create_new_branch(branch: str) -> None:
    check_call(['git', 'checkout', '-b', branch])
    files = create_branch_files(branch)
    add_files(files)
    create_commit('Added to ' + branch)


def create_new_tag(tag: str) -> None:
    with open(f'{tag}_file.rst', 'w', encoding='utf-8') as f:
        f.write(f'This file is associated with tag {tag}')

    add_files([f'{tag}_file.rst'])
    create_commit(f'Added file for tag {tag}')
    add_tag(tag)


def create_post_tag_commit(tag: str, branch: str) -> None:
    with open(f'post_tag_{tag}_on_{branch}_file.rst', 'w', encoding='utf-8') as f:
        f.write(f'This file is created after tagging {tag} on branch {branch}')

    add_files([f'post_tag_{tag}_on_{branch}_file.rst'])
    create_commit(f'Post-tag {tag} commit on {branch}')


def add_tag(tag_name: str) -> None:
    check_call(['git', 'tag', '-a', tag_name, '-m', f'This is tag {tag_name}'])


def switch(ref: str) -> None:
    check_call(['git', 'switch', ref])


def create_master(tmp_repo_path: Path, branches: List[str], tags: List[str]) -> None:
    with open(tmp_repo_path / 'conf.py', 'w+', encoding='utf8') as conf:
        lines = [
            "project = 'Test'\n",
            "extensions = ['flyout_multiversion']\n",
            "html_theme = 'sphinx_rtd_theme'\n",
            "fmv_flyout_downloads = ['html', 'source']\n",
            f"fmv_branch_build_list = {branches + ['master']}\n",
            f'fmv_tag_build_list = {tags}\n',
            "fmv_flyout_host = '0.0.0.0:8001'\n",
            "fmv_flyout_repository = 'https://google.com'\n",
        ]
        conf.writelines(lines)
    with open(tmp_repo_path / 'index.rst', 'w+', encoding='utf-8') as rst:
        rst.write('This is a master branch')
    add_files([tmp_repo_path / 'index.rst', tmp_repo_path / 'conf.py'])
    create_commit('Master init commit')


def create_branch_files(branch: str) -> List[str]:
    with open('conf.py', 'w+', encoding='utf8') as conf:
        lines = [
            f"project = 'Test_{branch}'\n",
            "extensions = ['flyout_multiversion']\n",
            "html_theme = 'sphinx_rtd_theme'\n",
        ]
        conf.writelines(lines)
    with open('index.rst', 'w+', encoding='utf-8') as rst:
        rst.write(f'This is a {branch} branch')
    return ['index.rst', 'conf.py']


@pytest.mark.parametrize(
    'branches,tags',
    [
        pytest.param(['dev', 'oppa'], ['v1', 'v2', 'v3'], id='branches and tags'),
        pytest.param([], [], id='empty'),
        pytest.param(['br1', 'br2'], [], id='branches only'),
        pytest.param([], ['tag1', 'ta.g2'], id='tags only'),
    ],
)
def test_build_multiversion(
    tmp_path: Path, setup_sample_repo_with_refs: Path, branches: List[str], tags: List[str]
) -> None:
    build_folder = tmp_path / 'build'
    build_multiversion([str(setup_sample_repo_with_refs), str(build_folder)])
    actual_folder_content = ['branches', 'tags'] if tags else ['branches']
    assert sorted([f.name for f in build_folder.iterdir()]) == actual_folder_content

    branches.append('master')
    branch_folder = build_folder / 'branches'
    assert sorted([b.name for b in branch_folder.iterdir()]) == sorted(branches)
    for branch in branches:
        current_path = branch_folder / branch
        with open(current_path / 'index.html') as index:
            assert branch in index.read()

    if tags:
        tag_folder = build_folder / 'tags'
        assert sorted([t.name for t in tag_folder.iterdir()]) == sorted(tags)
        for tag in tags:
            current_path = tag_folder / tag
            with open(current_path / f'{tag}_file.html') as rst:
                assert tag in rst.read()
