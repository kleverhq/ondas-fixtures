#!/usr/bin/env python3

from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def row(label, count, metadata, waveforms, bold=False):
    cells = [label, str(count), f"{metadata / 1_000_000:.0f}",
             f"{waveforms / 1_000_000:.0f}", f"{(metadata + waveforms) / 1_000_000:.0f}"]
    if bold:
        cells = [f"**{cell}**" for cell in cells]
    return "| " + " | ".join(cells) + " |"


def main():
    counts = Counter()
    metadata = Counter()
    waveforms = Counter()
    for sidecar in ROOT.glob("*/*/fixture.json"):
        artifact = json.loads(sidecar.read_bytes())["artifact"]
        format = artifact["format"]
        counts[format] += 1
        metadata[format] += sidecar.stat().st_size
        waveforms[format] += artifact["size"]

    print("| Format | Fixtures | JSON (MB) | Waveforms (MB) | Total (MB) |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for format in sorted(counts):
        print(row(format.upper(), counts[format], metadata[format], waveforms[format]))
    print(row("Total", sum(counts.values()),
              sum(metadata.values()) + (ROOT / "catalog.json").stat().st_size,
              sum(waveforms.values()), bold=True))


if __name__ == "__main__":
    main()
