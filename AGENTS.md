# Repository rules

This repository contains the Ondas waveform fixtures. Use `README.md` for usage instructions. Consumers pin a Git commit, typically through a submodule, rather than a separate corpus version.

## Commands

Use the root `justfile` for all repository operations. Do not invoke scripts directly. Run `just` to list commands.

| Command | Purpose |
| --- | --- |
| `just setup` | Create `.venv` and install validation dependencies. |
| `just install` | Download and verify waveform payloads. |
| `just install FORMAT/FIXTURE...` | Download and verify only the selected fixtures; bare directory names are also accepted. |
| `just install --dry-run` | List missing payloads without downloading. |
| `just validate` | Validate all repository JSON against the fixture schema. |
| `just check` | Validate metadata, layout, hashes, installed payloads, README statistics, and script tests. |
| `just test` | Run script tests. |
| `just stats` | Print the README corpus table. |
| `just release TAG FORMAT/FIXTURE... --target COMMIT` | Publish only the selected fixtures at a specific commit. |

Run `just setup` before validation, checks, or tests. `just check` also works without installed waveform payloads.

## Schemas

`schemas/fixture.schema.json` is the source of truth for fixture sidecars and the sparse oracle contract. Maintain this schema here; Ondas consumers must follow this contract. Its oracle definitions are available at `#/$defs/oracle`; their Apache-2.0 license text is in `LICENSES/Apache-2.0-ondas.txt`. Preserve the `schema: 1` markers in sidecars and nonempty oracles independently of commit pinning.

## Fixture format

- Put each fixture under `<format>/` at the repository root, using the lowercase artifact format. Each fixture directory must contain only `fixture.json` and `waveform.<format>`.
- For SHM, `waveform.shm` is a directory containing unchanged DSN/TRN components. Record each component's name, size, and SHA-256 in `artifact.files`; the artifact size is their sum. Hash the component list sorted by `file`, serialized as UTF-8 JSON with sorted keys, ASCII escapes, no whitespace, and no trailing newline, for the directory's `artifact.sha256`.
- Name directories `<format><NNNN>-<slug>`, for example `vcd0000-counter` or `fst0000-counter`. Use the lowercase artifact format, a zero-padded sequence number for that format, and the existing readable slug. Assign the next unused number. Never renumber fixtures or repeat the format at the end of the slug.
- Do not keep duplicate waveform content.
- Keep waveform files in the working tree, but never commit them. The root `.gitignore` allows only JSON files inside fixture directories.
- Do not change waveform bytes. Make sure `artifact.size` and `artifact.sha256` match the file.
- Keep descriptions short. Do not repeat IDs or values stored in other fields.
- Use tags for waveform semantics and test selection. Both `tags` and `oracle` may be empty.

## Sources and licenses

- Write repository content and commit messages in English.
- For imported GitHub files, use a permalink with the full 40-character commit SHA. Check that the linked file matches `artifact.sha256`.
- Generate fixtures authored from scratch in a neutral temporary workspace (for example, `/tmp/fixture-XXXXXX`), with neutral source, build, and output paths that reveal no project, user, host, or system identity. Check the resulting dump for embedded identifying paths before accepting it.
- Mark generated waveforms as `authored`. Record the source project commit, simulation test, generator, and any format conversion.
- For source/derived pairs in the corpus, record `derived-from` on the derived fixture. A reciprocal `source-of` relation is optional.
- For files outside Git commits, record a stable source URL.
- Use a confirmed SPDX license identifier when available; otherwise use `"unknown"`. Store required license texts in `LICENSES/`.

## Delivery format

- Name release assets `<fixture>.<sha256>.<format>.gz`. Each gzip stream must expand directly to the raw waveform bytes declared in `fixture.json`, or, for SHM directories, to a tar archive containing exactly the declared component files at its root.
- Do not add delivery fields to fixture metadata. `scripts/install.py` derives asset names from the directory and artifact fields. Without fixture arguments it installs every fixture; explicit directory names select a subset. It does not filter by tags.
- Keep `scripts/install.py` and `scripts/release.py` compatible with the Python standard library. Declare validation dependencies in `scripts/requirements.txt` and install them with `just setup`.

## Release

Publishing requires an authenticated GitHub CLI and valid local waveform payloads for the selected fixtures.

1. Run `just setup` and `just check`, then commit the changes without waveform payloads and push the commit.
2. For waveform uploads, use a tag named `files-<first 12 characters of the full commit SHA>`. Preview the explicit fixture list with `just release files-<short-sha> FORMAT/FIXTURE... --target <full-commit-sha> --dry-run`.
3. Publish the selected assets from a clean checkout of that commit with `just release files-<short-sha> FORMAT/FIXTURE... --target <full-commit-sha>`. The publisher resolves `--target` to a full SHA (default: `HEAD`) and requires it to match `HEAD`, with no tracked changes or untracked files; ignored waveform payloads are allowed. Dry runs enforce the same checkout requirements. It verifies any existing remote tag's commit and passes the SHA to `gh release create --target` to create an absent tag at that commit.
4. Never publish all working-tree directories by default. Metadata-only changes need only a pushed commit. Preserve existing tags, releases, and assets.

## Checks

- Limit `README.md` to the corpus purpose, layout, and usage.
- Update the corpus statistics in `README.md` whenever the corpus changes, including fixture additions, removals, and metadata updates. Run `just stats` and copy its output into the Corpus table. Round sizes to whole megabytes without thousands separators.
- Before finishing, validate the JSON files and directory layout. Check for duplicate hashes, verify artifact sizes and checksums, and check source links. Confirm that Git ignores the waveform files and that the metadata is in English.
