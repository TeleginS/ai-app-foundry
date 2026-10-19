---
name: publish-app-release
description: Prepare localized App Store metadata or run authorized iOS versioning, GitHub release, signed archive, IPA export, and App Store Connect upload stages. Use for an iOS app's store copy, version, tag, archive, upload, or release requests; resolve project identity and conventions from the selected app checkout.
---

# Publish iOS App Release

Prepare or publish an iOS app release while preserving the repository's current release conventions. This skill owns versioning, App Store copy, GitHub publication, and signed archive/export/upload through [scripts/app_store_build.py](scripts/app_store_build.py). Execute the requested stages in order; Git, GitHub, and Apple mutations must stay within the user's requested scope. Updating this skill alone does not run a release or upload.

## Installed plugin context

Resolve bundled scripts and references relative to this installed skill directory. Resolve app paths, Git state, and metadata in the user's selected application checkout; always pass its Git repository root explicitly with `--repo`. The plugin installation directory is not the application repository.

Run CLI `inspect` for archive/distribution work. For version or metadata-only work, resolve the same identity through read-only project/build settings without requiring signing access or an archive. Establish the `.xcodeproj` or `.xcworkspace`, scheme, native application target, bundle ID, release and validation configurations (defaults: Release and Debug), separate marketing version/build number, and requested metadata locales. Use explicit CLI `--project` or `--workspace`, `--scheme`, and `--target` when discovery is ambiguous; a scheme's name need not match its target. Supply `--configuration` and `--validation-configuration` for custom configurations. Do not guess between multiple apps.

`inspect` may infer the bundle ID from resolved app settings; `--bundle-id` is an optional assertion there. Every archive or artifact verification/export/upload command requires the verified `--bundle-id` as an assertion. Do not change app identifiers or signing settings to satisfy a supplied value. Full-checkout provenance includes shared code, configuration, and untracked files outside conventional app directories; resolve unrelated changes before requiring a clean release checkout.

## Published list formatting

In every prepared or published output, including App Store fields, GitHub Release notes, saved files, and chat responses, keep bulleted content as lists. Put each bullet and its item text on a separate line; never join multiple items into a paragraph or replace actual line breaks with literal `\n` sequences.

- For Markdown output, use native `- ` list items and a blank line before the list so it renders as a list.
- For plain-text App Store fields in all selected locales, use `• ` at the start of each item line, with actual line breaks between items. When reproducing these copy-ready fields in chat, use fenced `text` blocks to preserve their line breaks.
- Preserve these line breaks when passing text to publication tools, and verify the saved or published body before reporting success. Apply this rule to new copy and explicitly requested revisions; do not rewrite published historical files solely to change formatting.

## Choose the mode

Classify the request before changing anything:

1. **Version bump** — update `MARKETING_VERSION` to the user's exact semantic version, then prepare and save App Store metadata as step 2. A bump-only request does not authorize a commit, push, tag, release, merge, or App Store upload. Use the landing strategy the user specifies; ask before the first remote mutation if none is given.
2. **Bump and publish** — the user supplies an exact semantic version and explicitly requests the applicable commit/push/tag/release stages. Direct pushes to the default or protected release branch require an explicit request for that landing strategy.
3. **Publish current version** — the user asks for a tag and/or GitHub Release for a version already landed on a remote release branch. An explicit version is optional: when omitted, infer it from the app target at the exact remote release commit. A request for both tag and release authorizes creating and pushing the verified tag and then creating the GitHub Release without another approval. A tag-only request authorizes only the tag; a release-only request requires an existing verified tag. None of these requests authorizes a version edit, commit, branch push, merge, or App Store upload.
4. **Release through App Store Connect upload** — the user requests the complete pipeline through upload, with an exact version when a bump is needed. Run the authorized version/metadata/GitHub stages, then step 5 to create or reuse the verified signed archive and upload it. If they request archive-only or local IPA export as part of the release, stop step 5 at that outcome. Explicit upload authorization persists across all preceding stages; do not ask for it again at step 5. Direct pushes to the default or protected release branch still require explicit authorization, which may already be present in the session.

