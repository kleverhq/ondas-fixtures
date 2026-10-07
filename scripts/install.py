#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import time
from urllib.request import Request, urlopen

REPOSITORY = "kleverhq/ondas-fixtures"
API_URL = f"https://api.github.com/repos/{REPOSITORY}"
ROOT = Path(__file__).resolve().parent.parent
SHA256 = re.compile(r"[0-9a-f]{64}")


def directory_sha256(files):
    manifest = json.dumps(sorted(files, key=lambda item: item["file"]),
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def validate_components(artifact):
    files = artifact["files"]
    names = set()
    if not isinstance(files, list) or not files:
        raise ValueError("empty SHM component manifest")
    for component in files:
        name = component["file"]
        if (set(component) != {"file", "size", "sha256"}
                or not isinstance(name, str) or Path(name).name != name
                or "\\" in name or name in {".", ".."} or name in names
                or Path(name).suffix not in {".dsn", ".trn"}
                or type(component["size"]) is not int or component["size"] <= 0
                or not SHA256.fullmatch(component["sha256"])):
            raise ValueError("invalid SHM component manifest")
        names.add(name)
    if (sum(item["size"] for item in files) != artifact["size"]
            or directory_sha256(files) != artifact["sha256"]):
        raise ValueError("SHM directory checksum mismatch")


def arguments():
    parser = argparse.ArgumentParser(description="Install waveform fixtures from GitHub release assets.")
    parser.add_argument(
        "fixtures", nargs="*", metavar="FIXTURE",
        help="fixture names or FORMAT/FIXTURE directories to install (default: all fixtures)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print missing assets without downloading")
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="install available assets when some expected assets are absent",
    )
    return parser.parse_intermixed_args()


def request(url, accept="application/vnd.github+json"):
    headers = {
        "Accept": accept,
        "User-Agent": "ondas-fixtures-installer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if accept == "application/vnd.github+json":
        headers["Accept-Encoding"] = "gzip"
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return urlopen(Request(url, headers=headers), timeout=60)


def load_fixtures(names=()):
    sidecars = sorted(ROOT.glob("*/*/fixture.json"))
    if names:
        directories = {}
        for sidecar in sidecars:
            directories[sidecar.parent.name] = sidecar
            directories[sidecar.parent.relative_to(ROOT).as_posix()] = sidecar
        unknown = sorted(set(names) - directories.keys())
        if unknown:
            raise ValueError("unknown fixture directories: " + ", ".join(unknown))
        sidecars = [directories[name] for name in names]
        if len(sidecars) != len(set(sidecars)):
            raise ValueError("fixture selection contains duplicates")
    fixtures = []
    for sidecar in sidecars:
        data = json.loads(sidecar.read_text())
        artifact = data["artifact"]
        if sidecar.parent.parent.name != artifact["format"]:
            raise ValueError(f"format directory mismatch in {sidecar}")
        filename = artifact["file"]
        digest = artifact["sha256"]
        if Path(filename).name != filename or not SHA256.fullmatch(digest):
            raise ValueError(f"invalid artifact metadata in {sidecar}")
        if artifact["format"] == "shm":
            if filename != "waveform.shm":
                raise ValueError(f"invalid SHM artifact name in {sidecar}")
            validate_components(artifact)
        fixtures.append(
            {
                "name": sidecar.parent.name,
                "path": sidecar.parent / filename,
                "format": artifact["format"],
                "size": artifact["size"],
                "sha256": digest,
                **({"files": artifact["files"]} if artifact["format"] == "shm" else {}),
            }
        )
    return fixtures


def asset_name(fixture):
    return f"{fixture['name']}.{fixture['sha256']}.{fixture['format']}.gz"


def page(url):
    while url:
        with request(url) as response:
            if response.headers.get("Content-Encoding") == "gzip":
                with gzip.GzipFile(fileobj=response) as content:
                    items = json.load(content)
            else:
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
    if fixture["format"] == "shm":
        if not path.is_dir() or path.is_symlink():
            return False
        if {item.name for item in path.iterdir()} != {item["file"] for item in fixture["files"]}:
            return False
        return all(file_matches({**item, "path": path / item["file"], "format": "component"})
                   for item in fixture["files"])
    if path.is_symlink():
        return False
    if not path.is_file() or path.stat().st_size != fixture["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == fixture["sha256"]


def install_directory(fixture, source):
    target = fixture["path"]
    expected = {item["file"]: item for item in fixture["files"]}
    with tempfile.TemporaryDirectory(prefix=".waveform-shm-", dir=target.parent) as work:
        work = Path(work)
        directory = work / "new"
        directory.mkdir()
        seen = set()
        with tarfile.open(fileobj=source, mode="r|") as archive:
            for member in archive:
                if (member.name not in expected or member.name in seen or not member.isfile()
                        or member.size != expected[member.name]["size"]):
                    raise ValueError(f"invalid SHM archive member: {member.name}")
                seen.add(member.name)
                digest = hashlib.sha256()
                size = 0
                with archive.extractfile(member) as stream, (directory / member.name).open("wb") as output:
                    while chunk := stream.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                component = expected[member.name]
                if size != component["size"] or digest.hexdigest() != component["sha256"]:
                    raise ValueError(f"checksum mismatch for {fixture['name']}/{member.name}")
        # Read through the gzip trailer so truncated/corrupt streams cannot be accepted.
        while source.read(1024 * 1024):
            pass
        if seen != expected.keys():
            raise ValueError(f"missing SHM archive components for {fixture['name']}")
        backup = work / "old"
        if target.exists() or target.is_symlink():
            os.replace(target, backup)
        try:
            os.replace(directory, target)
        except Exception:
            if backup.exists() or backup.is_symlink():
                os.replace(backup, target)
            raise


def install(fixture, url):
    if fixture["format"] == "shm":
        with request(url, "application/octet-stream") as response, gzip.GzipFile(fileobj=response) as source:
            install_directory(fixture, source)
        return
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
    fixtures = load_fixtures(args.fixtures)
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
