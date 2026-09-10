import argparse
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install


class InstallTests(unittest.TestCase):
    def test_download_statistics_and_checksum_failure(self):
        payload = b"waveform data\n" * 100
        compressed = gzip.compress(payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "vcd0000-test"
            directory.mkdir()
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
