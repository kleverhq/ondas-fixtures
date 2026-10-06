import argparse
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import release


class ReleaseTests(unittest.TestCase):
    target = "0123456789abcdef0123456789abcdef01234567"
    tag = "files-0123456789ab"

    def test_target_is_resolved_to_a_full_commit_and_bound_to_the_tag(self):
        with patch.object(release.subprocess, "check_output", return_value=self.target + "\n") as git:
            self.assertEqual(release.release_target(self.tag, "HEAD"), self.target)
            git.assert_called_once_with(
                ["git", "rev-parse", "--verify", "--end-of-options", "HEAD^{commit}"],
                cwd=release.ROOT, text=True,
            )
            with self.assertRaisesRegex(ValueError, "release tag must be files-0123456789ab"):
                release.release_target("files-wrong", "HEAD")

    def test_arguments_accept_an_explicit_target_and_default_to_head(self):
        base = ["release.py", self.tag, "vcd/vcd0000-test"]
        with patch("sys.argv", base):
            self.assertEqual(release.arguments().target, "HEAD")
        with patch("sys.argv", base + ["--target", self.target, "--dry-run"]):
            args = release.arguments()
            self.assertEqual(args.target, self.target)
            self.assertEqual(args.fixtures, ["vcd/vcd0000-test"])
            self.assertTrue(args.dry_run)

    def test_creation_uses_the_exact_target_and_only_selected_assets(self):
        assets = [Path("one.gz"), Path("two.gz")]
        with patch.object(release, "check_tag_target") as tag_target, \
             patch.object(release, "release_exists", return_value=False), \
             patch.object(release.subprocess, "run") as gh:
            release.publish(self.tag, assets, self.target)
        tag_target.assert_called_once_with(self.tag, self.target)
        self.assertEqual(gh.call_count, 2)
        create = gh.call_args_list[0].args[0]
        self.assertEqual(create[:4], ["gh", "release", "create", self.tag])
        self.assertEqual(create[create.index("--target") + 1], self.target)
        gh.assert_called_with(
            ["gh", "release", "upload", self.tag, "one.gz", "two.gz",
             "--repo", release.REPOSITORY, "--clobber"], check=True,
        )

    def test_existing_release_is_reused_without_creating_a_tag(self):
        with patch.object(release, "check_tag_target") as tag_target, \
             patch.object(release, "release_exists", return_value=True), \
             patch.object(release.subprocess, "run") as gh:
            release.publish(self.tag, [Path("one.gz")], self.target)
        tag_target.assert_called_once_with(self.tag, self.target)
        gh.assert_called_once_with(
            ["gh", "release", "upload", self.tag, "one.gz",
             "--repo", release.REPOSITORY, "--clobber"], check=True,
        )

    def test_remote_lightweight_and_annotated_tags_must_match_the_target(self):
        ref = f"refs/tags/{self.tag}"
        other = "f" * 40
        cases = (
            ("", True),
            (f"{self.target}\t{ref}\n", True),
            (f"{other}\t{ref}\n{self.target}\t{ref}^{{}}\n", True),
            (f"{other}\t{ref}\n", False),
            (f"{self.target}\t{ref}\n{other}\t{ref}^{{}}\n", False),
        )
        for output, valid in cases:
            with self.subTest(output=output), \
                 patch.object(release.subprocess, "check_output", return_value=output) as git:
                if valid:
                    release.check_tag_target(self.tag, self.target)
                else:
                    with self.assertRaisesRegex(ValueError, "remote tag .* points to .* expected"):
                        release.check_tag_target(self.tag, self.target)
                git.assert_called_once_with(
                    ["git", "ls-remote", f"https://github.com/{release.REPOSITORY}.git", ref, ref + "^{}"],
                    text=True,
                )

    def test_mismatched_tag_blocks_creation_and_existing_release_upload(self):
        for exists in (False, True):
            with self.subTest(release_exists=exists), \
                 patch.object(release, "check_tag_target", side_effect=ValueError("wrong target")), \
                 patch.object(release, "release_exists", return_value=exists), \
                 patch.object(release.subprocess, "run") as gh:
                with self.assertRaisesRegex(ValueError, "wrong target"):
                    release.publish(self.tag, [Path("one.gz")], self.target)
                gh.assert_not_called()

    def test_dry_run_prints_commit_and_assets_without_publishing(self):
        fixture = {"name": "vcd0000-test", "sha256": "a" * 64, "format": "vcd"}
        args = argparse.Namespace(tag=self.tag, fixtures=["vcd/vcd0000-test"],
                                  target=self.target, dry_run=True)
        output = io.StringIO()
        with patch.object(release, "arguments", return_value=args), \
             patch.object(release, "release_target", return_value=self.target), \
             patch.object(release, "selected_fixtures", return_value=[fixture]) as selected, \
             patch.object(release, "publish") as publish, \
             patch.object(release, "compress") as compress, \
             contextlib.redirect_stdout(output):
            release.main()
        selected.assert_called_once_with(args.fixtures)
        publish.assert_not_called()
        compress.assert_not_called()
        self.assertIn(f"Release {self.tag} at {self.target}", output.getvalue())
        self.assertIn(release.asset_name(fixture), output.getvalue())
