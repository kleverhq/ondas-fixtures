# Ondas waveform fixtures

This repository contains waveform fixtures for Ondas parser, conformance, and regression tests. The corpus includes parser edge cases and files produced by real simulation tools.

## Layout

```text
catalog.json
<format><NNNN>-<slug>/
├── fixture.json
└── waveform.<format>
```

`catalog.json` stores the provider name and corpus version. Each fixture directory contains one waveform and a `fixture.json` sidecar with its format, size, SHA-256 checksum, source, license, tags, and optional test oracle.

## Installation

Clone the repository at `$ONDAS_FIXTURES/kleverhq.ondas-fixtures`, then materialize every fixture:

```text
python3 install.py
```

The installer finds the matching gzip assets across the repository releases, verifies the uncompressed size and SHA-256 checksum, and writes each `waveform.<format>` file. Existing valid files are left untouched. Use `--dry-run` to list missing assets without accessing GitHub. By default, a missing release asset stops the installation before any download; `--ignore-missing` installs the available assets and reports those skipped. Set `GITHUB_TOKEN` if authenticated GitHub API access is needed.

Waveform payloads are ignored by Git. Git tracks the metadata needed to download and verify them.

## Publishing assets

A release asset is named `<fixture>.<sha256>.<format>.gz`. The gzip stream contains the raw waveform, not a tar or zip archive.

Publish an explicit whitelist of fixture directories with an authenticated GitHub CLI:

```text
python3 release.py waveforms-2026-06-06 vcd0000-counter fst0000-counter
```

Use `--dry-run` to validate the selected fixtures and print their asset names without creating a release.

The source license still applies to each waveform. License texts are stored in `LICENSES/` when available. A license value of `unknown` means that no confirmed SPDX license was found.
