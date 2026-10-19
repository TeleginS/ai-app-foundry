#!/usr/bin/env python3
"""Deterministic iOS archive/export/upload CLI. Python standard library only."""

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import zipfile


class Failure(Exception):
    def __init__(self, message, code=2, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def require(condition, message, code=4):
    if not condition:
        raise Failure(message, code)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value, exclusive=False):
    path = Path(path)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        temporary = None
    else:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if temporary:
            os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink()


def read_plist(path):
    try:
        with Path(path).open("rb") as stream:
            return plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        raise Failure(f"Invalid or missing plist: {path}", 4) from error


def safe_child(parent, relative):
    """Reject traversal, absolute paths and symlink escapes in artifact metadata."""
    require(isinstance(relative, str) and relative, "Missing relative artifact path")
    part = PurePosixPath(relative)
    require(not part.is_absolute() and ".." not in part.parts, "Unsafe artifact path")
    path = (parent / relative).resolve()
    require(path.is_relative_to(parent.resolve()), "Artifact path escapes its container")
    return path


class Runner:
    def __init__(self, work=None):
        self.work = work
        self.counter = 0

    def run(self, args, *, capture=True, label="tool", record_stdout=True, cwd=None):
        """No shell, no automatic retries. External output stays in private logs."""
        self.counter += 1
        log = self.work / f"{self.counter:02d}-{label}.log" if self.work else None
        if capture:
            result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, check=False)
            if log:
                fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    if record_stdout:
                        stream.write(result.stdout)
                    stream.write(result.stderr)
            stdout, stderr = result.stdout, result.stderr
        else:
            require(log is not None, "Long-running operations require an output directory", 2)
            fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                result = subprocess.run(args, cwd=cwd, stdout=stream,
                                        stderr=subprocess.STDOUT, check=False)
            stdout, stderr = b"", b""
        if result.returncode:
            raise Failure(f"{args[0]} failed", 3, tool_exit_code=result.returncode,
                          log_path=str(log) if log else None)
        return stdout, stderr


