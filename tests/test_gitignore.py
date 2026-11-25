"""Keep local artifacts out of Git without hiding runtime resources."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_git_repo(tmp_path):
    env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, env=env)
    (tmp_path / '.gitignore').write_text((ROOT / '.gitignore').read_text(encoding='utf-8'), encoding='utf-8')
    return tmp_path, env


def ignored(repo, env, path):
    result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '-q', '--no-index', '--', path], env=env)
    assert result.returncode in (0, 1)
    return result.returncode == 0


@pytest.mark.parametrize('path', [
    '.workbuddy/memory/session.md', '.venv/Scripts/python.exe', 'artifacts/probe.json',
    'logs/beast-pick.log', 'build/beast-pick/output.bin', 'dist/BP.exe', 'release/BP.exe',
    '.pytest_cache/v/cache/nodeids', 'beast_pick/__pycache__/module.pyc',
    '.mypy_cache/3.12/cache.json', '.ruff_cache/0.1/cache', '.coverage',
    'htmlcov/index.html', 'node_modules/pkg/index.js', 'scratch.tmp', 'run.log',
    'old.bak', 'test.exe', 'module.dll', 'debug.pdb', 'bundle.zip', 'bundle.7z',
    'package.whl', '.DS_Store', 'Thumbs.db',
])
def test_generated_files_are_ignored(isolated_git_repo, path):
    repo, env = isolated_git_repo
    assert ignored(repo, env, path)


@pytest.mark.parametrize('path', [
    'beast_pick/data/items.json', 'beast_pick/data/dl2_weapon_items.json',
    'beast_pick/data/weapons.json', 'beast_pick/profiles/current.json',
    'beast_pick/profiles/dl2.json', 'beast_pick/assets/beast-pick.ico',
    'packaging/beast-pick.spec', '.github/workflows/build.yml',
])
def test_runtime_and_packaging_resources_remain_trackable(isolated_git_repo, path):
    repo, env = isolated_git_repo
    assert not ignored(repo, env, path)
