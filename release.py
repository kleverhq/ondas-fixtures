#!/usr/bin/env python3

import argparse
import gzip
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from install import REPOSITORY, asset_name, file_matches, load_fixtures

ROOT = Path(__file__).resolve().parent


def arguments():
    parser = argparse.ArgumentParser(description="Publish selected waveform fixtures as gzip release assets.")
    parser.add_argument("tag", help="GitHub release tag")
    parser.add_argument("fixtures", nargs="+", help="fixture directories to publish")
    parser.add_argument("--dry-run", action="store_true", help="validate and print assets without publishing")
    return parser.parse_args()


def selected_fixtures(names):
    fixtures = {}
    for fixture in load_fixtures():
        fixtures[fixture["name"]] = fixture
        fixtures[f"{fixture['format']}/{fixture['name']}"] = fixture
    unknown = sorted(set(names) - fixtures.keys())
    if unknown:
        raise ValueError("unknown fixture directories: " + ", ".join(unknown))
    selected = [fixtures[name] for name in names]
    if len(selected) != len({fixture["name"] for fixture in selected}):
        raise ValueError("fixture whitelist contains duplicates")
    invalid = [fixture["name"] for fixture in selected if not file_matches(fixture)]
    if invalid:
        raise ValueError("missing or invalid waveform files: " + ", ".join(invalid))
    return selected


def compress(fixture, directory):
    target = directory / asset_name(fixture)
    with target.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as archive:
            if fixture["format"] == "shm":
                with tarfile.open(fileobj=archive, mode="w|", format=tarfile.USTAR_FORMAT) as bundle:
                    for component in sorted(fixture["files"], key=lambda item: item["file"]):
                        member = tarfile.TarInfo(component["file"])
                        member.size = component["size"]
                        member.mode = 0o644
                        with (fixture["path"] / member.name).open("rb") as source:
                            bundle.addfile(member, source)
            else:
                with fixture["path"].open("rb") as source:
                    shutil.copyfileobj(source, archive, 1024 * 1024)
    return target


def release_exists(tag):
    return subprocess.run(
        ["gh", "release", "view", tag, "--repo", REPOSITORY],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def publish(tag, assets):
    if not release_exists(tag):
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                REPOSITORY,
                "--title",
                tag,
                "--notes",
                "Waveform fixture assets.",
            ],
            check=True,
        )
    subprocess.run(
        ["gh", "release", "upload", tag, *map(str, assets), "--repo", REPOSITORY, "--clobber"],
        check=True,
    )


def main():
    args = arguments()
    fixtures = selected_fixtures(args.fixtures)
    if args.dry_run:
        for fixture in fixtures:
            print(asset_name(fixture))
        return
    if shutil.which("gh") is None:
        raise RuntimeError("gh is required to publish a release")
    with tempfile.TemporaryDirectory(prefix="ondas-fixtures-release-") as temporary:
        assets = [compress(fixture, Path(temporary)) for fixture in fixtures]
        publish(args.tag, assets)
    print(f"Published {len(fixtures)} assets to {args.tag}.")


if __name__ == "__main__":
    main()