def source_state(repo):
    def git(*args):
        result = subprocess.run(["git", "-C", str(repo), *args], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout

    commit = git("rev-parse", "HEAD").decode().strip()
    require(Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() == repo.resolve(),
            "--repo must name the Git repository root", 2)
    changes = git("status", "--porcelain=v1", "--untracked-files=all")
    h = hashlib.sha256(git("diff", "HEAD", "--binary"))
    for name in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
        if name:
            path = safe_child(repo, os.fsdecode(name))
            h.update(name)
            h.update(digest(path).encode())
    return {"commit": commit, "app_changes": changes.decode().splitlines(),
            "app_diff_sha256": h.hexdigest()}


def identity_from_settings(settings):
    keys = {"version": "MARKETING_VERSION", "build": "CURRENT_PROJECT_VERSION",
            "bundle_id": "PRODUCT_BUNDLE_IDENTIFIER", "team": "DEVELOPMENT_TEAM",
            "signing_style": "CODE_SIGN_STYLE"}
    result = {key: settings.get(value, "") for key, value in keys.items()}
    require(re.fullmatch(r"\d+\.\d+\.\d+", result["version"]), "Invalid app marketing version", 2)
    require(result["build"], "Missing app build number", 2)
    require(result["bundle_id"] and "$" not in result["bundle_id"], "Missing or unresolved app bundle identifier", 2)
    require(result["team"], "Missing signing team", 2)
    require(result["signing_style"] in {"Automatic", "Manual"}, "Unknown signing style", 2)
    return result


def check_expected(identity, args):
    for key in ["version", "build", "team", "bundle_id"]:
        expected = getattr(args, key, None)
        require(not expected or identity[key] == expected, f"Requested {key} does not match artifact/settings", 2)


def select_container(args):
    repo = args.repo.expanduser().resolve()
    require(repo.is_dir(), "Application repository not found", 2)
    if args.project or args.workspace:
        kind = "workspace" if args.workspace else "project"
        path = (repo / (args.workspace or args.project)).resolve()
    else:
        candidates = sorted([*repo.glob("*.xcodeproj"), *repo.glob("*.xcworkspace")])
        require(len(candidates) == 1,
                "Specify --project or --workspace: expected exactly one top-level Xcode container", 2)
        path = candidates[0].resolve()
        kind = "workspace" if path.suffix == ".xcworkspace" else "project"
    suffix = ".xcworkspace" if kind == "workspace" else ".xcodeproj"
    require(path.is_dir() and path.suffix == suffix and path.is_relative_to(repo),
            "Xcode container must exist inside --repo and have the correct extension", 2)
    return {"kind": kind, "path": str(path.relative_to(repo))}


def container_flags(selection):
    return [f"-{selection['kind']}", selection["path"]]


def inspect_project(args, runner):
    repo = args.repo.expanduser().resolve()
    selection = select_container(args)
    developer_dir = runner.run(["xcode-select", "-p"], label="developer-dir")[0].decode().strip()
    xcode = runner.run(["xcodebuild", "-version"], label="xcode-version")[0].decode().strip()
    scheme = args.scheme
    if not scheme:
        output, _ = runner.run(["xcodebuild", *container_flags(selection), "-list", "-json"],
                               cwd=repo, label="schemes")
        schemes = json.loads(output).get(selection["kind"], {}).get("schemes", [])
        require(len(schemes) == 1, "Specify --scheme: expected exactly one Xcode scheme", 2)
        scheme = schemes[0]
    selection.update(scheme=scheme, configuration=args.configuration,
                     validation_configuration=args.validation_configuration)
    identities = []
    for configuration in [args.validation_configuration, args.configuration]:
        output, _ = runner.run([
            "xcodebuild", *container_flags(selection), "-scheme", scheme,
            "-configuration", configuration, "-destination", "generic/platform=iOS",
            "-showBuildSettings", "-json", "-disableAutomaticPackageResolution",
        ], cwd=repo, label=f"settings-{configuration.lower()}", record_stdout=False)
        targets = [item for item in json.loads(output)
                   if item.get("buildSettings", {}).get("PRODUCT_TYPE") == "com.apple.product-type.application"]
        if args.target:
            targets = [item for item in targets if item.get("target") == args.target]
        require(len(targets) == 1, "Specify --target: expected exactly one application target in the scheme", 2)
        target = targets[0]["target"]
        require("target" not in selection or selection["target"] == target,
                "Application target differs between configurations", 2)
        selection["target"] = target
        identities.append(identity_from_settings(targets[0]["buildSettings"]))
    require(identities[0] == identities[1], "App identity or signing settings differ between configurations", 2)
    check_expected(identities[1], args)
    return {"identity": identities[1], "source": source_state(repo),
            "selection": selection,
            "toolchain": {"developer_dir": developer_dir, "xcode": xcode}}


def entitlement_allowed(actual, permitted):
    if isinstance(actual, bool):
        return isinstance(permitted, bool) and (not actual or permitted)
    if isinstance(actual, str):
        return isinstance(permitted, str) and fnmatch.fnmatchcase(actual, permitted)
    if isinstance(actual, list):
        return isinstance(permitted, list) and all(
            any(entitlement_allowed(item, allowed) for allowed in permitted) for item in actual)
    if isinstance(actual, dict):
        return isinstance(permitted, dict) and all(
            key in permitted and entitlement_allowed(value, permitted[key]) for key, value in actual.items())
    return actual == permitted


def validate_profile(profile, entitlements, bundle_id, team, distribution=False):
    expiry = profile.get("ExpirationDate")
    require(isinstance(expiry, dt.datetime), "Provisioning profile has no expiration date")
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=dt.timezone.utc)
    require(expiry > dt.datetime.now(dt.timezone.utc), "Provisioning profile has expired")
    require(team in profile.get("TeamIdentifier", []), "Provisioning profile team mismatch")
    permitted = profile.get("Entitlements", {})
    app_id = entitlements.get("application-identifier", "")
    prefixes = profile.get("ApplicationIdentifierPrefix", [])
    require(any(app_id == f"{prefix}.{bundle_id}" for prefix in prefixes), "Signed application identifier mismatch")
    require(entitlements.get("com.apple.developer.team-identifier") == team, "Signed entitlement team mismatch")
    require(entitlement_allowed(entitlements, permitted), "Signed entitlements exceed provisioning profile")
    is_distribution = (not profile.get("ProvisionedDevices") and
                       not profile.get("ProvisionsAllDevices") and
                       not permitted.get("get-task-allow"))
    if distribution:
        require(is_distribution, "Exported IPA does not use an App Store distribution profile")
        require(not entitlements.get("get-task-allow"), "Distribution app permits debugging")
    return {"expires": expiry.isoformat(), "app_store_profile": is_distribution}


