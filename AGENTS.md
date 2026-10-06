# Repository rules

This repository is the `kleverhq.ondas-fixtures` waveform provider. Use `README.md` for usage instructions and `catalog.json` for the provider name and version.

## Commands

Use the root `justfile` for all repository operations. Do not invoke scripts directly. Run `just` to list commands.

| Command | Purpose |
| --- | --- |
| `just setup` | Create `.venv` and install validation dependencies. |
| `just install` | Download and verify waveform payloads. |
| `just install --dry-run` | List missing payloads without downloading. |
| `just validate` | Validate all repository JSON against local schemas. |
| `just check` | Validate metadata, layout, hashes, installed payloads, README statistics, and script tests. |
| `just test` | Run script tests. |
| `just stats` | Print the README corpus table. |
| `just release TAG FORMAT/FIXTURE...` | Publish only the selected fixtures. |

Run `just setup` before validation, checks, or tests. `just check` also works without installed waveform payloads.

## Schemas

`schemas/` is the source of truth for the catalog, fixture sidecars, and sparse oracle contract. Maintain the schemas here; Ondas consumers must follow this contract. The oracle schema's Apache-2.0 license text is in `LICENSES/Apache-2.0-ondas.txt`.

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
- When both a source waveform and its derived waveform are present, link them in both sidecars.
- For files outside Git commits, record a stable source URL.
- Use a confirmed SPDX license identifier when available; otherwise use `"unknown"`. Store required license texts in `LICENSES/`.

## Delivery format

- Name release assets `<fixture>.<sha256>.<format>.gz`. Each gzip stream must expand directly to the raw waveform bytes declared in `fixture.json`, or, for SHM directories, to a tar archive containing exactly the declared component files at its root.
- Do not add delivery fields to fixture metadata. `scripts/install.py` derives asset names from the directory and artifact fields. It scans every fixture without filtering by tags.
- Keep `scripts/install.py` and `scripts/release.py` compatible with the Python standard library. Declare validation dependencies in `scripts/requirements.txt` and install them with `just setup`.

## Release

Publishing requires an authenticated GitHub CLI and valid local waveform payloads for the selected fixtures.

1. Bump `catalog.json` following SemVer: patch for metadata fixes, minor for new fixtures, major for incompatible contract changes.
2. Run `just check`. For waveform uploads, preview the explicit fixture list with `just release v<version> FORMAT/FIXTURE... --dry-run`.
3. Commit the changes without waveform payloads, tag that same commit as `v<version>`, and push both the commit and the tag.
4. Publish the selected assets with `just release v<version> FORMAT/FIXTURE...`. Never publish all working-tree directories by default. Skip uploads for metadata-only releases.

## Checks

- Limit `README.md` to the corpus purpose, layout, and usage.
- Update the corpus statistics in `README.md` whenever the corpus changes, including fixture additions, removals, and metadata updates. Run `just stats` and copy its output into the Corpus table. Round sizes to whole megabytes without thousands separators.
- Before finishing, validate the JSON files and directory layout. Check for duplicate hashes, verify artifact sizes and checksums, and check source links. Confirm that Git ignores the waveform files and that the metadata is in English.
