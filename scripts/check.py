#!/usr/bin/env python3

import contextlib
import io
import re
import subprocess
import sys

import install
import stats
from validate import ROOT, validated_documents


def check_fixture(sidecar, data, hashes, names):
    directory = sidecar.parent
    artifact = data["artifact"]
    format = artifact["format"]
    label = f"{format}/{directory.name}"
    if (directory.parent.name != format
            or not re.fullmatch(re.escape(format) + r"\d{4}-.+", directory.name)
            or sidecar.is_symlink()
            or artifact["file"] != f"waveform.{format}"):
        raise ValueError(f"{label}: invalid fixture layout")
    allowed = {"fixture.json", artifact["file"]}
    if not {item.name for item in directory.iterdir()} <= allowed:
        raise ValueError(f"{label}: unexpected fixture directory contents")
    digest = artifact["sha256"]
    if digest in hashes:
        raise ValueError(f"{label}: duplicate artifact checksum with {hashes[digest]}")
    hashes[digest] = label
    if format == "shm":
        install.validate_components(artifact)
    for relation in data.get("relations", []):
        if relation["fixture"] not in names:
            raise ValueError(f"{label}: unknown related fixture {relation['fixture']}")
    path = directory / artifact["file"]
    present = path.exists() or path.is_symlink()
    if present and not install.file_matches({**artifact, "name": directory.name, "path": path}):
        raise ValueError(f"{label}: waveform size or checksum mismatch")
    return present


def check_git_payloads(root, payloads):
    paths = {str(path.relative_to(root)) for path in payloads}
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"], cwd=root,
        input="\n".join(sorted(paths)) + "\n", text=True, capture_output=True,
    )
    if ignored.returncode != 0 or set(ignored.stdout.splitlines()) != paths:
        raise ValueError("waveform payloads must be ignored by Git")
    tracked = subprocess.run(["git", "ls-files"], cwd=root, text=True, capture_output=True, check=True)
    if any("/waveform." in path for path in tracked.stdout.splitlines()):
        raise ValueError("waveform payloads must not be tracked by Git")


def main():
    hashes = {}
    names = {path.parent.name for path in ROOT.glob("*/*/fixture.json")}
    if not names:
        raise ValueError("no fixtures found")
    count = 0
    installed = 0
    payloads = []
    for path, data in validated_documents():
        count += 1
        if path.name == "fixture.json":
            installed += check_fixture(path, data, hashes, names)
            payloads.append(path.parent / data["artifact"]["file"])
    check_git_payloads(ROOT, payloads)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        stats.main()
    if output.getvalue().strip() not in (ROOT / "README.md").read_text():
        raise ValueError("README corpus statistics are stale; update them with just stats")
    print(f"Validated {count} JSON files and {len(hashes)} fixtures; verified {installed} installed artifacts.", flush=True)
    subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(ROOT / "scripts"), "-p", "test_*.py"],
        check=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"check.py: {error}", file=sys.stderr)
        raise SystemExit(1)