def uuids(output):
    pairs = re.findall(r"UUID: ([0-9A-Fa-f-]+) \(([^)]+)\)", output.decode())
    require(pairs, "No Mach-O UUIDs found")
    return {arch: uuid.upper() for uuid, arch in pairs}


def verify_app(app, runner, expected=None, distribution=False):
    info = read_plist(app / "Info.plist")
    identity = {"version": info.get("CFBundleShortVersionString"),
                "build": info.get("CFBundleVersion"), "bundle_id": info.get("CFBundleIdentifier")}
    require(identity["bundle_id"], "Artifact bundle identifier is missing")
    if expected:
        # Reject the wrong app before invoking signing/export tools.
        for key, value in expected.items():
            if key in identity and value is not None:
                require(identity[key] == value, f"Artifact {key} mismatch")
    require(identity["version"] and identity["build"], "Artifact version/build is missing")
    require(info.get("DTPlatformName") == "iphoneos", "Artifact is not an iOS device app")
    binary = safe_child(app, info.get("CFBundleExecutable"))
    require(binary.is_file(), "App executable is missing")
    arches = runner.run(["lipo", "-archs", str(binary)], label="architectures")[0].decode().split()
    require("arm64" in arches and not {"x86_64", "i386"}.intersection(arches), "Invalid iOS device architectures")
    runner.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], label="signature")
    metadata = runner.run(["codesign", "-d", "--verbose=4", str(app)], label="signing-info")[1].decode()
    match = re.search(r"^TeamIdentifier=(\S+)$", metadata, re.M)
    require(match is not None and match[1] != "not set", "Signed app has no team identifier")
    identity["team"] = match[1]
    ent_data = runner.run(["codesign", "-d", "--entitlements", ":-", str(app)],
                          label="entitlements", record_stdout=False)[0]
    entitlements = plistlib.loads(ent_data)
    profile_data = runner.run(["security", "cms", "-D", "-i", str(app / "embedded.mobileprovision")],
                             label="profile", record_stdout=False)[0]
    profile = validate_profile(plistlib.loads(profile_data), entitlements,
                               identity["bundle_id"], identity["team"], distribution)
    if expected:
        for key in ["version", "build", "bundle_id", "team"]:
            if expected.get(key) is not None:
                require(identity[key] == expected[key], f"Artifact {key} mismatch")
    return {"identity": identity, "architectures": arches, "profile": profile}, binary


def archive_fingerprint(archive, app, binary):
    paths = [archive / "Info.plist", app / "Info.plist", binary,
             app / "embedded.mobileprovision", app / "_CodeSignature" / "CodeResources"]
    require(all(path.is_file() for path in paths), "Archive signature resources are incomplete")
    return hashlib.sha256("".join(digest(path) for path in paths).encode()).hexdigest()


