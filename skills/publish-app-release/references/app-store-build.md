# Signed archive, export, and App Store Connect upload

Use the deterministic, standard-library-only CLI in [scripts/app_store_build.py](../scripts/app_store_build.py). The skill selects authorized stages, supplies explicit paths/expected identity, and interprets JSON results. Do not reconstruct shell pipelines for archive, plist generation, signing checks, IPA inspection, or upload.

Creating or updating the skill does not run a build or upload. An archive request defaults to archive-only; an export request additionally creates a local IPA. Upload only when the user explicitly requests it, without asking for the same authorization again. None of these modes implies App Review submission, tester distribution, public release, metadata edits, version/build changes, commits, tags, or GitHub Releases.

## Select source and policy

1. Read `AGENTS.md` and inspect Git status. Use the user's requested app checkout/ref/version/archive, or the current application checkout and app version when omitted. `--repo` must be the Git repository root, including in monorepos. Use a clean managed worktree for a different requested ref; never reset or discard another checkout's changes. Pass its absolute path with `--repo`.
2. Before building, run `inspect`. It resolves the Xcode container, scheme, and application target, then verifies identity in the validation/release configurations, signing team/style, Xcode, and full-checkout source state. Test-target versions are ignored. `--bundle-id`, `--version`, `--build`, and `--team` are assertions, never edits or overrides. `inspect` can infer the bundle ID; every other command requires an explicit verified `--bundle-id`, including commands that operate only on existing artifacts. Stop on mismatches. If the user requests a version/build edit, handle that separately within their authorized scope, then inspect again; use the versioning and GitHub stages in [SKILL.md](../SKILL.md) for release work.
3. For an existing archive, use `verify-archive` and its own version/team/provenance; do not infer a historical archive's source from the current checkout. A matching `archive-manifest.json` beside the archive supplies recorded provenance; otherwise report it as unknown.
4. Use `codebase-memory` for structural source checks when available; otherwise inspect the selected app checkout with local search and file tools. Verify the selected app's documented production requirements: debug/test overrides, access rules, entitlements, Terms/Privacy links, and relevant testing configuration. Do not assume a particular payment provider, entitlement name, or feature flag. Reuse verified checks for identical release source. The CLI validates binary/signing identity, not product behavior or policy/legal correctness.
5. Before export/upload, verify current [Apple upload requirements](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/). The CLI checks installed Xcode export-option support; it does not certify that Apple currently accepts that Xcode/SDK.

## CLI contract

Run with Python 3.9+ on macOS with Xcode selected. Resolve the installed skill directory as `SKILL_DIR` and use its absolute script path. Pass the application checkout explicitly with `--repo`; the plugin directory is not the application checkout. Without `--repo`, the CLI uses the current working directory, never its installation path:

```bash
python3 "$SKILL_DIR/scripts/app_store_build.py" --help
```

Commands emit a JSON result to stdout. Commands with an output directory also save `result.json` there. Exit codes: `0` success, `2` invalid input/environment or blocked operation, `3` external tool failure, `4` artifact verification failure, `5` upload outcome unknown, `130` interruption. Argument syntax errors use argparse's exit code `2` and stderr usage text.

Each archive/export/upload needs a **new** `--output-dir` outside the repository. Choose persistent version/build/run-based locations, for example beneath `~/Library/Developer/<app-name>/AppStoreBuilds/`; never put the only deliverable in a temporary directory. The CLI creates private directories/logs and refuses existing output directories or paths within the selected repository. Do not place output inside an existing `.xcarchive` bundle. Keep dSYMs, logs, manifests, export options, and IPA with the delivered run.

Use these command shapes, replacing sample paths with actual absolute paths:

