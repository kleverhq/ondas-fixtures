import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from jsonschema import Draft202012Validator

from check import check_fixture
import install
from validate import ROOT, read_json, validated_documents


class ValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
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
        self.assertEqual(len(list(validated_documents(self.root))), 2)
        names = {self.directory.name}
        self.assertFalse(check_fixture(self.sidecar, self.data, {}, names))
        waveform = self.directory / "waveform.vcd"
        waveform.write_bytes(self.payload)
        self.assertTrue(check_fixture(self.sidecar, self.data, {}, names))
        waveform.write_bytes(b"!" * len(self.payload))
        with self.assertRaisesRegex(ValueError, "size or checksum mismatch"):
            check_fixture(self.sidecar, self.data, {}, names)

    def test_sidecar_and_oracle_schema_markers_remain_required(self):
        for value in (None, 2):
            with self.subTest(sidecar_schema=value):
                data = copy.deepcopy(self.data)
                if value is None:
                    del data["schema"]
                else:
                    data["schema"] = value
                self.write_sidecar(data)
                with self.assertRaisesRegex(ValueError, r"fixture.json: .*schema"):
                    list(validated_documents(self.root))
            with self.subTest(oracle_schema=value):
                data = copy.deepcopy(self.data)
                data["oracle"] = {"open": {"result": "ok"}}
                if value is not None:
                    data["oracle"]["schema"] = value
                self.write_sidecar(data)
                with self.assertRaisesRegex(ValueError, r"fixture.json: .*oracle"):
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

    def test_nested_oracle_is_validated_through_embedded_reference(self):
        data = copy.deepcopy(self.data)
        data["oracle"] = {
            "schema": 1, "open": {"result": "ok"},
            "signals": {"clock": {"encoding": {"kind": "bits", "width": 1},
                                  "samples": [{"time": "0", "value": {"bits": "2"}}]}},
        }
        self.write_sidecar(data)
        with self.assertRaisesRegex(ValueError, r"fixture.json: .*oracle.*bits"):
            list(validated_documents(self.root))

    def test_oracle_definition_is_usable_from_the_single_schema(self):
        schema = read_json(self.root / "schemas" / "fixture.schema.json")
        validator = Draft202012Validator(schema).evolve(schema={"$ref": "#/$defs/oracle"})
        cases = (
            ({}, True),
            ({"schema": 1, "open": {"result": "ok"}}, True),
            ({"schema": 1, "open": {"result": "error", "kind": "malformed"}}, True),
            ({"schema": 1, "open": {"result": "error", "kind": "malformed"}, "signals": {}}, False),
            ({"open": {"result": "ok"}}, False),
            ({"schema": 2, "open": {"result": "ok"}}, False),
        )
        for oracle, valid in cases:
            with self.subTest(oracle=oracle):
                self.assertEqual(validator.is_valid(oracle), valid)

    def test_embedded_oracle_preserves_sample_and_window_constraints(self):
        cases = (
            ({"time": "0", "value": {"bits": "01xz"}, "changed_at": None}, True),
            ({"time": "0", "value": {"real_bits": "3ff0000000000000"}}, True),
            ({"time": "0", "value": {"string": "value"}}, True),
            ({"time": "0", "value": {"event": True}}, True),
            ({"time": "0", "missing": True}, True),
            ({"time": "0", "occurrences": "2"}, True),
            ({"time": "0", "error": {"kind": "unsupported-signal"}}, True),
            ({"time": "00", "missing": True}, False),
            ({"time": "0", "value": {"real_bits": "bad"}}, False),
            ({"time": "0", "missing": True, "changed_at": "0"}, False),
            ({"time": "0", "value": {"bits": "1"}, "occurrences": "1"}, False),
        )
        for sample, valid in cases:
            with self.subTest(sample=sample):
                data = copy.deepcopy(self.data)
                data["oracle"] = {
                    "schema": 1, "open": {"result": "ok"},
                    "signals": {"signal": {"encoding": {"kind": "bits", "width": 1},
                                           "samples": [sample]}},
                }
                self.write_sidecar(data)
                if valid:
                    list(validated_documents(self.root))
                else:
                    with self.assertRaises(ValueError):
                        list(validated_documents(self.root))
        for window, valid in (
            ({"start": "0", "end": "1", "initial": None, "changes": []}, True),
            ({"start": "0", "end": "1", "error": {"kind": "malformed"}}, True),
            ({"start": "0", "end": "1", "initial": None}, False),
            ({"start": "0", "end": "1", "initial": None, "changes": [],
              "error": {"kind": "malformed"}}, False),
        ):
            with self.subTest(window=window):
                data["oracle"]["signals"]["signal"].pop("samples", None)
                data["oracle"]["signals"]["signal"]["windows"] = [window]
                self.write_sidecar(data)
                if valid:
                    list(validated_documents(self.root))
                else:
                    with self.assertRaises(ValueError):
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
        path = self.root / "schemas" / "fixture.schema.json"
        original = path.read_bytes()
        path.write_text(json.dumps({"type": "invalid"}))
        with self.assertRaisesRegex(ValueError, "fixture.schema.json: invalid schema"):
            list(validated_documents(self.root))
        path.write_bytes(original)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing schema: fixture.schema.json"):
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