def verify_archive(archive, runner, expected=None):
    archive = archive.resolve()
    info = read_plist(archive / "Info.plist")
    relative = info.get("ApplicationProperties", {}).get("ApplicationPath")
    products = archive / "Products"
    app = safe_child(products, relative)
    require(app.parent == (products / "Applications").resolve() and app.suffix == ".app",
            "Not an iOS application archive")
    report, binary = verify_app(app, runner, expected)
    properties = info["ApplicationProperties"]
    for archive_key, key in [("CFBundleIdentifier", "bundle_id"),
                             ("CFBundleShortVersionString", "version"), ("CFBundleVersion", "build")]:
        require(properties.get(archive_key) == report["identity"][key], "Archive/app metadata mismatch")
    executable_uuids = uuids(runner.run(["dwarfdump", "--uuid", str(binary)], label="app-uuids")[0])
    matches = []
    for dsym in sorted((archive / "dSYMs").glob("*.dSYM")):
        for dwarf in sorted((dsym / "Contents/Resources/DWARF").glob("*")):
            if dwarf.name == binary.name:
                dsym_uuids = uuids(runner.run(["dwarfdump", "--uuid", str(dwarf)], label="dsym-uuids")[0])
                if dsym_uuids == executable_uuids:
                    matches.append(str(dsym))
    require(matches, "App dSYM is missing or its UUIDs do not match")
    report.update(archive_path=str(archive), app_path=str(app), dsyms=matches,
                  uuids=executable_uuids, fingerprint=archive_fingerprint(archive, app, binary))
    manifest = archive.parent / "archive-manifest.json"
    if manifest.is_file():
        recorded = json.loads(manifest.read_text())
        if recorded.get("fingerprint") == report["fingerprint"] and recorded.get("archive_path") == str(archive):
            report["provenance"] = recorded.get("provenance")
    return report


def extract_ipa(ipa, target):
    with zipfile.ZipFile(ipa) as zipped:
        for member in zipped.infolist():
            safe_child(target, member.filename)
            mode = member.external_attr >> 16
            # iOS app bundles do not need symlinks. Reject them rather than extract unsafe targets.
            require(not stat.S_ISLNK(mode), "IPA contains a symlink; automatic inspection is unsupported")
            require(not member.flag_bits & 1, "Encrypted ZIP container is unsupported")
        require(sum(m.file_size for m in zipped.infolist()) <= 8 * 1024**3, "IPA exceeds inspection size limit")
        zipped.extractall(target)
        for member in zipped.infolist():
            path = safe_child(target, member.filename)
            mode = (member.external_attr >> 16) & 0o777
            if mode and path.is_file():
                path.chmod(mode)
    apps = list((target / "Payload").glob("*.app"))
    require(len(apps) == 1, "IPA must contain exactly one Payload app")
    return apps[0]


def verify_ipa(ipa, runner, expected=None):
    with tempfile.TemporaryDirectory(prefix="app-ipa-inspect-") as temporary:
        app = extract_ipa(ipa, Path(temporary))
        report, _ = verify_app(app, runner, expected, distribution=True)
    report.update(ipa_path=str(ipa.resolve()), sha256=digest(ipa))
    return report


def outside_repo(path, repo):
    path = path.expanduser().resolve()
    require(not path.is_relative_to(repo.resolve()), "Artifact/log paths must be outside the repository", 2)
    return path


def fresh_work(path, repo):
    path = outside_repo(path, repo)
    require(not any(parent.suffix == ".xcarchive" for parent in (path, *path.parents)),
            "Output directory must not be inside an archive bundle", 2)
    require(not path.exists(), "Output directory already exists; use a new path", 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=0o700)
    return path


def authentication(args):
    values = [args.authentication_key_path, args.authentication_key_id, args.authentication_key_issuer_id]
    require(not any(values) or all(values), "Provide all three API key arguments or none", 2)
    flags = []
    if all(values):
        require(Path(values[0]).expanduser().is_file(), "API key file not found", 2)
        for option, value in zip(["-authenticationKeyPath", "-authenticationKeyID", "-authenticationKeyIssuerID"], values):
            flags.extend([option, str(Path(value).expanduser().resolve()) if option.endswith("Path") else value])
    if args.allow_provisioning_updates:
        flags.append("-allowProvisioningUpdates")
    return flags


