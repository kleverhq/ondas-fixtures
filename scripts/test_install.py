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
    def test_metadata_requests_accept_http_gzip_without_changing_asset_requests(self):
        with patch.object(install, "urlopen") as urlopen:
            install.request("https://example.com/releases")
            request = urlopen.call_args.args[0]
            self.assertEqual(request.get_header("Accept-encoding"), "gzip")
            install.request("https://example.com/asset", "application/octet-stream")
            request = urlopen.call_args.args[0]
            self.assertIsNone(request.get_header("Accept-encoding"))

    def test_metadata_pagination_reads_gzip_and_plain_responses(self):
        first = io.BytesIO(gzip.compress(json.dumps([{"name": "first"}]).encode()))
        first.headers = {"Content-Encoding": "gzip", "Link": '<https://example.com/page2>; rel="next"'}
        second = io.BytesIO(json.dumps([{"name": "second"}]).encode())
        second.headers = {}
        with patch.object(install, "request", side_effect=[first, second]) as request:
            self.assertEqual(list(install.page("https://example.com/page1")),
                             [{"name": "first"}, {"name": "second"}])
        self.assertEqual([call.args[0] for call in request.call_args_list],
                         ["https://example.com/page1", "https://example.com/page2"])

    def test_asset_lookup_searches_releases_without_version_or_tag_filtering(self):
        name = "vcd0000-test." + "a" * 64 + ".vcd.gz"
        releases = [
            {"tag_name": "files-0123456789ab", "assets_url": "https://example.com/new"},
            {"tag_name": "v6.0.0", "assets_url": "https://example.com/old"},
        ]
        asset = {"name": name, "url": "https://example.com/asset", "size": 42}
        with patch.object(install, "page", side_effect=[releases, [], [asset]]) as page:
            self.assertEqual(install.find_assets({name}), {name: {"url": asset["url"], "size": 42}})
        self.assertEqual(page.call_count, 3)
        self.assertEqual(page.call_args_list[-1].args, ("https://example.com/old?per_page=100",))

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
                loaded, = install.load_fixtures(["shm/shm0000-test"])
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
            args = argparse.Namespace(fixtures=[], dry_run=False, ignore_missing=False)
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

            repeated = io.StringIO()
            with patch.object(install, "ROOT", root), patch.object(install, "arguments", return_value=args), \
                 patch.object(install, "page") as page, patch.object(install, "request") as request, \
                 contextlib.redirect_stdout(repeated):
                install.main()
            page.assert_not_called()
            request.assert_not_called()
            self.assertIn("All 1 fixtures are installed. Downloaded 0 MB", repeated.getvalue())

            fixture = {**artifact, "name": directory.name, "path": directory / artifact["file"]}
            corrupt = b"!" * len(payload)
            with patch.object(install, "request", return_value=io.BytesIO(gzip.compress(corrupt))), \
                 self.assertRaisesRegex(ValueError, "checksum mismatch"):
                install.install(fixture, asset["url"])
            self.assertEqual(fixture["path"].read_bytes(), payload)
            self.assertFalse(fixture["path"].with_suffix(".vcd.part").exists())


class SelectiveInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fixture-install-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payloads = {}
        for format in ("vcd", "fst"):
            name = f"{format}0000-test"
            directory = self.root / format / name
            directory.mkdir(parents=True)
            payload = f"{format} waveform\n".encode()
            self.payloads[name] = payload
            artifact = {"file": f"waveform.{format}", "format": format,
                        "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            (directory / "fixture.json").write_text(json.dumps({"artifact": artifact, "tags": []}))
        patcher = patch.object(install, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_arguments_default_to_all_and_accept_flags_between_fixture_names(self):
        with patch("sys.argv", ["install.py"]):
            args = install.arguments()
            self.assertEqual(args.fixtures, [])
            self.assertFalse(args.dry_run)
            self.assertFalse(args.ignore_missing)
        for argv in (
            ["--dry-run", "--ignore-missing", "fst/fst0000-test", "vcd0000-test"],
            ["fst/fst0000-test", "--dry-run", "vcd0000-test", "--ignore-missing"],
            ["fst/fst0000-test", "vcd0000-test", "--dry-run", "--ignore-missing"],
        ):
            with self.subTest(argv=argv), patch("sys.argv", ["install.py", *argv]):
                args = install.arguments()
                self.assertEqual(args.fixtures, ["fst/fst0000-test", "vcd0000-test"])
                self.assertTrue(args.dry_run)
                self.assertTrue(args.ignore_missing)

    def test_selection_loads_only_requested_metadata_in_argument_order(self):
        ignored = self.root / "vcd" / "vcd0001-ignored"
        ignored.mkdir()
        (ignored / "fixture.json").write_text("invalid JSON")
        selected = install.load_fixtures(["vcd0000-test", "fst/fst0000-test"])
        self.assertEqual([item["name"] for item in selected], ["vcd0000-test", "fst0000-test"])
        self.assertEqual([item["format"] for item in selected], ["vcd", "fst"])
        with self.assertRaises(json.JSONDecodeError):
            install.load_fixtures()

    def test_invalid_selection_fails_before_payload_checks_or_network_access(self):
        cases = (
            (["vcd0000-test", "unknown"], "unknown fixture directories"),
            (["fst/vcd0000-test"], "unknown fixture directories"),
            (["../vcd/vcd0000-test"], "unknown fixture directories"),
            (["fst0000-test", "fst0000-test"], "duplicates"),
            (["fst0000-test", "fst/fst0000-test"], "duplicates"),
        )
        for names, message in cases:
            args = argparse.Namespace(fixtures=names, dry_run=False, ignore_missing=False)
            with self.subTest(names=names), \
                 patch.object(install, "arguments", return_value=args), \
                 patch.object(install, "file_matches") as file_matches, \
                 patch.object(install, "find_assets") as find_assets, \
                 patch.object(install, "request") as request:
                with self.assertRaisesRegex(ValueError, message):
                    install.main()
                file_matches.assert_not_called()
                find_assets.assert_not_called()
                request.assert_not_called()

    def test_dry_run_lists_selected_missing_payloads_and_defaults_to_all(self):
        for names, expected in ((["vcd0000-test"], ["vcd0000-test"]),
                                ([], ["fst0000-test", "vcd0000-test"])):
            args = argparse.Namespace(fixtures=names, dry_run=True, ignore_missing=False)
            output = io.StringIO()
            with self.subTest(names=names), \
                 patch.object(install, "arguments", return_value=args), \
                 patch.object(install, "find_assets") as find_assets, \
                 patch.object(install, "request") as request, \
                 contextlib.redirect_stdout(output):
                install.main()
            lines = output.getvalue().splitlines()
            self.assertEqual([line.split(".")[0] for line in lines[:-1]], expected)
            self.assertEqual(lines[-1], f"{len(expected)} fixtures would be installed.")
            find_assets.assert_not_called()
            request.assert_not_called()

    def test_partial_download_and_repeat_ignore_unselected_payloads(self):
        fixture, = install.load_fixtures(["fst0000-test"])
        other, = install.load_fixtures(["vcd0000-test"])
        other["path"].write_bytes(b"unrelated local data")
        compressed = gzip.compress(self.payloads[fixture["name"]])
        asset = {"url": "https://example.com/fixture.gz", "size": len(compressed)}
        args = argparse.Namespace(fixtures=["fst/fst0000-test"], dry_run=False, ignore_missing=False)
        with patch.object(install, "arguments", return_value=args), \
             patch.object(install, "find_assets", return_value={install.asset_name(fixture): asset}) as find_assets, \
             patch.object(install, "request", return_value=io.BytesIO(compressed)) as request, \
             patch.object(install, "file_matches", wraps=install.file_matches) as file_matches, \
             contextlib.redirect_stdout(io.StringIO()):
            install.main()
        find_assets.assert_called_once_with({install.asset_name(fixture)})
        request.assert_called_once_with(asset["url"], "application/octet-stream")
        self.assertEqual([call.args[0]["name"] for call in file_matches.call_args_list], [fixture["name"]])
        self.assertEqual(fixture["path"].read_bytes(), self.payloads[fixture["name"]])
        self.assertEqual(other["path"].read_bytes(), b"unrelated local data")
        with patch.object(install, "arguments", return_value=args), \
             patch.object(install, "find_assets") as find_assets, \
             patch.object(install, "request") as request, \
             contextlib.redirect_stdout(io.StringIO()):
            install.main()
        find_assets.assert_not_called()
        request.assert_not_called()

    def test_unavailable_selected_assets_respect_ignore_missing(self):
        fixture, = install.load_fixtures(["vcd0000-test"])
        for ignore_missing in (False, True):
            args = argparse.Namespace(fixtures=[fixture["name"]], dry_run=False,
                                      ignore_missing=ignore_missing)
            with self.subTest(ignore_missing=ignore_missing), \
                 patch.object(install, "arguments", return_value=args), \
                 patch.object(install, "find_assets", return_value={}) as find_assets, \
                 patch.object(install, "request") as request, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if ignore_missing:
                    install.main()
                else:
                    with self.assertRaisesRegex(RuntimeError, "release assets not found"):
                        install.main()
                find_assets.assert_called_once_with({install.asset_name(fixture)})
                request.assert_not_called()
                self.assertFalse(fixture["path"].exists())


if __name__ == "__main__":
    unittest.main()
