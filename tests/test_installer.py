"""Exercise the setup script with isolated paths and mocked system commands."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class InstallerTests(unittest.TestCase):
    def run_installer(self, suite, architecture):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        commands = root / "commands"
        commands.mkdir()
        fingerprint = "A" * 40
        mocks = {
            "dpkg": f"echo {architecture}\n",
            "apt-get": f"echo apt >> '{root}/calls'\n",
            "curl": 'while [ "$1" != "-o" ]; do shift; done\nprintf key > "$2"\n',
            "gpg": f"printf 'pub:::::::::\\nfpr:::::::::{fingerprint}:\\n'\n",
        }
        for name, body in mocks.items():
            path = commands / name
            path.write_text("#!/bin/sh\nset -eu\n" + body)
            path.chmod(0o755)
        (root / "os-release").write_text(f"VERSION_CODENAME={suite}\n")
        (root / "sources.list.d").mkdir()
        script = (Path(__file__).resolve().parents[1] / "scripts/install-repository.sh").read_text()
        script = (script.replace("$EUID != 0", "0 != 0")
                  .replace("/etc/os-release", str(root / "os-release"))
                  .replace("/etc/apt/", str(root) + "/")
                  .replace("@BASE_URL@", "https://example.invalid")
                  .replace("@FINGERPRINT@", fingerprint))
        env = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}")
        result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
        return root, result, script, env

    def test_detects_architecture_and_refuses_overwrite(self):
        for suite in ("bookworm", "trixie"):
            for architecture in ("arm64", "amd64"):
                with self.subTest(suite=suite, architecture=architecture):
                    root, result, script, env = self.run_installer(suite, architecture)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    sources = root / "sources.list.d/rpi-astro.sources"
                    before = sources.read_bytes()
                    self.assertIn(f"Architectures: {architecture}\n", before.decode())
                    self.assertIn(f"Suites: {suite}\n", before.decode())
                    result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("already configured", result.stderr)
                    self.assertEqual(sources.read_bytes(), before)

    def test_rejects_unsupported_targets_before_apt(self):
        for suite, architecture in (("bookworm", "armhf"), ("trixie", "i386"), ("jammy", "amd64")):
            with self.subTest(suite=suite, architecture=architecture):
                root, result, _, _ = self.run_installer(suite, architecture)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "calls").exists())
                self.assertFalse((root / "sources.list.d/rpi-astro.sources").exists())