```bash
# Read-only: resolved identity and source provenance; no archive or upload.
python3 "$SKILL_DIR/scripts/app_store_build.py" inspect \
  --repo /absolute/repo --version 1.2.3

# Signed Release device archive; result includes the persistent archive path.
python3 "$SKILL_DIR/scripts/app_store_build.py" archive \
  --repo /absolute/repo --bundle-id com.example.app --version 1.2.3 --build 1 \
  --output-dir /absolute/persistent/new-archive-run

# Verify an existing archive independently of the current checkout version.
python3 "$SKILL_DIR/scripts/app_store_build.py" verify-archive \
  --archive /absolute/run/App.xcarchive --bundle-id com.example.app --version 1.2.3

# Export and verify a local App Store Connect IPA; no upload.
python3 "$SKILL_DIR/scripts/app_store_build.py" export \
  --archive /absolute/run/App.xcarchive --bundle-id com.example.app --version 1.2.3 \
  --signing-style automatic --output-dir /absolute/persistent/new-export-run

# Verify the exported IPA separately, including its distribution profile and SHA-256.
python3 "$SKILL_DIR/scripts/app_store_build.py" verify-ipa \
  --ipa /absolute/export/App.ipa --bundle-id com.example.app --version 1.2.3 --build 1
```

The archive stage uses the resolved project/workspace, scheme, release configuration, and `generic/platform=iOS`, preserving code signing. Its output name is the neutral `App.xcarchive`; the app product and exported IPA retain the names chosen by Xcode (use the paths returned in JSON rather than assuming the sample IPA filename). It verifies version/build/bundle ID/team, device architecture, the app/nested signatures, profile expiry/entitlements, archive metadata, and matching app dSYM UUIDs. It detects full-checkout changes during archiving, including shared modules, build configuration, and untracked files. No fixed app-directory allowlist is used; ignored files and dependencies outside the Git root are not fingerprinted. Verify these external inputs separately when they affect the build. Existing Git or metadata checks do not substitute for these artifact checks.

When the requested build intentionally includes inspected local checkout changes, add `--include-dirty-source`. Do not use it to bypass unexplained changes. The JSON provenance records those changes and a diff digest. The CLI does not edit source or automatically restore a scheme; review any Xcode-generated diff and restore only changes proven to come from the run.

## Select the Xcode container and scheme

- Supply either `--project <path>.xcodeproj` or `--workspace <path>.xcworkspace` for `inspect`/`archive` when needed. Paths are relative to `--repo` or absolute inside it. Nested containers are supported explicitly. With neither flag, discovery requires exactly one top-level container; it never chooses between a workspace and a project silently.
- Supply `--scheme <scheme>` when there are several schemes. Without it, `xcodebuild -list -json` must report exactly one scheme.
- Application targets are selected by resolved `PRODUCT_TYPE = com.apple.product-type.application`, not by matching the scheme name. Test and extension targets are excluded. If several app targets participate, require `--target <native-app-target>`; archive verification still asserts the selected app identity.
- Configurations default to `Release` and `Debug`. Use `--configuration <release-configuration>` and `--validation-configuration <validation-configuration>` for other names. Both must resolve the same app version/build/bundle/team/signing identity; `--validation-configuration` may name the release configuration when the app's debug flavor intentionally differs.
- The JSON `selection` (also recorded in archive provenance) identifies the container, scheme, target, and configurations. Preserve these resolved values for the archive stage; artifact-only verification/export/upload does not require a source project or a scheme.

For example, run `inspect --repo /absolute/repo --workspace 'Client Workspace.xcworkspace' --scheme 'Store Scheme' --target 'Mobile App' --configuration AppStore --validation-configuration Development` using the installed script. Use the returned bundle ID as the required assertion in subsequent commands, e.g. `archive --repo /absolute/repo --workspace 'Client Workspace.xcworkspace' --scheme 'Store Scheme' --target 'Mobile App' --configuration AppStore --validation-configuration Development --bundle-id com.example.app --output-dir /absolute/persistent/new-archive-run`.

## Signing and exports

Use the signing style/team confirmed by `inspect`, archive provenance, or the archive's signing configuration. `--signing-style` is mandatory for export/upload so the CLI never silently chooses one. Manual signing also requires `--profile-mapping /absolute/profiles.json`, a JSON object mapping the actual app/extension bundle IDs to their actual distribution profile names/UUIDs.

