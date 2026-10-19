# AI App Foundry

AI-powered development toolkit for iOS apps and backends, with reusable agents, skills, and workflows for planning, coding, review, testing, and releases.

## Included in 0.1.0

- **[publish-app-release](skills/publish-app-release/SKILL.md)**: prepare App Store Description and What's New in Russian, English, and Spanish; manage authorized versioning and GitHub release stages; create and verify signed archives; export IPAs; upload to App Store Connect.
- A standard-library Python CLI with signing, identity, provenance, dSYM, and duplicate-upload checks.
- Offline tests that use fake external tools and never build, sign, or upload a real app.

The initial release skill is specific to [TrafficTestApp](https://github.com/TeleginS/TrafficRulesApp): project `TrafficTestApp.xcodeproj`, scheme `TrafficTestApp`, bundle `com.telegins.RUSAutoescuelaDGT`, and RU/EN/ES metadata. It is not yet a general-purpose release tool for arbitrary apps. Backend skills are planned; none are included in this version.

## Install in Codex

Add this repository as a plugin marketplace:

```bash
codex plugin marketplace add TeleginS/ai-app-foundry
```

Then open the plugin browser, find **AI App Foundry**, and install it. Adding a marketplace makes its plugin discoverable; it does not itself install or activate the plugin. Available installation controls depend on the Codex client and workspace policy.

The repository includes a portable `plugin.json`, a Codex compatibility manifest at `.codex-plugin/plugin.json`, and a marketplace catalog at `.agents/plugins/marketplace.json`. No MCP server or service connection is bundled.

See the official [plugin packaging and installation documentation](https://developers.openai.com/plugins/build/plugins).

## Use

Open the TrafficTestApp checkout and invoke the installed **Publish App Release** skill. For example:

```text
Use $publish-app-release to prepare App Store metadata for the current version in RU/EN/ES.
```

```text
Use $publish-app-release to create a signed archive of the current version. Archive only.
```

Only requested stages run. Installing this plugin does not publish a release, upload a build, change App Store metadata, or submit an app for review.

For direct CLI use, resolve `SKILL_DIR` to the installed `skills/publish-app-release` directory and pass the application checkout explicitly:

```bash
python3 "$SKILL_DIR/scripts/app_store_build.py" inspect \
  --repo /absolute/path/to/TrafficRulesApp
```

The CLI defaults to the current working directory when `--repo` is omitted. It never derives the app repository from the plugin cache path. Use absolute paths for installed scripts; do not assume they exist inside the application checkout.

Archive/export/upload requires macOS, Xcode, Python 3.9+, and an appropriate signing account. GitHub publication requires Git and authenticated GitHub CLI access. App Store Connect uploads require the existing app record and appropriate Apple access. Credentials and signing artifacts are not included. Codebase Memory can assist source inspection when installed; it is optional for this package.

## Develop and validate

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/publish-app-release/tests -v
```

Add further skills as `skills/<skill-name>/SKILL.md`, with supporting resources inside that skill's directory. Update the plugin version and both manifests together when publishing package changes.

## Origin

The release skill was imported from [TrafficRulesApp at e873cd6](https://github.com/TeleginS/TrafficRulesApp/tree/e873cd640058a75d29b8d9ab37fdfcf4b6787d7b/.agents/skills/publish-app-release), including its bullet-formatting rules, references, CLI, and offline tests. The packaged copy adjusts resource paths and repository selection for installation outside the app checkout. The original repository skill remains in place.
