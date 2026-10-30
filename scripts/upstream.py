#!/usr/bin/env python3
"""Resolve released T3 artifacts, or check our successful-release marker. Stdlib only."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

UPSTREAM = "pingdotgg/t3code"
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-nightly\.[0-9.]+)?\Z")


def request(url, *, authenticated=True):
    headers = {"User-Agent": "t3-code-k8s-release", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN")
    if authenticated and token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def api(path):
    return json.loads(request(f"https://api.github.com/repos/{path}"))


def valid_release(release, channel):
    version = release.get("tag_name", "").removeprefix("v")
    return bool(
        VERSION.fullmatch(version)
        and not release.get("draft", False)
        and ("-nightly." in version) == (channel == "nightly")
        and bool(release.get("prerelease", False)) == (channel == "nightly")
    )


def select_release(channel, version=None):
    if version:
        if not VERSION.fullmatch(version):
            raise ValueError("Expected an exact stable or nightly version (without v)")
        release = api(f"{UPSTREAM}/releases/tags/v{version}")
    elif channel == "stable":
        release = api(f"{UPSTREAM}/releases/latest")
    else:
        # Preview builds are deliberately excluded, even when newer than nightly.
        candidates = api(f"{UPSTREAM}/releases?per_page=100")
        release = max(
            (r for r in candidates if valid_release(r, channel)),
            key=lambda r: r["published_at"],
            default=None,
        )
    if not release or not valid_release(release, channel):
        raise ValueError(f"No valid published {channel} release found")
    return release


def published(repository, channel, version):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository")
    try:
        release = api(f"{repository}/releases/tags/{channel}-v{version}")
        return not release.get("draft", False)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise  # Do not interpret outages, auth failures or rate limits as changes.


def checksums(release):
    version = release["tag_name"].removeprefix("v")
    assets = {asset["name"]: asset for asset in release["assets"]}
    sums = assets["SHA256SUMS"]
    expected_url = f"https://github.com/{UPSTREAM}/releases/download/v{version}/SHA256SUMS"
    if sums["browser_download_url"] != expected_url:
        raise ValueError("Unexpected checksum URL")
    text = request(expected_url, authenticated=False).decode()
    result = {}
    for arch, upstream_arch in (("amd64", "x64"), ("arm64", "arm64")):
        filename = f"t3-{version}-linux-{upstream_arch}.tar.gz"
        if filename not in assets:
            raise ValueError(f"Missing release asset: {filename}")
        matches = re.findall(r"^([a-fA-F0-9]{64}) [ *]" + re.escape(filename) + r"$", text, re.M)
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous checksum: {filename}")
        result[f"sha256_{arch}"] = matches[0].lower()
    return result


def emit(values):
    print(json.dumps(values, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=("stable", "nightly"), required=True)
    parser.add_argument("--version", help="Exact upstream version; defaults to current channel")
    parser.add_argument("--check", metavar="OWNER/REPO", help="Only check successful-release marker")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    release = select_release(args.channel, args.version)
    version = release["tag_name"].removeprefix("v")
    values = {"version": version, "channel": args.channel}
    if args.check:
        values["changed"] = args.force or not published(args.check, args.channel, version)
    else:
        values.update(checksums(release))
    emit(values)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, urllib.error.URLError) as error:
        print(f"Upstream resolution failed: {error}", file=sys.stderr)
        sys.exit(1)
