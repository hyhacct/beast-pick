"""Version, changelog and annotated-tag management; version lives in the package."""
from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / 'beast_pick' / '__init__.py'
CHANGELOG = ROOT / 'CHANGELOG.md'
SEMVER = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z')


def parse_version(value: str) -> tuple[int, int, int]:
    if not SEMVER.fullmatch(value):
        raise ValueError('版本必须为 X.Y.Z，例如 0.2.1；不接受前导零。')
    numbers = tuple(map(int, value.split('.')))
    if any(number > 65535 for number in numbers):
        raise ValueError('版本分量不能超过 Windows 文件版本上限 65535。')
    return numbers


def current_version() -> str:
    tree = ast.parse(VERSION_FILE.read_text(encoding='utf-8'))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in statement.targets):
            value = ast.literal_eval(statement.value)
            parse_version(value)
            return value
    raise ValueError('未找到唯一版本来源 __version__。')


def release_notes(version: str, changelog: str) -> str:
    parse_version(version)
    sections = re.findall(r'^## \[' + re.escape(version) + r'\] - (\d{4}-\d{2}-\d{2})\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
    if len(sections) != 1:
        raise ValueError(f'CHANGELOG.md 中必须恰好有一个 {version} 版本章节。')
    release_date, notes = sections[0]
    date.fromisoformat(release_date)
    if not notes.strip() or '待补充' in notes:
        raise ValueError('请先填写本版本实际变更，再发布。')
    return notes.strip() + '\n'


def check(tag: str | None = None) -> str:
    version = current_version()
    if tag is not None and tag != f'v{version}':
        raise ValueError(f'标签 {tag} 与源码版本 v{version} 不一致。')
    release_notes(version, CHANGELOG.read_text(encoding='utf-8'))
    return version


def bump(version: str) -> None:
    if parse_version(version) <= parse_version(current_version()):
        raise ValueError('新版本必须高于当前版本。')
    changelog = CHANGELOG.read_text(encoding='utf-8')
    if re.search(r'^## \[' + re.escape(version) + r'\]', changelog, re.M):
        raise ValueError('此版本已经存在于更新日志。')
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    index = changelog.find('\n## [')
    if index < 0:
        raise ValueError('更新日志缺少可识别的版本章节。')
    section = f'\n## [{version}] - {today}\n\n### 变更\n\n- 待补充本版本变更。\n'
    source = VERSION_FILE.read_text(encoding='utf-8')
    source, count = re.subn(r"(?m)^__version__\s*=\s*['\"][^'\"]+['\"]", f"__version__ = '{version}'", source)
    if count != 1:
        raise ValueError('版本定义不唯一。')
    VERSION_FILE.write_text(source, encoding='utf-8')
    CHANGELOG.write_text(changelog[:index] + section + changelog[index:], encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('version')
    verify = commands.add_parser('check')
    verify.add_argument('--tag')
    update = commands.add_parser('bump')
    update.add_argument('version')
    notes = commands.add_parser('notes')
    notes.add_argument('--output', type=Path)
    commands.add_parser('tag')
    args = parser.parse_args()
    if args.command == 'version':
        print(current_version())
    elif args.command == 'check':
        print(check(args.tag))
    elif args.command == 'bump':
        bump(args.version)
        print(f'已更新为 {args.version}，请填写 CHANGELOG.md 后提交。')
    elif args.command == 'notes':
        text = release_notes(check(), CHANGELOG.read_text(encoding='utf-8'))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding='utf-8')
        else:
            print(text, end='')
    elif args.command == 'tag':
        version = check()
        dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
        if dirty.strip():
            raise ValueError('工作区尚有未提交改动，请先提交后再创建发布标签。')
        tag = f'v{version}'
        if subprocess.run(['git', 'rev-parse', '--verify', '--quiet', f'refs/tags/{tag}'], cwd=ROOT, stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError(f'标签 {tag} 已存在；发布新版本时请提升版本号。')
        subprocess.run(['git', 'tag', '-a', tag, '-m', f'Beast Pick {tag}'], cwd=ROOT, check=True)
        print(tag)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
