import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("build", ROOT / "scripts/build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


@unittest.skipUnless(shutil.which("git") and shutil.which("xz"), "Requires git and xz")
class ComponentTests(unittest.TestCase):
    def test_pinned_component_and_debian_source_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / "upstream"
            upstream.mkdir()
            (upstream / "sdk").mkdir()
            (upstream / "sdk/library.bin").write_bytes(b"pinned vendor library\x00")
            (upstream / "sdk/LICENSE").write_text("Keep this vendor notice\n")
            (upstream / "unrelated").write_text("Must not be included\n")
            subprocess.run(["git", "init", str(upstream)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
            subprocess.run(["git", "-C", str(upstream), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "-c",
                            "core.hooksPath=/dev/null", "commit", "-m", "fixture"], check=True, capture_output=True)
            commit = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
            checkout = root / "checkout"
            subprocess.run(["git", "init", str(checkout)], check=True, capture_output=True)
            source = root / "fixture-1.0"
            source.mkdir()
            (source / "README").write_text("Main source\n")
            with tarfile.open(root / "fixture_1.0.orig.tar.xz", "w:xz") as archive:
                archive.add(source, arcname=source.name)
            package = {"name": "fixture", "version": "1.0", "url": str(upstream),
                       "components": [{"name": "qhybookworm", "commit": commit, "paths": ["sdk"]}]}
            build.add_components(package, checkout, root, source)
            self.assertEqual((source / "qhybookworm/sdk/library.bin").read_bytes(), b"pinned vendor library\x00")
            self.assertFalse((source / "qhybookworm/unrelated").exists())
            self.assertTrue((root / "fixture_1.0.orig-qhybookworm.tar.xz").is_file())
            if not shutil.which("dpkg-source"):
                return
            debian = source / "debian"
            (debian / "source").mkdir(parents=True)
            (debian / "source/format").write_text("3.0 (quilt)\n")
            (debian / "control").write_text(
                "Source: fixture\nSection: science\nPriority: optional\n"
                "Maintainer: Test <test@example.invalid>\nStandards-Version: 4.6.2\n\n"
                "Package: fixture\nArchitecture: any\nDescription: fixture\n")
            (debian / "rules").write_text("#!/usr/bin/make -f\n%:\n\ttrue\n")
            (debian / "rules").chmod(0o755)
            (debian / "changelog").write_text(
                "fixture (1.0-1) bookworm; urgency=low\n\n  * Test.\n\n"
                " -- Test <test@example.invalid>  Fri, 04 Sep 2026 12:00:00 +0000\n")
            subprocess.run(["dpkg-source", "-b", str(source)], cwd=root, check=True, capture_output=True)
            dsc = root / "fixture_1.0-1.dsc"
            self.assertIn("orig-qhybookworm.tar.xz", dsc.read_text())
            subprocess.run(["dpkg-source", "--no-check", "-x", str(dsc), str(root / "rebuilt")],
                           check=True, capture_output=True)
            self.assertEqual((root / "rebuilt/qhybookworm/sdk/library.bin").read_bytes(), b"pinned vendor library\x00")

    @unittest.skipUnless(shutil.which("dpkg-parsechangelog") and Path("/usr/share/dpkg/architecture.mk").exists(),
                         "Requires Debian packaging tools")
    def test_fallback_selected_only_for_bookworm_amd64(self):
        rules = ROOT / "packaging/indi-3rdparty-libs/rules"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "debian").mkdir()
            for suite in ("bookworm", "trixie"):
                (root / "debian/changelog").write_text(
                    f"fixture (1.0-1) {suite}; urgency=low\n\n  * Test.\n\n"
                    " -- Test <test@example.invalid>  Fri, 04 Sep 2026 12:00:00 +0000\n")
                for architecture in ("arm64", "amd64"):
                    result = subprocess.check_output(
                        ["make", "-n", "-f", str(rules), f"DEB_HOST_ARCH={architecture}", "override_dh_auto_configure"],
                        cwd=root, text=True)
                    expected = "ON" if (suite, architecture) == ("bookworm", "amd64") else "OFF"
                    self.assertIn(f"-DRPI_ASTRO_QHY_BOOKWORM={expected}", result)