5. **Archive/export/upload only** — perform step 5 directly using the requested source ref or existing archive, or the current checkout when omitted. Skip version edits, metadata preparation, GitHub convention/publication checks, and steps 1–4 unless separately requested. An archive request defaults to archive-only; an export request additionally creates a local IPA. An upload request authorizes preparing the needed archive and uploading it, without another confirmation.
6. **App Store metadata only** — perform step 2 directly for the requested version, including historical versions, or infer the current app version when omitted. Prepare or validate both fields for every selected locale and save one Markdown file per locale. Skip version edits, GitHub publication/authentication preflight, builds, archives, uploads, and steps 1 and 3–5 unless separately requested. Use read-only release evidence as needed; a copy request does not authorize committing, pushing, or editing App Store Connect.

A GitHub-only release request ends at step 4; a complete pipeline request that includes upload continues through step 5. For archive/export/upload-only mode, read [references/app-store-build.md](references/app-store-build.md) and use the bundled CLI rather than running a separate skill.

For publish-current mode, use an explicitly named release branch or otherwise the repository's remote default branch. If the version is unlanded, the target commit is ambiguous, or the remote branch does not contain the intended product changes, stop before mutations and ask one concrete target/landing question.

In publish-current mode, if the user supplies a version, compare it with the resolved app version at the release commit. Never ignore a mismatch or silently publish either value.

Never force-push, move or overwrite a tag, recreate a release, use `--admin`, bypass branch protection, or operate on another repository or remote.

## Establish the current convention

Inspect conventions on every run because they may change:

1. Read `AGENTS.md`; inspect `git status --short --branch`, remotes, the remote default branch, and `git worktree list --porcelain`.
2. Use a clean worktree at the exact remote release commit. A clean detached managed worktree is appropriate when the branch-owning checkout contains unrelated changes. Never switch or clean another worktree to make room.
3. Inspect recent local and remote tags, `gh release list`, two or three recent release bodies, and their tag objects. Fetch the target branch without rewriting historical local tags.
4. Inspect the actual commits and merged PRs since the most recent published release.

Follow the verified tag format, annotation message, release title, notes language/sections, stable/prerelease policy, and compare-link convention. Do not import conventions from the plugin's repository or a different app. If no publication history exists, use an annotated `vX.Y.Z` tag, a `Release vX.Y.Z` title, stable status, and concise user-facing notes in the user's requested language unless the project specifies otherwise.

Do not hardcode the previous release tag or infer it from version arithmetic.

## Resolve the application version

The version source is resolved `MARKETING_VERSION` for the selected native application target. Find its defining project settings or `.xcconfig` files in the application checkout; workspace and scheme names are not target identifiers.

- Read both validation and release configuration values at the exact release commit; they must be equal semantic versions.
- Confirm both with `xcodebuild -showBuildSettings` for the resolved container and scheme; assert the same verified `PRODUCT_BUNDLE_IDENTIFIER` and application target.
- Treat `CURRENT_PROJECT_VERSION` as the separate build number. Do not derive the marketing version from it or change it unless requested.
- Ignore `MARKETING_VERSION` values belonging to unit-test or UI-test targets.

In publish-current mode, also require the remote target branch to equal the inspected commit and already contain this version. Do not create a compensating commit or push the branch.

## Preflight publication state

Before any remote mutation, verify GitHub authentication and inspect the exact local tag ref, remote tag ref and GitHub Release:

- **Tag and release absent:** proceed when the release commit and version are verified.
- **Remote annotated tag exists at the intended commit, release absent:** this is a safe partial retry; create only the release after validating the tag name, message and dereferenced commit.
- **Tag and release both already match:** report that GitHub publication is already complete and skip recreating those objects. Continue to step 5 if archive/export/upload was also requested; an existing GitHub Release does not complete that Apple distribution stage.
- **Any tag/release points elsewhere or has conflicting metadata:** stop and report the conflict. Never delete, retarget or overwrite it.

Re-check the remote branch immediately before creating a new tag. Stop on unexpected remote movement, unrelated worktree changes, or ambiguous release contents.

## Release steps

After the checks above, follow this order:

