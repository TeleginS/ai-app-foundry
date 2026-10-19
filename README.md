# AI App Foundry

AI-powered development toolkit for iOS apps and backends, with reusable agents, skills, and workflows for planning, coding, review, testing, and releases.

## Included in 0.1.0

- **[publish-app-release](skills/publish-app-release/SKILL.md)**: prepare App Store Description and What's New in Russian, English, and Spanish; manage authorized versioning and GitHub release stages; create and verify signed archives; export IPAs; upload to App Store Connect.
- A standard-library Python CLI with signing, identity, provenance, dSYM, and duplicate-upload checks.
- Offline tests that use fake external tools and never build, sign, or upload a real app.
- Client packaging for Codex, Claude Code, and DeepSeek Harness: the DSH plugin bundle in `package.json`, `cordis.patch.yml`, and [`dsh/index.mjs`](dsh/index.mjs) serves the same `skills/` directory in DSH sessions.

The initial release skill is specific to [TrafficTestApp](https://github.com/TeleginS/TrafficRulesApp): project `TrafficTestApp.xcodeproj`, scheme `TrafficTestApp`, bundle `com.telegins.RUSAutoescuelaDGT`, and RU/EN/ES metadata. It is not yet a general-purpose release tool for arbitrary apps. Backend skills are planned; none are included in this version.

## Install in Codex

Add this repository as a plugin marketplace:

```bash
codex plugin marketplace add TeleginS/ai-app-foundry
```

Then open the plugin browser, find **AI App Foundry**, and install it. Adding a marketplace makes its plugin discoverable; it does not itself install or activate the plugin. Available installation controls depend on the Codex client and workspace policy.

The repository includes a portable `plugin.json`, a Codex compatibility manifest at `.codex-plugin/plugin.json`, and a marketplace catalog at `.agents/plugins/marketplace.json`. No MCP server or service connection is bundled.

See the official [plugin packaging and installation documentation](https://developers.openai.com/plugins/build/plugins).

## Install in Claude Code

Install the plugin from this repository's marketplace (Claude Code 2.1.275 or later):

```text
/plugin install ai-app-foundry --marketplace TeleginS/ai-app-foundry
```

On older versions, add the marketplace first and then install:

```text
/plugin marketplace add TeleginS/ai-app-foundry
/plugin install ai-app-foundry@ai-app-foundry
```

The Claude Code manifests live in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`; they share the same `skills/` directory with Codex. See the [Claude Code plugin documentation](https://code.claude.com/docs/en/plugins).

## Install in DeepSeek Harness

DSH installs skills through plugin bundles. This repository is also one: the root `package.json` declares `dsh.bundle.patch`, and [`dsh/index.mjs`](dsh/index.mjs) registers a bundled skill provider, so every skill under `skills/` appears in the DSH session catalog. Add the repository to the profile your DSH app boots (for example `web`):

```bash
dsh plugin --profile web add github:TeleginS/ai-app-foundry
```

To install from a local checkout instead, pass its absolute path to the same command, for example `dsh plugin --profile web add /absolute/path/to/ai-app-foundry`.

The bundle needs a profile that mounts the skill registry; profiles built from `@deepseek-ai/dsh-base`, including the shipped `web`, `headless`, `acp`, and `sdk` profiles, do. It contributes only a skill provider: no tools, MCP servers, network connections, credentials, or dsh peer dependencies. Installed bundles are listed on DSH's **Plugins** page and can be disabled, removed, or installed from there as well. Remove it with:

```bash
dsh plugin --profile web remove ai-app-foundry
```

DSH also discovers local skills without a bundle: link the skill directory into `~/.agents/skills/` (shared agent configuration) or into a project's `.agents/skills/` or `.dsh/skills/`, and DSH picks it up on the next step. That is the quickest way to try the skill from a checkout before installing the bundle.

## Use

Open the TrafficTestApp checkout and invoke the installed **Publish App Release** skill. For example, in Codex:

```text
Use $publish-app-release to prepare App Store metadata for the current version in RU/EN/ES.
```

```text
Use $publish-app-release to create a signed archive of the current version. Archive only.
```

In Claude Code, invoke it as `/ai-app-foundry:publish-app-release` or describe the task and Claude loads the skill automatically:

```text
/ai-app-foundry:publish-app-release prepare App Store metadata for the current version in RU/EN/ES
```

In DSH, describe the task and the agent loads the skill from its catalog, or invoke it explicitly by name:

```text
/publish-app-release prepare App Store metadata for the current version in RU/EN/ES
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

The DSH plugin has its own offline tests; they mount the plugin with a fake skill registry and check the bundled catalog:

```bash
node --test
```

Add further skills as `skills/<skill-name>/SKILL.md`, with supporting resources inside that skill's directory. The DSH provider discovers them automatically; no bundle edit is needed. Update the plugin version in all manifests together when publishing package changes: `plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and the DSH bundle's root `package.json`. Validate the Claude Code manifests with:

```bash
claude plugin validate .
```

## Origin

The release skill was imported from [TrafficRulesApp at e873cd6](https://github.com/TeleginS/TrafficRulesApp/tree/e873cd640058a75d29b8d9ab37fdfcf4b6787d7b/.agents/skills/publish-app-release), including its bullet-formatting rules, references, CLI, and offline tests. The packaged copy adjusts resource paths and repository selection for installation outside the app checkout. The original repository skill remains in place.
