"""Offline orchestration/verification tests. No real signing, builds or uploads."""

import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/app_store_build.py"
spec = importlib.util.spec_from_file_location("app_store_build", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
REAL_RUNNER = cli.Runner
TEAM = "TESTTEAM01"
UUID = "00112233-4455-6677-8899-AABBCCDDEEFF"
SOURCE = {"commit": "test-commit", "app_changes": [], "app_diff_sha256": "test-diff"}


def profile(distribution=False):
    value = {"ExpirationDate": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(days=1),
             "TeamIdentifier": [TEAM], "ApplicationIdentifierPrefix": ["PREFIX"],
             "Entitlements": {"application-identifier": f"PREFIX.{cli.BUNDLE_ID}",
                              "com.apple.developer.team-identifier": TEAM,
                              "get-task-allow": not distribution}}
    if not distribution:
        value["ProvisionedDevices"] = ["device"]
    return value


def write_plist(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(value))


def make_archive(path):
    app = path / "Products/Applications/TrafficTestApp.app"
    write_plist(app / "Info.plist", {"CFBundleIdentifier": cli.BUNDLE_ID,
                                   "CFBundleShortVersionString": "2.0.3", "CFBundleVersion": "1",
                                   "CFBundleExecutable": "TrafficTestApp", "DTPlatformName": "iphoneos"})
    (app / "TrafficTestApp").write_bytes(b"mock Mach-O")
    (app / "TrafficTestApp").chmod(0o755)
    write_plist(app / "embedded.mobileprovision", profile())
    (app / "_CodeSignature").mkdir()
    (app / "_CodeSignature/CodeResources").write_bytes(b"mock resource seal")
    write_plist(path / "Info.plist", {"ApplicationProperties": {
        "ApplicationPath": "Applications/TrafficTestApp.app", "CFBundleIdentifier": cli.BUNDLE_ID,
        "CFBundleShortVersionString": "2.0.3", "CFBundleVersion": "1"}})
    dwarf = path / "dSYMs/TrafficTestApp.app.dSYM/Contents/Resources/DWARF/TrafficTestApp"
    dwarf.parent.mkdir(parents=True)
    dwarf.write_bytes(b"mock DWARF")
    return app


class FakeRunner:
    calls = []
    fail_label = None
    wrong_dsym = False
    export_development_profile = False

    def __init__(self, work=None):
        self.work = work

    def run(self, args, *, label="tool", **kwargs):
        self.calls.append((args, label))
        if label == self.fail_label:
            raise cli.Failure("mock tool failed", 3, tool_exit_code=65, log_path="private.log")
        if args[:2] == ["xcode-select", "-p"]:
            return b"/Applications/Xcode.app/Contents/Developer\n", b""
        if args[:2] == ["xcodebuild", "-version"]:
            return b"Xcode test\nBuild version test\n", b""
        if "-showBuildSettings" in args:
            data = [{"target": "TrafficTestAppTests", "buildSettings": {"MARKETING_VERSION": "9.9.9"}},
                    {"target": cli.SCHEME, "buildSettings": {
                        "MARKETING_VERSION": "2.0.3", "CURRENT_PROJECT_VERSION": "1",
                        "PRODUCT_BUNDLE_IDENTIFIER": cli.BUNDLE_ID, "DEVELOPMENT_TEAM": TEAM,
                        "CODE_SIGN_STYLE": "Automatic"}}]
            return json.dumps(data).encode(), b""
        if args[:2] == ["xcodebuild", "-help"]:
            return b"", b"method: app-store-connect; manageAppVersionAndBuildNumber"
        if args[0] == "xcodebuild" and "archive" in args:
            make_archive(Path(args[args.index("-archivePath") + 1]))
            return b"", b""
        if args[:2] == ["xcodebuild", "-exportArchive"]:
            options = cli.read_plist(Path(args[args.index("-exportOptionsPlist") + 1]))
            if options["destination"] == "export":
                archive = Path(args[args.index("-archivePath") + 1])
                destination = Path(args[args.index("-exportPath") + 1])
                destination.mkdir()
                with tempfile.TemporaryDirectory() as temporary:
                    payload = Path(temporary) / "Payload/TrafficTestApp.app"
                    shutil.copytree(archive / "Products/Applications/TrafficTestApp.app", payload)
                    write_plist(payload / "embedded.mobileprovision",
                                profile(distribution=not self.export_development_profile))
                    with zipfile.ZipFile(destination / "TrafficTestApp.ipa", "w") as zipped:
                        for file in payload.rglob("*"):
                            if file.is_file():
                                zipped.write(file, file.relative_to(temporary))
            return b"", b""
        if args[0] == "lipo":
            return b"arm64\n", b""
        if args[0] == "codesign":
            if "--verify" in args:
                return b"", b"valid on disk"
            if "--entitlements" in args:
                return plistlib.dumps(cli.read_plist(Path(args[-1]) / "embedded.mobileprovision")["Entitlements"]), b""
            return b"", f"TeamIdentifier={TEAM}\n".encode()
        if args[0] == "security":
            return Path(args[-1]).read_bytes(), b""
        if args[0] == "dwarfdump":
            uuid = "BAD" if self.wrong_dsym and "dSYMs" in args[-1] else UUID
            return f"UUID: {uuid} (arm64) app\n".encode(), b""
        raise AssertionError(f"Unexpected external operation: {args}")


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        (self.repo / cli.PROJECT).mkdir(parents=True)
        self.archive = self.root / "input/TrafficTestApp.xcarchive"
        make_archive(self.archive)
        self.runner_patch = patch.object(cli, "Runner", FakeRunner)
        self.source_patch = patch.object(cli, "source_state", return_value=copy.deepcopy(SOURCE))
        self.runner_patch.start()
        self.source_patch.start()
        FakeRunner.calls = []
        FakeRunner.fail_label = None
        FakeRunner.wrong_dsym = False
        FakeRunner.export_development_profile = False

    def tearDown(self):
        self.source_patch.stop()
        self.runner_patch.stop()
        self.temporary.cleanup()

    def invoke(self, command, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main([command, "--repo", str(self.repo), *map(str, args)])
        result = json.loads(output.getvalue())
        self.assertEqual(code, result["exit_code"])
        return code, result

    def distribution_args(self, output, *extra):
        return ["--archive", self.archive, "--output-dir", self.root / output,
                "--signing-style", "automatic", *extra]

    def test_installed_cli_inspects_current_app_checkout_without_repo_flag(self):
        output = io.StringIO()
        with patch("os.getcwd", return_value=str(self.repo)), contextlib.redirect_stdout(output):
            code = cli.main(["inspect"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "inspected")
        cli.source_state.assert_called_once_with(self.repo.resolve())

    def test_explicit_app_checkout_overrides_plugin_working_directory(self):
        with patch("os.getcwd", return_value=str(SCRIPT.parents[3])):
            code, report = self.invoke("inspect")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "inspected")
        cli.source_state.assert_called_once_with(self.repo.resolve())

    def test_archive_selects_app_target_and_preserves_identity_and_source(self):
        code, report = self.invoke("archive", "--output-dir", self.root / "archive-run", "--version", "2.0.3")
        self.assertEqual(code, 0)
        self.assertEqual(report["identity"]["version"], "2.0.3")
        self.assertEqual(report["identity"]["build"], "1")
        self.assertEqual(report["provenance"]["source"], SOURCE)
        self.assertTrue(Path(report["archive_path"]).is_dir())
        self.assertTrue((self.root / "archive-run/archive-manifest.json").is_file())
        command = next(args for args, label in FakeRunner.calls if label == "archive")
        self.assertIn("generic/platform=iOS", command)
        self.assertNotIn("CODE_SIGNING_ALLOWED=NO", command)

    def test_archive_failure_is_not_reported_as_success(self):
        FakeRunner.fail_label = "archive"
        code, result = self.invoke("archive", "--output-dir", self.root / "failed")
        self.assertEqual(code, 3)
        self.assertEqual(result["tool_exit_code"], 65)
        self.assertFalse((self.root / "failed/archive-manifest.json").exists())

    def test_version_mismatch_stops_before_build(self):
        code, _ = self.invoke("archive", "--output-dir", self.root / "wrong", "--version", "9.9.9")
        self.assertEqual(code, 2)
        self.assertNotIn("archive", [label for _, label in FakeRunner.calls])

    def test_output_inside_repo_and_existing_directory_are_refused(self):
        for output in [self.repo / "output", self.root / "input", self.archive / "export-output"]:
            code, _ = self.invoke("archive", "--output-dir", output)
            self.assertEqual(code, 2)
        self.assertFalse(FakeRunner.calls)

    def test_dirty_source_is_not_silently_included(self):
        dirty = {**SOURCE, "app_changes": [" M TrafficRulesApp/Example.swift"]}
        with patch.object(cli, "source_state", return_value=dirty):
            code, _ = self.invoke("archive", "--output-dir", self.root / "dirty")
            self.assertEqual(code, 2)
            code, report = self.invoke("archive", "--output-dir", self.root / "included",
                                       "--include-dirty-source")
            self.assertEqual(code, 0)
            self.assertEqual(report["provenance"]["source"], dirty)

    def test_source_changes_during_build_are_rejected(self):
        with patch.object(cli, "source_state", side_effect=[SOURCE, {**SOURCE, "commit": "different"}]):
            code, _ = self.invoke("archive", "--output-dir", self.root / "changing")
        self.assertEqual(code, 4)

    def test_unsigned_archive_or_missing_dsym_is_rejected(self):
        FakeRunner.fail_label = "signature"
        code, _ = self.invoke("verify-archive", "--archive", self.archive)
        self.assertNotEqual(code, 0)
        FakeRunner.fail_label = None
        shutil.rmtree(self.archive / "dSYMs")
        code, _ = self.invoke("verify-archive", "--archive", self.archive)
        self.assertEqual(code, 4)

    def test_mismatching_dsym_is_rejected(self):
        FakeRunner.wrong_dsym = True
        code, _ = self.invoke("verify-archive", "--archive", self.archive)
        self.assertEqual(code, 4)

    def test_archive_path_traversal_is_rejected_before_external_verification(self):
        metadata = cli.read_plist(self.archive / "Info.plist")
        metadata["ApplicationProperties"]["ApplicationPath"] = "../../outside.app"
        write_plist(self.archive / "Info.plist", metadata)
        code, _ = self.invoke("verify-archive", "--archive", self.archive)
        self.assertEqual(code, 4)
        self.assertFalse(FakeRunner.calls)

    def test_export_verifies_ipa_and_does_not_upload_or_renumber(self):
        code, result = self.invoke("export", *self.distribution_args("export-run"))
        self.assertEqual(code, 0)
        options = cli.read_plist(Path(result["export_options_path"]))
        self.assertEqual(options["destination"], "export")
        self.assertEqual(options["method"], "app-store-connect")
        self.assertIs(options["manageAppVersionAndBuildNumber"], False)
        self.assertIs(options["testFlightInternalTestingOnly"], False)
        self.assertEqual(len(result["ipa"]["sha256"]), 64)
        self.assertEqual(result["ipa"]["identity"], result["archive"]["identity"])
        self.assertNotIn("upload", [label for _, label in FakeRunner.calls])

    def test_development_signed_ipa_is_rejected(self):
        FakeRunner.export_development_profile = True
        code, _ = self.invoke("export", *self.distribution_args("bad-export"))
        self.assertEqual(code, 4)

    def test_upload_requires_explicit_flag_and_does_not_touch_disk(self):
        code, _ = self.invoke("upload", *self.distribution_args("unconfirmed"),
                              "--remote-build-check", "unverified")
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "unconfirmed").exists())
        self.assertFalse(FakeRunner.calls)

    def test_upload_receipt_prevents_repeated_upload(self):
        extra = ["--confirm-upload", "--app-id", "12345", "--remote-build-check", "unverified"]
        code, report = self.invoke("upload", *self.distribution_args("upload-run", *extra))
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "uploaded")
        self.assertEqual(report["processing_status"], "not_checked")
        code, repeated = self.invoke("upload", *self.distribution_args("repeat-run", *extra))
        self.assertEqual(code, 0)
        self.assertEqual(repeated["status"], "already_uploaded")
        self.assertEqual([label for _, label in FakeRunner.calls].count("upload"), 1)
        state = Path(report["upload_state_path"])
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)

    def test_invalid_authentication_is_rejected_before_upload_receipt(self):
        code, _ = self.invoke("upload", *self.distribution_args("invalid-auth"),
                              "--confirm-upload", "--app-id", "12345", "--remote-build-check", "available",
                              "--authentication-key-path", self.root / "missing.p8")
        self.assertEqual(code, 2)
        self.assertFalse(list(self.archive.parent.glob("*.upload-state.json")))
        self.assertNotIn("upload", [label for _, label in FakeRunner.calls])

    def test_unknown_upload_blocks_retry_and_retains_receipt(self):
        FakeRunner.fail_label = "upload"
        extra = ["--confirm-upload", "--app-id", "12345", "--remote-build-check", "available"]
        code, report = self.invoke("upload", *self.distribution_args("failed-upload", *extra))
        self.assertEqual(code, 5)
        state = json.loads(Path(report["upload_state_path"]).read_text())
        self.assertEqual(state["status"], "unknown")
        FakeRunner.fail_label = None
        code, _ = self.invoke("upload", *self.distribution_args("retry-upload", *extra))
        self.assertEqual(code, 2)
        self.assertEqual([label for _, label in FakeRunner.calls].count("upload"), 1)

    def test_expired_profile_and_entitlement_escalation_are_rejected(self):
        original = profile()
        entitlements = original["Entitlements"]
        bad = copy.deepcopy(original)
        bad["ExpirationDate"] = dt.datetime(2000, 1, 1)
        with self.assertRaises(cli.Failure):
            cli.validate_profile(bad, entitlements, cli.BUNDLE_ID, TEAM)
        elevated = {**entitlements, "aps-environment": "production"}
        with self.assertRaises(cli.Failure):
            cli.validate_profile(original, elevated, cli.BUNDLE_ID, TEAM)

    def test_ipa_zip_traversal_and_symlinks_are_rejected(self):
        for name, symlink in [("../escape", False), ("Payload/app.app/link", True)]:
            ipa = self.root / "malicious.ipa"
            with zipfile.ZipFile(ipa, "w") as zipped:
                member = zipfile.ZipInfo(name)
                if symlink:
                    member.external_attr = (stat.S_IFLNK | 0o777) << 16
                zipped.writestr(member, "/outside")
            code, _ = self.invoke("verify-ipa", "--ipa", ipa)
            self.assertEqual(code, 4)
            self.assertFalse((self.root / "escape").exists())

    def test_manual_signing_requires_real_profile_mapping(self):
        arguments = self.distribution_args("manual")
        arguments[arguments.index("automatic")] = "manual"
        code, _ = self.invoke("export", *arguments)
        self.assertEqual(code, 2)
        self.assertNotIn("export", [label for _, label in FakeRunner.calls])

    def test_external_failure_output_is_kept_in_private_log(self):
        work = self.root / "private-run"
        work.mkdir(mode=0o700)
        runner = REAL_RUNNER(work)
        with self.assertRaises(cli.Failure) as captured:
            runner.run([sys.executable, "-c", "import sys; print('private-output'); sys.exit(7)"],
                       capture=False, label="failed-command")
        self.assertEqual(captured.exception.details["tool_exit_code"], 7)
        self.assertNotIn("private-output", str(captured.exception))
        log = Path(captured.exception.details["log_path"])
        self.assertIn("private-output", log.read_text())
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