def export_options(args, identity, help_text):
    require("app-store-connect" in help_text and "manageAppVersionAndBuildNumber" in help_text,
            "Installed Xcode lacks required export options; inspect its help", 2)
    options = {"method": "app-store-connect", "destination": args.command,
               "teamID": identity["team"], "signingStyle": args.signing_style,
               "manageAppVersionAndBuildNumber": False, "uploadSymbols": True,
               "testFlightInternalTestingOnly": False}
    if args.signing_style == "manual":
        require(args.profile_mapping, "Manual export requires a profile mapping JSON file", 2)
        mapping = json.loads(args.profile_mapping.read_text())
        require(isinstance(mapping, dict) and identity["bundle_id"] in mapping and
                all(isinstance(k, str) and isinstance(v, str) and v for k, v in mapping.items()),
                "Invalid manual profile mapping", 2)
        options["provisioningProfiles"] = mapping
    else:
        require(not args.profile_mapping, "Profile mapping requires manual signing", 2)
    return options


def archive_command(args, runner):
    inspected = inspect_project(args, runner)
    require(not inspected["source"]["app_changes"] or args.include_dirty_source,
            "App source has local changes; inspect and explicitly include them", 2)
    archive = runner.work / "App.xcarchive"
    selection = inspected["selection"]
    command = ["xcodebuild", *container_flags(selection), "-scheme", selection["scheme"],
               "-configuration", selection["configuration"],
               "-destination", "generic/platform=iOS", "-archivePath", str(archive),
               "-resultBundlePath", str(runner.work / "archive.xcresult"),
               *authentication(args), "archive"]
    runner.run(command, cwd=args.repo.resolve(), capture=False, label="archive")
    require(source_state(args.repo.resolve()) == inspected["source"], "App source changed during archiving")
    report = verify_archive(archive, runner, inspected["identity"])
    report["provenance"] = inspected
    write_json(runner.work / "archive-manifest.json", report, exclusive=True)
    return {"status": "archived", **report}


