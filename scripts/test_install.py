import argparse
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

import install
import release


class InstallTests(unittest.TestCase):
    def test_format_directories_and_release_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = {}
            for format in ("vcd", "fst"):
                name = f"{format}0000-test"
                directory = root / format / name
                directory.mkdir(parents=True)
                payload = f"{format} waveform".encode()
                artifact = {"file": f"waveform.{format}", "format": format,
                            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
                (directory / artifact["file"]).write_bytes(payload)
                (directory / "fixture.json").write_text(json.dumps({"artifact": artifact, "tags": []}))
                expected[name] = directory / artifact["file"]
            with patch.object(install, "ROOT", root):
                loaded = install.load_fixtures()
                self.assertEqual({item["name"]: item["path"] for item in loaded}, expected)
                selected = release.selected_fixtures(["vcd/vcd0000-test", "fst0000-test"])
                self.assertEqual([item["name"] for item in selected], ["vcd0000-test", "fst0000-test"])
                for fixture in selected:
                    self.assertEqual(install.asset_name(fixture),
                                     f"{fixture['name']}.{fixture['sha256']}.{fixture['format']}.gz")
                with self.assertRaisesRegex(ValueError, "duplicates"):
                    release.selected_fixtures(["vcd0000-test", "vcd/vcd0000-test"])
                with self.assertRaisesRegex(ValueError, "unknown fixture directories"):
                    release.selected_fixtures(["fst/vcd0000-test"])
                (root / "vcd" / "vcd0000-test").rename(root / "fst" / "vcd0000-test")
                with self.assertRaisesRegex(ValueError, "format directory mismatch"):
                    install.load_fixtures()

    def directory_fixture(self, root):
        payloads = {"waves.dsn": b"design bytes", "waves.trn": b"transaction bytes",
                    "waves-1.trn": b"continued transactions"}
        directory = root / "waveform.shm"
        directory.mkdir()
        files = []
        for name, payload in payloads.items():
            (directory / name).write_bytes(payload)
            files.append({"file": name, "size": len(payload),
                          "sha256": hashlib.sha256(payload).hexdigest()})
        return {"name": "shm0000-test", "path": directory, "file": directory.name,
                "format": "shm", "size": sum(item["size"] for item in files),
                "sha256": install.directory_sha256(files), "files": files}, payloads

    def tar_asset(self, members):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            for name, payload, kind in members:
                member = tarfile.TarInfo(name)
                member.type = kind
                if kind == tarfile.REGTYPE:
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
                else:
                    member.linkname = "../outside"
                    archive.addfile(member)
        return gzip.compress(output.getvalue())

    def test_directory_round_trip_and_content_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "shm" / "shm0000-test"
            root.mkdir(parents=True)
            fixture, payloads = self.directory_fixture(root)
            sidecar = {"artifact": {key: value for key, value in fixture.items()
                                    if key not in {"name", "path"}}}
            (root / "fixture.json").write_text(json.dumps(sidecar))
            with patch.object(install, "ROOT", root.parent.parent):
                loaded = next(item for item in install.load_fixtures() if item["path"] == fixture["path"])
            self.assertEqual(loaded["files"], fixture["files"])
            self.assertTrue(install.file_matches(loaded))
            compressed = release.compress(fixture, root).read_bytes()
            self.assertEqual(compressed, release.compress(fixture, root).read_bytes())
            with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:gz") as archive:
                self.assertEqual(archive.getnames(), sorted(payloads))
                for member in archive:
                    self.assertEqual(archive.extractfile(member).read(), payloads[member.name])
                    self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))
            (fixture["path"] / "waves.trn").write_bytes(b"broken")
            self.assertFalse(install.file_matches(fixture))
            with patch.object(install, "request", return_value=io.BytesIO(compressed)):
                install.install(fixture, "https://example.com/shm.gz")
            self.assertTrue(install.file_matches(fixture))
            (fixture["path"] / "extra.trn").write_bytes(b"extra")
            self.assertFalse(install.file_matches(fixture))
            (fixture["path"] / "extra.trn").unlink()
            (fixture["path"] / "waves.trn").unlink()
            (fixture["path"] / "waves.trn").symlink_to(fixture["path"] / "waves-1.trn")
            self.assertFalse(install.file_matches(fixture))

    def test_directory_rejects_invalid_archives_and_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, payloads = self.directory_fixture(root)
            good = [(name, payload, tarfile.REGTYPE) for name, payload in payloads.items()]
            corrupt = [(name, b"!" * len(payload), tarfile.REGTYPE) for name, payload in payloads.items()]
            archives = {
                "corrupt": self.tar_asset(corrupt),
                "missing": self.tar_asset(good[:-1]),
                "duplicate": self.tar_asset(good + good[:1]),
                "unexpected": self.tar_asset(good + [("extra.trn", b"!", tarfile.REGTYPE)]),
                "traversal": self.tar_asset([("../outside", b"!", tarfile.REGTYPE)]),
                "symlink": self.tar_asset([("waves.dsn", b"", tarfile.SYMTYPE)]),
                "hardlink": self.tar_asset([("waves.dsn", b"", tarfile.LNKTYPE)]),
                "wrong-size": self.tar_asset([("waves.dsn", b"!", tarfile.REGTYPE)]),
                "truncated": self.tar_asset(good)[:-4],
            }
            for label, compressed in archives.items():
                with self.subTest(label=label):
                    with patch.object(install, "request", return_value=io.BytesIO(compressed)), \
                         self.assertRaises((ValueError, EOFError, tarfile.TarError)):
                        install.install(fixture, "https://example.com/shm.gz")
                    self.assertTrue(install.file_matches(fixture))
                    self.assertEqual(sorted(item.name for item in root.iterdir()), ["waveform.shm"])

    def test_directory_manifest_rejects_unsafe_names_and_inconsistent_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture, _ = self.directory_fixture(Path(temporary))
            install.validate_components(fixture)
            self.assertEqual(install.directory_sha256(fixture["files"]),
                             install.directory_sha256(list(reversed(fixture["files"]))))
            with self.assertRaisesRegex(ValueError, "directory checksum"):
                install.validate_components({**fixture, "sha256": "0" * 64})
            for name in ["../waves.dsn", "/waves.dsn", "..", "waves\\bad.dsn"]:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "component manifest"):
                    files = [{**fixture["files"][0], "file": name}]
                    install.validate_components({**fixture, "files": files})

    def test_download_statistics_and_checksum_failure(self):
        payload = b"waveform data\n" * 100
        compressed = gzip.compress(payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "vcd" / "vcd0000-test"
            directory.mkdir(parents=True)
            artifact = {"file": "waveform.vcd", "format": "vcd", "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()}
            (directory / "fixture.json").write_text(json.dumps({"artifact": artifact}))
            name = f"{directory.name}.{artifact['sha256']}.vcd.gz"
            asset = {"name": name, "url": "https://api.github.com/repos/example/fixtures/releases/assets/1",
                     "size": len(compressed)}
            args = argparse.Namespace(dry_run=False, ignore_missing=False)
            output = io.StringIO()
            with patch.object(install, "ROOT", root), patch.object(install, "arguments", return_value=args), \
                 patch.object(install, "page", side_effect=[[{"assets_url": "https://api.github.com/assets"}], [asset]]), \
                 patch.object(install, "request", return_value=io.BytesIO(compressed)) as request, \
                 patch.object(install.time, "monotonic", side_effect=[10, 12, 15, 17]), \
                 contextlib.redirect_stdout(output):
                install.main()
            request.assert_called_once_with(asset["url"], "application/octet-stream")
            self.assertEqual((directory / artifact["file"]).read_bytes(), payload)
            self.assertIn(f"{len(compressed)} bytes gzip", output.getvalue())
            self.assertIn(f"{len(payload)} bytes unpacked", output.getvalue())
            self.assertIn(
                f"download and verification 3.00 s; average {len(compressed) / 1_000_000 / 3:.3f} MB/s",
                output.getvalue(),
            )
            self.assertIn(
                f"Downloaded {len(compressed) / 1_000_000:.3f} MB; total time 7.00 s; "
                f"average {len(compressed) / 1_000_000 / 7:.3f} MB/s",
                output.getvalue(),
            )

            fixture = {**artifact, "name": directory.name, "path": directory / artifact["file"]}
            corrupt = b"!" * len(payload)
            with patch.object(install, "request", return_value=io.BytesIO(gzip.compress(corrupt))), \
                 self.assertRaisesRegex(ValueError, "checksum mismatch"):
                install.install(fixture, asset["url"])
            self.assertEqual(fixture["path"].read_bytes(), payload)
            self.assertFalse(fixture["path"].with_suffix(".vcd.part").exists())


if __name__ == "__main__":
    unittest.main()
