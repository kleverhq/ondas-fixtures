import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from check import check_fixture
import install
from validate import ROOT, validated_documents


class ValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
        (self.root / "catalog.json").write_text(json.dumps(
            {"schema": 1, "provider": "kleverhq.ondas-fixtures", "version": "1.0.0"}
        ))
        self.directory = self.root / "vcd" / "vcd0000-test"
        self.directory.mkdir(parents=True)
        self.sidecar = self.directory / "fixture.json"
        self.payload = b"waveform bytes"
        self.data = {
            "schema": 1,
            "artifact": {"format": "vcd", "file": "waveform.vcd", "size": len(self.payload),
                         "sha256": hashlib.sha256(self.payload).hexdigest()},
            "provenance": {"kind": "authored", "license": "unknown"},
            "tags": [],
            "oracle": {},
        }
        self.write_sidecar(self.data)

    def write_sidecar(self, data):
        self.sidecar.write_text(json.dumps(data))

    def test_metadata_only_checkout_and_present_artifact_verification(self):
        self.data["provenance"]["transform"] = {"tool": "vcd2fst", "input_format": "vcd"}
        self.write_sidecar(self.data)
        self.assertEqual(len(list(validated_documents(self.root))), 5)
        names = {self.directory.name}
        self.assertFalse(check_fixture(self.sidecar, self.data, {}, names))
        waveform = self.directory / "waveform.vcd"
        waveform.write_bytes(self.payload)
        self.assertTrue(check_fixture(self.sidecar, self.data, {}, names))
        waveform.write_bytes(b"!" * len(self.payload))
        with self.assertRaisesRegex(ValueError, "size or checksum mismatch"):
            check_fixture(self.sidecar, self.data, {}, names)

    def test_catalog_errors_include_file_and_property(self):
        (self.root / "catalog.json").write_text(json.dumps(
            {"schema": 1, "provider": "kleverhq.ondas-fixtures", "version": 1}
        ))
        with self.assertRaisesRegex(ValueError, r"catalog.json: \$.version"):
            list(validated_documents(self.root))

    def test_catalog_version_follows_semver(self):
        valid = (
            "0.0.0", "6.0.0", "123.456.789", "6.0.0-alpha.1", "6.0.0-0",
            "6.0.0-01a", "6.0.0+001", "6.0.0-rc.1+build.001",
        )
        invalid = (
            "", "latest", "6.0", "v6.0.0", "06.0.0", "6.00.0", "6.0.00",
            "6.0.0-01", "6.0.0-alpha..1", "6.0.0+", "6.0.0\n", "6.\u0661.0",
        )
        for version in (*valid, *invalid):
            with self.subTest(version=version):
                (self.root / "catalog.json").write_text(json.dumps(
                    {"schema": 1, "provider": "kleverhq.ondas-fixtures", "version": version}
                ))
                if version in valid:
                    list(validated_documents(self.root))
                else:
                    with self.assertRaisesRegex(ValueError, r"catalog.json: \$.version"):
                        list(validated_documents(self.root))

    def test_schema_binds_artifact_filename_to_format(self):
        formats = ("fsdb", "fst", "ghw", "vcd", "wlf")
        for format in formats:
            data = copy.deepcopy(self.data)
            data["artifact"]["format"] = format
            data["artifact"]["file"] = f"waveform.{format}"
            self.write_sidecar(data)
            list(validated_documents(self.root))
            for extension in (*formats, "shm"):
                if extension == format:
                    continue
                with self.subTest(format=format, extension=extension):
                    data["artifact"]["file"] = f"waveform.{extension}"
                    self.write_sidecar(data)
                    with self.assertRaisesRegex(ValueError, r"artifact.file"):
                        list(validated_documents(self.root))

    def test_license_is_required_for_every_provenance_kind(self):
        for kind in ("authored", "imported", "converted"):
            with self.subTest(kind=kind):
                data = copy.deepcopy(self.data)
                data["provenance"].update(kind=kind, source="https://example.com/waveform.vcd")
                if kind == "converted":
                    data["provenance"]["transform"] = "vcd2fst"
                self.write_sidecar(data)
                list(validated_documents(self.root))
                del data["provenance"]["license"]
                self.write_sidecar(data)
                with self.assertRaisesRegex(ValueError, "license.*required"):
                    list(validated_documents(self.root))

    def test_fixture_schema_rejects_unknown_top_level_properties(self):
        data = copy.deepcopy(self.data)
        data["tag"] = data.pop("tags")
        self.write_sidecar(data)
        with self.assertRaisesRegex(ValueError, r"fixture.json: .*Additional properties.*tag"):
            list(validated_documents(self.root))

    def test_derived_relation_does_not_require_a_source_backlink(self):
        source = self.root / "vcd" / "vcd0001-source"
        source.mkdir()
        source_data = copy.deepcopy(self.data)
        source_payload = b"source waveform bytes"
        source_data["artifact"].update(
            size=len(source_payload), sha256=hashlib.sha256(source_payload).hexdigest(),
        )
        source_sidecar = source / "fixture.json"
        source_sidecar.write_text(json.dumps(source_data))
        data = copy.deepcopy(self.data)
        data["relations"] = [{"kind": "derived-from", "fixture": source.name}]
        self.write_sidecar(data)
        list(validated_documents(self.root))
        names = {self.directory.name, source.name}
        hashes = {}
        self.assertFalse(check_fixture(source_sidecar, source_data, hashes, names))
        self.assertFalse(check_fixture(self.sidecar, data, hashes, names))
        data["relations"][0]["fixture"] = "vcd9999-missing"
        with self.assertRaisesRegex(ValueError, "unknown related fixture"):
            check_fixture(self.sidecar, data, {}, names)

    def test_sidecar_schema_rejects_invalid_artifact_provenance_and_tags(self):
        cases = [
            ("artifact", {**self.data["artifact"], "size": "12"}, r"artifact.size"),
            ("artifact", {**self.data["artifact"], "sha256": "bad"}, r"artifact.sha256"),
            ("provenance", {"kind": "imported", "license": "unknown"}, r"source.*required"),
            ("tags", ["values", "values"], r"tags"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.data)
                data[field] = value
                self.write_sidecar(data)
                with self.assertRaisesRegex(ValueError, message):
                    list(validated_documents(self.root))

    def test_nested_oracle_is_validated_through_local_reference(self):
        data = copy.deepcopy(self.data)
        data["oracle"] = {
            "schema": 1, "open": {"result": "ok"},
            "signals": {"clock": {"encoding": {"kind": "bits", "width": 1},
                                  "samples": [{"time": "0", "value": {"bits": "2"}}]}},
        }
        self.write_sidecar(data)
        with self.assertRaisesRegex(ValueError, r"fixture.json: .*oracle.*bits"):
            list(validated_documents(self.root))

    def test_malformed_json_and_unassigned_json_files_fail(self):
        self.sidecar.write_text("{broken")
        with self.assertRaisesRegex(ValueError, "fixture.json: invalid JSON"):
            list(validated_documents(self.root))
        self.sidecar.write_text(json.dumps(self.data)[:-1] + ', "extra": NaN}')
        with self.assertRaisesRegex(ValueError, "non-standard JSON constant: NaN"):
            list(validated_documents(self.root))
        self.write_sidecar(self.data)
        (self.root / "extra.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "extra.json: no schema assigned"):
            list(validated_documents(self.root))

    def test_invalid_or_missing_schemas_fail(self):
        path = self.root / "schemas" / "catalog.schema.json"
        original = path.read_bytes()
        path.write_text(json.dumps({"type": "invalid"}))
        with self.assertRaisesRegex(ValueError, "catalog.schema.json: invalid schema"):
            list(validated_documents(self.root))
        path.write_bytes(original)
        (self.root / "schemas" / "oracle.schema.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing schemas: oracle.schema.json"):
            list(validated_documents(self.root))

    def test_duplicate_hash_and_unexpected_directory_contents_fail(self):
        duplicate = self.root / "vcd" / "vcd0001-duplicate"
        duplicate.mkdir()
        other = duplicate / "fixture.json"
        other.write_text(json.dumps(self.data))
        names = {self.directory.name, duplicate.name}
        hashes = {}
        check_fixture(self.sidecar, self.data, hashes, names)
        with self.assertRaisesRegex(ValueError, "duplicate artifact checksum"):
            check_fixture(other, self.data, hashes, names)
        (self.directory / "extra.txt").write_text("extra")
        with self.assertRaisesRegex(ValueError, "unexpected fixture directory contents"):
            check_fixture(self.sidecar, self.data, {}, names)

    def test_layout_must_match_the_declared_format(self):
        data = copy.deepcopy(self.data)
        data["artifact"]["file"] = "waveform.fst"
        with self.assertRaisesRegex(ValueError, "invalid fixture layout"):
            check_fixture(self.sidecar, data, {}, {self.directory.name})
        renamed = self.directory.with_name("fst0000-test")
        self.directory.rename(renamed)
        with self.assertRaisesRegex(ValueError, "invalid fixture layout"):
            check_fixture(renamed / "fixture.json", self.data, {}, {renamed.name})

    def test_shm_manifest_is_validated_without_component_files(self):
        directory = self.root / "shm" / "shm0000-test"
        directory.mkdir(parents=True)
        self.sidecar.rename(directory / "fixture.json")
        self.sidecar = directory / "fixture.json"
        data = copy.deepcopy(self.data)
        files = [{"file": "waves.dsn", "size": len(self.payload),
                  "sha256": hashlib.sha256(self.payload).hexdigest()}]
        data["artifact"] = {"format": "shm", "file": "waveform.shm", "files": files,
                            "size": len(self.payload), "sha256": install.directory_sha256(files)}
        self.write_sidecar(data)
        list(validated_documents(self.root))
        self.assertFalse(check_fixture(self.sidecar, data, {}, {directory.name}))
        data["artifact"]["file"] = "waveform.vcd"
        self.write_sidecar(data)
        with self.assertRaisesRegex(ValueError, r"artifact.file"):
            list(validated_documents(self.root))
        data["artifact"]["file"] = "waveform.shm"
        del data["artifact"]["files"]
        self.write_sidecar(data)
        with self.assertRaisesRegex(ValueError, "files.*required"):
            list(validated_documents(self.root))


if __name__ == "__main__":
    unittest.main()