def distribute(args, runner):
    archive = outside_repo(args.archive, args.repo)
    report = verify_archive(archive, runner, {"bundle_id": args.bundle_id})
    check_expected(report["identity"], args)
    help_stdout, help_stderr = runner.run(["xcodebuild", "-help"], label="export-help")
    options = export_options(args, report["identity"], (help_stdout + help_stderr).decode())
    auth_flags = authentication(args)
    options_path = runner.work / "ExportOptions.plist"
    with options_path.open("xb") as stream:
        plistlib.dump(options, stream)
    options_path.chmod(0o600)
    state_path = archive.parent / f"{archive.name}.upload-state.json"
    state = None
    if args.command == "upload":
        require(args.confirm_upload, "Upload requires --confirm-upload and explicit user authorization", 2)
        require(args.app_id and args.app_id.isdigit(), "Upload requires the verified numeric App Store Connect app ID", 2)
        if state_path.exists():
            previous = json.loads(state_path.read_text())
            require(previous.get("fingerprint") == report["fingerprint"], "Upload receipt belongs to a different artifact", 2)
            require(previous.get("app_id") == args.app_id, "Upload receipt belongs to a different App Store app", 2)
            if previous.get("status") == "uploaded":
                return {"status": "already_uploaded", "receipt": previous,
                        "upload_state_path": str(state_path), "archive": report}
            raise Failure("Previous upload outcome requires reconciliation; no automatic retry", 2,
                          upload_state_path=str(state_path))
        state = {"status": "unknown", "fingerprint": report["fingerprint"],
                 "identity": report["identity"], "app_id": args.app_id,
                 "remote_build_check": args.remote_build_check,
                 "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                 "operation_dir": str(runner.work)}
        # Persist unknown before invoking the uploader, including if the process is interrupted.
        write_json(state_path, state, exclusive=True)
    command = ["xcodebuild", "-exportArchive", "-archivePath", str(archive),
               "-exportOptionsPlist", str(options_path), "-exportPath", str(runner.work / "export"),
               *auth_flags]
    try:
        runner.run(command, capture=False, label=args.command)
    except Failure as error:
        if args.command == "upload":
            raise Failure("Upload outcome is unknown; reconcile the receipt before any retry", 5,
                          upload_state_path=str(state_path), **error.details) from error
        raise
    if args.command == "upload":
        state.update(status="uploaded", processing_status="not_checked",
                     finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(state_path, state)
        return {"status": "uploaded", "processing_status": "not_checked", "archive": report,
                "upload_state_path": str(state_path), "export_options_path": str(options_path),
                "app_url": f"https://appstoreconnect.apple.com/apps/{args.app_id}"}
    ipas = list((runner.work / "export").glob("*.ipa"))
    require(len(ipas) == 1, "Export did not produce exactly one IPA")
    ipa_report = verify_ipa(ipas[0], runner, report["identity"])
    return {"status": "exported", "archive": report, "ipa": ipa_report,
            "export_options_path": str(options_path)}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ["inspect", "archive", "verify-archive", "export", "verify-ipa", "upload"]:
        command = commands.add_parser(name)
        command.add_argument("--repo", type=Path, default=Path.cwd(),
                             help="Application checkout (defaults to the current working directory)")
        command.add_argument("--version")
        command.add_argument("--build")
        command.add_argument("--team")
        command.add_argument("--bundle-id", required=name != "inspect",
                             help="Expected application bundle identifier (an assertion, never an override)")
        if name in {"inspect", "archive"}:
            container = command.add_mutually_exclusive_group()
            container.add_argument("--project", type=Path)
            container.add_argument("--workspace", type=Path)
            command.add_argument("--scheme")
            command.add_argument("--target", help="Application target when a scheme contains several apps")
            command.add_argument("--configuration", default="Release")
            command.add_argument("--validation-configuration", default="Debug")
        command.add_argument("--output-dir", type=Path, required=name in {"archive", "export", "upload"})
        if name in {"archive", "export", "upload"}:
            command.add_argument("--allow-provisioning-updates", action="store_true")
            command.add_argument("--authentication-key-path")
            command.add_argument("--authentication-key-id")
            command.add_argument("--authentication-key-issuer-id")
        if name == "archive":
            command.add_argument("--include-dirty-source", action="store_true")
        if name in {"verify-archive", "export", "upload"}:
            command.add_argument("--archive", type=Path, required=True)
        if name == "verify-ipa":
            command.add_argument("--ipa", type=Path, required=True)
        if name in {"export", "upload"}:
            command.add_argument("--signing-style", choices=["automatic", "manual"], required=True)
            command.add_argument("--profile-mapping", type=Path)
        if name == "upload":
            command.add_argument("--confirm-upload", action="store_true")
            command.add_argument("--app-id")
            command.add_argument("--remote-build-check", choices=["available", "unverified"], required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    work = None
    try:
        args.repo = args.repo.expanduser().resolve()
        # Refuse an unconfirmed upload before even creating output directories.
        if args.command == "upload":
            require(args.confirm_upload, "Upload requires --confirm-upload and explicit user authorization", 2)
        if args.output_dir:
            work = fresh_work(args.output_dir, args.repo)
        runner = Runner(work)
        if args.command == "inspect":
            result = {"status": "inspected", **inspect_project(args, runner)}
        elif args.command == "archive":
            result = archive_command(args, runner)
        elif args.command == "verify-archive":
            result = {"status": "verified", **verify_archive(args.archive, runner, {"bundle_id": args.bundle_id})}
            check_expected(result["identity"], args)
        elif args.command == "verify-ipa":
            result = {"status": "verified", **verify_ipa(args.ipa, runner, {"bundle_id": args.bundle_id})}
            check_expected(result["identity"], args)
        else:
            result = distribute(args, runner)
        code = 0
    except Failure as error:
        result = {"status": "error", "error": str(error), **error.details}
        code = error.code
    except KeyboardInterrupt:
        result = {"status": "interrupted", "error": "Operation interrupted; reconcile any upload before retrying"}
        code = 130
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        # Do not leak captured command output, settings or credentials in exception text.
        result = {"status": "error", "error": f"Invalid input or environment ({type(error).__name__})"}
        code = 2
    result["exit_code"] = code
    if args.command == "upload" and code:
        state_path = args.archive.expanduser().resolve().parent / f"{args.archive.name}.upload-state.json"
        if state_path.is_file():
            result["upload_state_path"] = str(state_path)
            result["upload_status"] = "requires_reconciliation"
    if work:
        result["operation_dir"] = str(work)
        write_json(work / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
