#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

REPOSITORY = "kleverhq/ondas-fixtures"
API_URL = f"https://api.github.com/repos/{REPOSITORY}"
ROOT = Path(__file__).resolve().parent
SHA256 = re.compile(r"[0-9a-f]{64}")


def arguments():
    parser = argparse.ArgumentParser(description="Install waveform fixtures from GitHub release assets.")
    parser.add_argument("--dry-run", action="store_true", help="print missing assets without downloading")
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="install available assets when some expected assets are absent",
    )
    return parser.parse_args()


def request(url, accept="application/vnd.github+json"):
    headers = {
        "Accept": accept,
        "User-Agent": "ondas-fixtures-installer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return urlopen(Request(url, headers=headers))


def load_fixtures():
    fixtures = []
    for sidecar in sorted(ROOT.glob("*/fixture.json")):
        data = json.loads(sidecar.read_text())
        artifact = data["artifact"]
        filename = artifact["file"]
        digest = artifact["sha256"]
        if Path(filename).name != filename or not SHA256.fullmatch(digest):
            raise ValueError(f"invalid artifact metadata in {sidecar}")
        fixtures.append(
            {
                "name": sidecar.parent.name,
                "path": sidecar.parent / filename,
                "format": artifact["format"],
                "size": artifact["size"],
                "sha256": digest,
            }
        )
    return fixtures


def asset_name(fixture):
    return f"{fixture['name']}.{fixture['sha256']}.{fixture['format']}.gz"


def page(url):
    while url:
        with request(url) as response:
            items = json.load(response)
            yield from items
            url = response.headers.get("Link", "")
            url = next(
                (
                    part[part.index("<") + 1 : part.index(">")]
                    for part in url.split(",")
                    if 'rel="next"' in part
                ),
                None,
            )


def find_assets(names):
    found = {}
    releases = page(f"{API_URL}/releases?per_page=100")
    for release in releases:
        for asset in page(f"{release['assets_url']}?per_page=100"):
            name = asset["name"]
            if name in names and name not in found:
                found[name] = {"url": asset["url"], "size": asset["size"]}
        if len(found) == len(names):
            break
    return found


def file_matches(fixture):
    path = fixture["path"]
    if not path.is_file() or path.stat().st_size != fixture["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == fixture["sha256"]


def install(fixture, url):
    target = fixture["path"]
    temporary = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with request(url, "application/octet-stream") as response, gzip.GzipFile(fileobj=response) as source, temporary.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                if size > fixture["size"]:
                    raise ValueError(f"oversized asset for {fixture['name']}")
        if size != fixture["size"] or digest.hexdigest() != fixture["sha256"]:
            raise ValueError(f"checksum mismatch for {fixture['name']}")
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main():
    args = arguments()
    started = time.monotonic()
    fixtures = load_fixtures()
    missing = [fixture for fixture in fixtures if not file_matches(fixture)]
    if not missing:
        print(f"All {len(fixtures)} fixtures are installed. Downloaded 0 MB; total time {time.monotonic() - started:.2f} s.")
        return
    if args.dry_run:
        for fixture in missing:
            print(f"{asset_name(fixture)} -> {fixture['path'].relative_to(ROOT)}")
        print(f"{len(missing)} fixtures would be installed.")
        return

    names = {asset_name(fixture) for fixture in missing}
    assets = find_assets(names)
    unavailable = sorted(names - assets.keys())
    if unavailable and not args.ignore_missing:
        raise RuntimeError("release assets not found:\n  " + "\n  ".join(unavailable))
    if unavailable:
        print("Release assets not found:", file=sys.stderr)
        for name in unavailable:
            print(f"  {name}", file=sys.stderr)
        missing = [fixture for fixture in missing if asset_name(fixture) in assets]

    downloaded = 0
    for index, fixture in enumerate(missing, 1):
        asset = assets[asset_name(fixture)]
        print(f"[{index}/{len(missing)}] {fixture['name']}", flush=True)
        file_started = time.monotonic()
        install(fixture, asset["url"])
        elapsed = time.monotonic() - file_started
        downloaded += asset["size"]
        print(
            f"  {asset['size']} bytes gzip ({asset['size'] / 1_000_000:.3f} MB), "
            f"{fixture['size']} bytes unpacked; download and verification {elapsed:.2f} s; "
            f"average {asset['size'] / 1_000_000 / elapsed if elapsed > 0 else 0:.3f} MB/s.",
            flush=True,
        )
    elapsed = time.monotonic() - started
    print(
        f"Installed {len(missing)} fixtures; skipped {len(unavailable)} missing assets. "
        f"Downloaded {downloaded / 1_000_000:.3f} MB; total time {elapsed:.2f} s; "
        f"average {downloaded / 1_000_000 / elapsed if elapsed > 0 else 0:.3f} MB/s."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"install.py: {error}", file=sys.stderr)
        raise SystemExit(1)