Use the configured Xcode account/keychain. If needed for automatic signing, add `--allow-provisioning-updates`; Xcode may then manage profiles, app IDs, and certificates. Do not add device registration, revoke certificates, or change teams to bypass errors. API-key authentication is optional and takes all three flags together: `--authentication-key-path`, `--authentication-key-id`, and `--authentication-key-issuer-id`. Use an existing protected key file; never print its contents or ask the user to paste secrets into chat.

The CLI generates `ExportOptions.plist` with `method=app-store-connect`, explicit `destination=export` or `upload`, `manageAppVersionAndBuildNumber=false`, symbol upload enabled, and App Store distribution enabled. It checks a locally exported IPA against the archive and computes SHA-256. ZIP traversal and symlinks are rejected rather than inspected unsafely; report an unsupported artifact instead of skipping verification.

For missing Xcode login/keychain access, explain the specific local action required and retain diagnostics. For a build/export failure, inspect the private log, fix only authorized configuration, and retry once with a new output directory after a concrete correction. Do not turn off signing or label an incomplete artifact ready. Apply dependency workarounds only when supported by the selected project's documentation or diagnosed logs. Do not repeat simulator builds/tests solely to create an archive.

## Upload

First confirm the existing App Store Connect app record matches the verified application bundle ID and the signing account/team. Read its numeric app ID from the authenticated surface; do not guess it. Check whether the exact version/build is available when possible. A confirmed duplicate requires an authorized new build number and a newly verified archive. If build history is unavailable, disclose that fact and use `--remote-build-check unverified`; this is recorded rather than presented as a successful availability check.

After explicit upload authorization and local verification:

```bash
python3 "$SKILL_DIR/scripts/app_store_build.py" upload \
  --archive /absolute/run/App.xcarchive --bundle-id com.example.app --version 1.2.3 --build 1 \
  --signing-style automatic --output-dir /absolute/persistent/new-upload-run \
  --app-id 1234567890 --remote-build-check available --confirm-upload
```

`--confirm-upload` conveys the user's authorization; the skill must not add it for an archive/export-only request. `--app-id` and `--remote-build-check` are recorded agent-verified inputs, not an automated App Store Connect API lookup.

Before invoking the uploader, the CLI writes an exclusive `<archive>.upload-state.json` beside the archive with its fingerprint and `unknown` status. A zero uploader exit records `uploaded` with processing `not_checked`; repeat runs return `already_uploaded` without sending the binary again. Errors/interruption leave `unknown`, blocking automatic retry. Preserve this receipt. Do not delete it, relocate the archive, or switch upload tools to bypass the guard. Reconcile an unknown result from uploader logs and the exact App Store Connect version/build first; if unavailable, stop and report the unknown outcome. There is deliberately no blind retry command.

Keep transport acceptance distinct from processing and App Store validation. After an authorized upload, use an authenticated App Store Connect surface for a bounded processing check when available. Report pending, failed, or unverified processing accurately; do not imply a public release or promise background monitoring without a scheduling request.

## Delivery and validation

Return version/build, source commit and included changes, team/Xcode, actual archive/export/upload status, material warnings, and clickable absolute artifact/log paths from the JSON result. Report IPA SHA-256 when exported. Preserve delivery artifacts and remove only temporary inspection files created by the run. Never commit archives, IPAs, profiles, credentials, logs, or DerivedData.

Validate changes to the skill and scripts with the skill-creator validator and the offline tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s "$SKILL_DIR/tests" -v
```

Tests replace external tools with local fakes; they never build, sign, or upload a real app. `inspect` provides a real read-only smoke check on the configured Mac. A successful test suite does not demonstrate a real signed archive/export/upload.

References: [Apple distribution workflow](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases), [archive export files](https://help.apple.com/xcode/mac/current/en.lproj/deva1f2ab5a2.html), and installed `xcodebuild -help`.
