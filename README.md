# Ondas waveform fixtures

A collection of waveform fixtures for the [Ondas library](https://github.com/kleverhq/ondas). It provides convenient storage and a shared source of fixtures for tests, benchmarks, and other tools. The collection can be used for any waveform-related purpose.

Most waveforms were collected from public sources and retain their original licenses. Available source project license texts are in [LICENSES/](LICENSES/).

## Installation

The repository contains only metadata; waveforms are stored in [GitHub releases](https://github.com/kleverhq/ondas-fixtures/releases). With Python 3 and `just` installed, add the repository as a submodule and install the waveforms:

```sh
git submodule add https://github.com/kleverhq/ondas-fixtures.git fixtures
cd fixtures
just install
```

The parent repository pins the submodule commit. After cloning the parent, run `git submodule update --init fixtures` before installation. A standalone clone works too; run `just install` at its root.

The installer downloads waveforms into their fixture directories and verifies their sizes and SHA-256 checksums. It searches all releases by asset name and checksum, regardless of release tag. Repeated installation verifies and reuses matching local waveforms. Use `just install --dry-run` at the fixture repository root to list missing assets without downloading.

## Corpus

| Format | Fixtures | JSON (MB) | Waveforms (MB) | Total (MB) |
| --- | ---: | ---: | ---: | ---: |
| FSDB | 51 | 159 | 16 | 175 |
| FST | 88 | 106 | 1964 | 2070 |
| GHW | 93 | 0 | 140 | 140 |
| SHM | 66 | 29 | 8 | 37 |
| VCD | 99 | 26 | 1645 | 1671 |
| WLF | 70 | 134 | 47 | 181 |
| **Total** | **467** | **454** | **3820** | **4274** |

## Layout

```text
schemas/fixture.schema.json
<format>/
└── <format><NNNN>-<slug>/
    ├── fixture.json
    └── waveform.<format>
```

Fixtures are grouped by format. Each `fixture.json` records the waveform's format, size, SHA-256 checksum, source, license, tags, and optional test oracle. The shared [fixture schema](schemas/fixture.schema.json) includes the oracle definitions. The `schema: 1` markers identify the sidecar and oracle data contract.

## Development

See [AGENTS.md](AGENTS.md) for development instructions.
