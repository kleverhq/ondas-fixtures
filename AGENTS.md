# Repository rules

This repository is the `kleverhq.ondas-fixtures` waveform provider. `README.md` explains how to use it. `catalog.json` stores the provider name and version.

## Fixture format

- Each fixture must be an immediate child directory containing only `fixture.json` and `waveform.<format>`.
- Name fixture directories `<format><NNNN>-<slug>`, using the lowercase artifact format, a zero-padded per-format sequence, and the existing readable slug, for example `vcd0000-counter` or `fst0000-counter`. Assign the next unused number, never renumber existing fixtures, and do not repeat the artifact format at the end of the slug.
- Do not keep duplicate waveform content.
- Keep waveform payloads in the working tree, but never commit them. The root `.gitignore` allows only JSON files inside fixture directories.
- Do not modify waveform bytes. Keep `artifact.size` and `artifact.sha256` in sync with the file.
- Descriptions should be short and must not repeat IDs or values already stored in other fields.
- Tags are for waveform semantics and test selection. `tags` and `oracle` may be empty.

## Sources and licenses

- Write repository content and commit messages in English.
- Link imported GitHub files using a permalink with the full 40-character commit SHA. Confirm that the linked file matches `artifact.sha256`.
- Record generated waveforms as `authored`. Include the source project commit, simulation test, generator, and any format conversion.
- Link related source and derived fixtures in both sidecars when both payloads are present.
- For files outside Git commits, record a stable source URL.
- Use a confirmed SPDX license identifier when one is known. Otherwise, use `"unknown"`. Store required license texts in `LICENSES/`.

## Delivery

- Name release assets `<fixture>.<sha256>.<format>.gz`. Each gzip stream must expand directly to the raw waveform bytes declared by `fixture.json`.
- Do not add delivery fields to fixture metadata. `install.py` derives asset names from the directory and artifact fields, scans every fixture, and does not filter by tags.
- Use `release.py` with an explicit fixture-directory whitelist. Never publish every working-tree directory implicitly.
- Keep both scripts compatible with the Python standard library. `release.py` may call the GitHub CLI for authentication and upload.

## Checks

- Keep `README.md` limited to the corpus purpose, layout, and usage.
- Follow SemVer in `catalog.json`: patch for metadata fixes, minor for new fixtures, and major for incompatible contract changes.
- Before finishing, check the JSON files, directory layout, duplicate hashes, artifact sizes and checksums, source links, ignored payloads, and language of the metadata.
