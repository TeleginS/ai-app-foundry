#!/usr/bin/env python3
"""Check or bump the AI App Foundry version in every manifest. Python standard library only."""

import argparse
import json
from pathlib import Path
import re
import sys


NAME = "ai-app-foundry"
ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
VERSION_FIELD = r'"version"\s*:\s*"([^"]*)"'


def top_level(data):
    return data["version"]


def marketplace_entry(data):
    for plugin in data["plugins"]:
        if plugin["name"] == NAME:
            return plugin["version"]
    raise Failure(f"marketplace does not list {NAME}")


# Each location: file, regex whose single match captures the version, and for JSON
# files the field that must hold the captured value (guards against matching another key).
LOCATIONS = (
    ("plugin.json", VERSION_FIELD, top_level),
    ("plugin.json", r"Version (\S+) includes", None),
    (".codex-plugin/plugin.json", VERSION_FIELD, top_level),
    (".claude-plugin/plugin.json", VERSION_FIELD, top_level),
    (".claude-plugin/marketplace.json", VERSION_FIELD, marketplace_entry),
    ("package.json", VERSION_FIELD, top_level),
    ("README.md", r"(?m)^## Included in (\S+)$", None),
)


class Failure(Exception):
    pass


def find(root, path, pattern, field):
    text = (root / path).read_text(encoding="utf-8")
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise Failure(f"{path}: expected one match for {pattern!r}, found {len(matches)}")
    match = matches[0]
    if field is not None and field(json.loads(text)) != match.group(1):
        raise Failure(f"{path}: {pattern!r} matched a value other than the manifest version")
    return text, match


def read_versions(root):
    return [(path, find(root, path, pattern, field)[1].group(1))
            for path, pattern, field in LOCATIONS]


def current_version(root):
    versions = read_versions(root)
    found = {version for _, version in versions}
    if len(found) != 1:
        details = "\n".join(f"  {path}: {version}" for path, version in versions)
        raise Failure(f"versions disagree:\n{details}")
    return found.pop()


def parse(version):
    match = SEMVER.fullmatch(version)
    if not match:
        raise Failure(f"{version!r} is not a semantic version X.Y.Z")
    return tuple(int(part) for part in match.groups())


def bump(root, new):
    old = current_version(root)
    if parse(new) <= parse(old):
        raise Failure(f"new version {new} must be greater than the current {old}")
    # current_version() has verified one match per location; edit pending text so
    # several locations in the same file compose before anything is written.
    texts = {}
    for path, pattern, _ in LOCATIONS:
        text = texts.get(path) or (root / path).read_text(encoding="utf-8")
        match = re.search(pattern, text)
        texts[path] = text[:match.start(1)] + new + text[match.end(1):]
    for path, text in texts.items():
        if path.endswith(".json"):
            json.loads(text)
        (root / path).write_text(text, encoding="utf-8")
    if current_version(root) != new:
        raise Failure("version update did not apply to every location")
    return old


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="verify that every location has the same version")
    bump_command = commands.add_parser("bump", help="set a new, greater version everywhere")
    bump_command.add_argument("version", help="new semantic version X.Y.Z")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "check":
            version = current_version(args.root)
            print(f"{NAME} {version}: {len(LOCATIONS)} locations agree")
        else:
            old = bump(args.root, args.version)
            for path, _, _ in LOCATIONS:
                print(f"{path}: {old} -> {args.version}")
    except Failure as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