1. Bump the application version when authorized.
2. Prepare App Store metadata for the bumped version using the workflow below and save all selected locale files.
3. Validate the release and land the version and metadata changes only when authorized.
4. Tag and publish only when authorized.
5. Use the bundled CLI to create or reuse the signed archive, export an IPA, or upload to App Store Connect according to the requested release outcome.

In publish-current mode, skip steps 1 and 2; do not create a metadata commit for a version that is already landed. If the user explicitly limits a bump request to the version edit alone, honor that narrower scope and report that metadata preparation was skipped.

## Step 1 — Change the version when authorized

Skip this section entirely in publish-current mode.

- Update only the selected app target's marketing version in the files/configurations that define it; preserve other targets and shared settings unrelated to the requested version.
- Do not change test-target versions merely to make project values equal.
- Use `apply_patch`; review the exact diff and run `git diff --check`.

Proceed directly to step 2 before committing or pushing the version change.

## Step 2 — Prepare App Store metadata

Use the workflow below for the exact version set in step 1, or directly for metadata-only mode. Perform it once and produce one set of files for the selected version; no separate metadata skill is needed.

Create exactly two copy-ready fields per selected locale. Honor user-specified locales; otherwise infer the supported metadata locales from approved existing store files and app localization settings. If that evidence is ambiguous, ask for the locale set before generating copy. Follow the established metadata location; when none exists, save one Markdown file per locale under:

```text
docs/app-store/<X.Y.Z>/<locale>.md
```

Each file must contain only these headings and their field bodies:

```markdown
## Description

...

## What's New in This Version

...
```

The version and locale are already clear from the path; do not add frontmatter or commentary inside the file.

### Select the metadata version

- In the release pipeline, use the exact semantic version from step 1 and confirm it matches the equal validation and release `MARKETING_VERSION` values for the selected native application target. Confirm the resolved bundle ID matches the selected app.
- In metadata-only mode, honor an explicitly requested semantic version. Historical versions are valid even when the current app version is newer; verify their facts against the matching tag/commit or durable release evidence, without changing the checkout's version or substituting current app facts.
- When a metadata-only request omits the version, infer it from the equal validation and release `MARKETING_VERSION` values for the selected native app target; confirm resolved `xcodebuild -showBuildSettings` and the verified bundle ID when practical. This is a settings lookup, not a build.
- Do not use `CURRENT_PROJECT_VERSION` or test-target versions as the App Store version.
- Sort or compare version directories semantically, never lexically.
- Verify the selected release against its intended commit or working-tree changes. If a matching tag already exists, also inspect that release evidence; never substitute an unrelated newer release.

### Build the copy

- Treat user-provided approved copy and existing version files as source material. Preserve historical wording, punctuation, numbers, bullets, disclaimers, and URLs exactly unless the user explicitly requests a revision.
- Do not silently overwrite an existing version. If it represents published history, require an explicit revision request; update that version in place rather than making timestamped duplicates. When all required files already exist and fit the selected release, validate and reuse them.
- `Description` describes the whole customer-facing offering for that version. Start from the most recent approved description and change only facts affected by the selected release.
- `What's New in This Version` describes verified user-facing changes since the previous published semantic version. Inspect the selected tag/commit, prior published release, merged product changes, and trusted user-provided release copy. Omit internal model, analytics, tooling, and implementation details unless customers directly benefit from them.
- Verify mutable counts, access rules, localized feature names, and release-specific claims against the selected release's code or durable evidence. Use `codebase-memory` for structural code questions when available; otherwise inspect the selected app checkout with local search and file tools.
- Verify time-sensitive claims against the selected release date. Preserve approved legal/non-affiliation disclaimers and Terms/Privacy URLs when carrying a description forward; do not invent certifications or affiliations.
- Localize meaning naturally for every selected locale while keeping feature scope and numbers aligned. Use the `•` bullet character in copy-ready text.
- Inside App Store field bodies in every selected locale, place the first list item immediately on the line after its section heading, with no blank line between them. Keep blank lines between sections. For example:

  ```text
  FEATURES
  • First verified feature
  • Second verified feature
  ```

  This applies to copy-ready field text, not the Markdown wrapper headings `## Description` and `## What's New in This Version`. Preserve existing historical files unless a formatting revision is explicitly requested.

### Validate the metadata

