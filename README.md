# Ondas waveform fixtures

This repository contains waveforms for Ondas parser, conformance, and regression tests. It includes parser edge cases and output from simulation tools.

## Layout

```text
catalog.json
<format><NNNN>-<slug>/
├── fixture.json
└── waveform.<format>
```

`catalog.json` records the provider name and corpus version. Each fixture directory contains one waveform and a `fixture.json` sidecar that records its format, size, SHA-256 checksum, source, license, tags, and optional test oracle.

Git tracks the metadata needed to download and verify waveforms, but ignores the waveform files themselves.

## Installation

Clone the repository at `$ONDAS_FIXTURES/kleverhq.ondas-fixtures`, then install the waveforms:

```text
python3 install.py
```

The installer looks for matching gzip assets in the repository's releases. It checks each waveform's uncompressed size and SHA-256 checksum before saving it as `waveform.<format>`. It leaves existing files alone if they pass those checks.

For each downloaded file, the log shows the gzip asset size, unpacked size, and time spent downloading, unpacking, and verifying it. The final summary reports the total compressed MB downloaded (1 MB = 1,000,000 bytes) and elapsed installation time, including checks of existing files and release lookup. Both report average MB/s: compressed size divided by the corresponding elapsed time, including that processing time.

Use `--dry-run` to list missing assets without accessing GitHub. By default, the installer stops before downloading anything if a release asset is missing. With `--ignore-missing`, it installs the available assets and reports what it skipped. Set `GITHUB_TOKEN` when you need authenticated GitHub API access.

## Publishing assets

Release assets use the name `<fixture>.<sha256>.<format>.gz`. Each gzip stream contains the raw waveform, not a tar or zip archive.

Authenticate the GitHub CLI, then pass the fixture directories you want to publish:

```text
python3 release.py waveforms-2026-06-06 vcd0000-counter fst0000-counter
```

Use `--dry-run` to check the selected fixtures and print their asset names without creating a release.

Each waveform retains its source license. Available license texts are in `LICENSES/`. The value `unknown` means that no SPDX license identifier has been confirmed.
