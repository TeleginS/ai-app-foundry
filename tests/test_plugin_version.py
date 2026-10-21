"""Offline tests for the plugin version script. They edit copies, never the checkout."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/plugin_version.py"
spec = importlib.util.spec_from_file_location("plugin_version", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
FILES = sorted({path for path, _, _ in cli.LOCATIONS})


class PluginVersionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        for path in FILES:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / path, self.root / path)
        self.version = cli.current_version(self.root)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def next_minor(self):
        major, minor, _ = cli.parse(self.version)
        return f"{major}.{minor + 1}.0"

    def test_checkout_versions_agree(self):
        self.assertEqual(cli.current_version(ROOT), self.version)
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_bump_updates_every_location_and_nothing_else(self):
        before = {path: (self.root / path).read_text(encoding="utf-8") for path in FILES}
        new = self.next_minor()
        code, out, _ = self.run_cli("bump", new)
        self.assertEqual(code, 0)
        self.assertEqual(out.count(f"{self.version} -> {new}"), len(cli.LOCATIONS))
        self.assertEqual({version for _, version in cli.read_versions(self.root)}, {new})
        for path in FILES:
            after = (self.root / path).read_text(encoding="utf-8")
            self.assertEqual(after.replace(new, self.version), before[path], path)
            if path.endswith(".json"):
                json.loads(after)

    def test_bump_rejects_invalid_or_non_increasing_versions(self):
        major, minor, patch = cli.parse(self.version)
        for version in (self.version, f"{major}.{minor}", f"v{self.next_minor()}",
                        f"{major}.{minor}.{patch}-beta", "0.0.1"):
            with self.subTest(version=version):
                code, _, err = self.run_cli("bump", version)
                self.assertEqual(code, 1)
                self.assertIn("error:", err)
                self.assertEqual(cli.current_version(self.root), self.version)

    def test_mismatch_is_reported_and_blocks_bump(self):
        path = self.root / ".codex-plugin/plugin.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = "9.9.9"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        code, _, err = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn(".codex-plugin/plugin.json: 9.9.9", err)
        self.assertEqual(self.run_cli("bump", "10.0.0")[0], 1)
        self.assertNotIn("10.0.0", (self.root / "package.json").read_text(encoding="utf-8"))

    def test_marketplace_version_must_belong_to_this_plugin(self):
        path = self.root / ".claude-plugin/marketplace.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["plugins"][0]["name"] = "another-plugin"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        code, _, err = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("marketplace does not list ai-app-foundry", err)


if __name__ == "__main__":
    unittest.main()