Before finalizing, re-check Apple's current official [Platform version information](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information). Use the current field limits and plain-text formatting rules from that source.

Count Unicode characters in each field body, including its line breaks but excluding the Markdown heading. Report two counts per locale for each version.

- For a new draft over the current limit, shorten it without dropping verified facts or changing meaning.
- For approved historical copy over a limit, report the conflict and do not silently edit it.
- Confirm every version has both fields for every selected locale, the two headings occur exactly once per locale file, and no Markdown escape artifacts remain in copy (`\` line continuations or `\:` in URLs).
- Check that section headings inside newly prepared field bodies are followed directly by their lists, without an intervening blank line.
- Check that every bullet starts its own line and that no line contains multiple list items or literal `\n` separators in place of actual line breaks.

Return links to every selected locale file and, when requested, reproduce the two copy-ready fields for each language. Metadata preparation alone does not authorize a commit, push, edit to App Store Connect, GitHub Release, or build upload. Continue to the authorized release stages only after this step is complete.

## Step 3 — Validate and land the release changes

After a version edit and before any tag or release publication:

1. Confirm the selected validation and release configurations report the intended marketing version, build number, bundle ID, and application target.
2. Run a simulator build with code signing disabled using the resolved `-project` or `-workspace`, scheme, and release configuration. For example, substitute the established values in:

   ```bash
   xcodebuild -workspace '<resolved workspace>.xcworkspace' \
     -scheme '<resolved scheme>' \
     -configuration '<resolved release configuration>' \
     -destination 'generic/platform=iOS Simulator' \
     CODE_SIGNING_ALLOWED=NO build
   ```

   Use `-project '<resolved project>.xcodeproj'` for project-based builds. If the scheme also builds other app targets, confirm the selected native application's result separately.
3. Treat the exit status as authoritative and, when available, verify the selected built app's `Info.plist` version, build number, and bundle identifier.

Use DerivedData and dependency directories outside the repository when isolation is needed. Apply only dependency workarounds supported by this project's instructions or diagnosed logs; do not modify project settings to hide an unrelated failure.

Xcode may rewrite the shared scheme. Revert only a diff demonstrably caused by this run; preserve all pre-existing user changes.

After successful validation, commit or push only if those stages are authorized. When step 2 ran, commit its generated Markdown documents together with the version change:

- Explicitly stage only the resolved version-setting files and every selected locale metadata file, including newly created untracked files. Do not rely on `git commit -a`, which omits new documents.
- Review the staged diff and confirm all selected locale files are included in the version commit. If unchanged metadata documents were already committed, verify they exist at the intended release commit instead of creating an empty change.
- After an authorized push, verify the remote release commit contains the version change and all selected metadata documents before creating the release tag.

Follow the selected application's established version-commit style and language.

Re-check the remote before every authorized push. Never merge a pending version PR merely because publication was requested. In publish-current mode, validation does not authorize a commit or branch push.

## Step 4 — Tag and publish when authorized

Build release notes from actual user-facing changes since the most recent published release. Omit internal tooling churn unless it changes the shipped product. Put the notes file outside the repository and remove it after verification.

Write bulleted release notes as Markdown lists, with a blank line before each list and one `- ` item per line. Pass the file through `--notes-file` to preserve actual line breaks; after publication, read back the release body and verify that the lists retain their item boundaries.

For a new publication:

1. Create the verified annotated tag with the project-conventional tag name and message at `<verified-release-commit>`.
2. Push only the exact verified tag ref. If the push fails, do not create the release.
3. Create the stable release with the verified tag, repository-standard title, and curated notes, for example:

   ```bash
   gh release create <verified-tag> \
     --verify-tag \
     --target <release-branch> \
     --title "<verified release title>" \
     --notes-file /tmp/release-notes.md
   ```

If the tag was already published correctly and only release creation previously failed, skip tag creation and push, then retry only `gh release create`.

If a later step fails, preserve published facts. Do not delete a pushed tag to hide a partial release.

## Step 5 — Archive and distribute through the deterministic CLI

Read [references/app-store-build.md](references/app-store-build.md) before this stage. It contains the command examples, signing/authentication requirements, persistent output layout, exit-code contract, upload receipt behavior, and recovery rules. Use [scripts/app_store_build.py](scripts/app_store_build.py) for `inspect`, `archive`, `verify-archive`, `export`, `verify-ipa`, and `upload`; do not reconstruct its shell commands or verification logic. Run only the requested archive/export/upload outcomes. A full pipeline request through upload authorizes this stage without another confirmation; archive-only and GitHub-only requests do not authorize an upload.

### Pin the same release source

- For the full release pipeline, pass the exact clean release checkout with `--repo`, plus the resolved project/workspace, scheme, configurations, and app target when needed; pass bundle ID, marketing version, build number, and team as assertions. Use the CLI from this skill's directory even when archiving a different managed worktree.
- For the full pipeline, require `inspect` to report the verified release commit and no local checkout changes. When step 4 ran, that commit must equal the remote tag's dereferenced commit. Do not archive a newer branch tip or use `--include-dirty-source` to hide a mismatch. For standalone requests, follow the reference's source selection and existing-archive provenance checks; a GitHub tag is not required.
- Look for an existing archive/receipt for this release in the known persistent output directory before creating another artifact. Reuse it only after `verify-archive` passes and its recorded source commit, clean checkout state, container/scheme/target/configuration selection, version/build, bundle ID, and team match the release. Unknown provenance does not establish a match.
- Preserve `CURRENT_PROJECT_VERSION`. If App Store Connect confirms that the version/build was already used, follow the reference's build-number resolution; do not silently renumber a tagged release or move its tag.

### Execute the requested distribution outcome

1. Reuse the verified archive or invoke `archive` with a new persistent `--output-dir` outside the repository. Require exit code `0`, `status=archived` or a successful `verify-archive`, valid signatures/profile, and matching app dSYM UUIDs before proceeding. Keep the resulting `archive-manifest.json`, `.xcarchive`, dSYMs, and logs.
2. When a local IPA was requested, run `export` with the verified signing style and a fresh output directory; retain the verified IPA, SHA-256, export options, and result JSON. An upload-only request can proceed directly from a verified archive to `upload`.
3. For an authorized upload, verify the existing App Store Connect app/bundle/team and numeric app ID, and check the version/build availability when possible. Pass these verified inputs to `upload` with `--confirm-upload`, the same archive and identity, the actual signing style, a fresh output directory, and `--remote-build-check available` or `unverified` as appropriate. Never invent availability or an app ID.
4. Respect the CLI's upload receipt. `already_uploaded` completes the transport stage without another upload. Exit code `5`, interruption, or a receipt with an unknown outcome requires reconciliation; do not delete receipts, relocate/rebuild an archive, or change upload tools to bypass duplicate protection.
5. After successful transport, check the exact version/build's processing state through an authenticated App Store Connect surface when available. Distinguish upload acceptance from Processing, Complete, and rejection. A pending processing state is reported accurately; it does not justify another upload.

Preserve any verified GitHub Release and completed archive if Apple distribution fails, and report which stages succeeded and which need attention. Follow the reference's bounded correction/retry rules; do not repeat the simulator build solely to archive the same source. App Review submission, tester distribution, public App Store release, and metadata edits remain separate actions.

## Final verification

Verify and report the results of requested stages only. For metadata-only mode, return all selected locale-file links, both character counts per locale, and any copy-validation conflicts; do not run other stages to fill out this report. For the release pipeline, report as applicable:

- release branch and exact commit SHA;
- app marketing version and separate build number;
- resolved validation/release settings and Release build result;
- links to all selected App Store metadata files and both field character counts per locale when step 2 ran;
- remote annotated tag object and its dereferenced commit;
- GitHub Release tag, title, body, target branch, stable status, URL, and Latest status when intended;
- when step 5 ran: exact archive source/version/build/team, signing and dSYM verification, absolute links to the archive and JSON/logs, and requested IPA path/SHA-256;
- when upload was requested: receipt/transport result, App Store Connect app/build link, actual processing state or its verification limit, and material SDK-symbol warnings;
- clean release worktree and removal of temporary notes;
- non-blocking warnings and deliberately unperformed stages.

A GitHub Release request alone never implies an archive, App Store upload, version bump, branch push, or merge; perform those stages only when separately and explicitly requested.
