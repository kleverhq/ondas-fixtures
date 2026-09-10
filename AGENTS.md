# Repository rules

This repository is the `kleverhq.ondas-fixtures` waveform provider. Use `README.md` for usage instructions and `catalog.json` for the provider name and version.

## Fixture format

- Put each fixture in a directory directly under the repository root. It must contain only `fixture.json` and `waveform.<format>`.
- Name directories `<format><NNNN>-<slug>`, for example `vcd0000-counter` or `fst0000-counter`. Use the lowercase artifact format, a zero-padded sequence number for that format, and the existing readable slug. Assign the next unused number. Never renumber fixtures or repeat the format at the end of the slug.
- Do not keep duplicate waveform content.
- Keep waveform files in the working tree, but never commit them. The root `.gitignore` allows only JSON files inside fixture directories.
- Do not change waveform bytes. Make sure `artifact.size` and `artifact.sha256` match the file.
- Keep descriptions short. Do not repeat IDs or values stored in other fields.
- Use tags for waveform semantics and test selection. Both `tags` and `oracle` may be empty.

## Sources and licenses

- Write repository content and commit messages in English.
- For imported GitHub files, use a permalink with the full 40-character commit SHA. Check that the linked file matches `artifact.sha256`.
- Mark generated waveforms as `authored`. Record the source project commit, simulation test, generator, and any format conversion.
- When both a source waveform and its derived waveform are present, link them in both sidecars.
- For files outside Git commits, record a stable source URL.
- Use a confirmed SPDX license identifier when available; otherwise use `"unknown"`. Store required license texts in `LICENSES/`.

## Delivery

- Name release assets `<fixture>.<sha256>.<format>.gz`. Each gzip stream must expand directly to the raw waveform bytes declared in `fixture.json`.
- Do not add delivery fields to fixture metadata. `install.py` derives asset names from the directory and artifact fields. It scans every fixture without filtering by tags.
- Pass an explicit list of fixture directories to `release.py`. Never publish all working-tree directories by default.
- Keep both scripts compatible with the Python standard library. `release.py` may use the GitHub CLI for authentication and upload.

## Checks

- Limit `README.md` to the corpus purpose, layout, and usage.
- Follow SemVer in `catalog.json`: patch for metadata fixes, minor for new fixtures, and major for incompatible contract changes.
- When bumping the version in `catalog.json`, tag that same commit as `v<version>` and push both the commit and the tag.
- Before finishing, validate the JSON files and directory layout. Check for duplicate hashes, verify artifact sizes and checksums, and check source links. Confirm that Git ignores the waveform files and that the metadata is in English.
