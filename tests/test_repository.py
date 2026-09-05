"""Exercise real Debian metadata, signatures, suite isolation and APT downloads."""

import functools
import http.server
import importlib.util
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location(
    "repository", Path(__file__).resolve().parents[1] / "scripts/repository.py"
)
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, **kwargs).stdout


@unittest.skipUnless(all(shutil.which(tool) for tool in ("reprepro", "gpg", "dpkg-deb", "dpkg-source", "apt-get")),
                     "Requires Debian packaging tools")
class RepositoryTest(unittest.TestCase):
    def test_signed_archive_and_apt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            gnupg = root / "gnupg"
            gnupg.mkdir(mode=0o700)
            previous = os.environ.get("GNUPGHOME")
            os.environ["GNUPGHOME"] = str(gnupg)
            try:
                run("gpg", "--batch", "--passphrase", "", "--quick-generate-key",
                    "Repository test <test@example.invalid>", "ed25519", "sign", "1d")
                fingerprint = next(line.split(":")[9] for line in
                                   run("gpg", "--with-colons", "--list-keys").splitlines()
                                   if line.startswith("fpr:"))
                for suite in repository.SUITES:
                    folder = root / "packages" / suite / "arm64"
                    folder.mkdir(parents=True)
                    (folder / "sources.json").write_text('{"revision": 3}\n')
                    version = f"1.0+{suite}"
                    source = folder / "source"
                    (source / "debian" / "source").mkdir(parents=True)
                    (source / "debian" / "source" / "format").write_text("3.0 (native)\n")
                    control = (
                        "Source: rpi-astro-test\nSection: science\nPriority: optional\n"
                        "Maintainer: Test <test@example.invalid>\nStandards-Version: 4.6.2\n\n"
                        "Package: rpi-astro-test\nArchitecture: all\nDescription: test fixture\n"
                    )
                    (source / "debian" / "control").write_text(control)
                    (source / "debian" / "rules").write_text("#!/usr/bin/make -f\n%:\n\ttrue\n")
                    (source / "debian" / "rules").chmod(0o755)
                    (source / "debian" / "changelog").write_text(
                        f"rpi-astro-test ({version}) {suite}; urgency=low\n\n"
                        "  * Test.\n\n -- Test <test@example.invalid>  Fri, 04 Sep 2026 12:00:00 +0000\n"
                    )
                    run("dpkg-source", "-b", source, cwd=folder)
                    binary = folder / "binary"
                    (binary / "DEBIAN").mkdir(parents=True)
                    (binary / "DEBIAN" / "control").write_text(
                        f"Package: rpi-astro-test\nVersion: {version}\nArchitecture: all\n"
                        "Section: science\nPriority: optional\n"
                        "Maintainer: Test <test@example.invalid>\nDescription: test fixture\n"
                    )
                    run("dpkg-deb", "--build", binary, folder / f"rpi-astro-test_{version}_all.deb")
                    other_folder = folder.parent / "amd64"
                    other_folder.mkdir()
                    shutil.copy2(folder / "sources.json", other_folder)
                    shutil.copy2(folder / f"rpi-astro-test_{version}_all.deb", other_folder)
                    for architecture in repository.ARCHITECTURES:
                        target = folder.parent / architecture
                        (binary / "DEBIAN" / "control").write_text(
                            f"Package: rpi-astro-native\nSource: rpi-astro-test\nVersion: {version}\n"
                            f"Architecture: {architecture}\nSection: science\nPriority: optional\n"
                            "Maintainer: Test <test@example.invalid>\nDescription: native test fixture\n"
                        )
                        run("dpkg-deb", "--build", binary, target / f"rpi-astro-native_{version}_{architecture}.deb")
                site = root / "site"
                repository.publish(root / "packages", site, fingerprint, "https://example.invalid/astro")
                self.assertFalse((site / "conf").exists())
                self.assertFalse((site / "db").exists())
                self.assertIn(fingerprint, (site / "install-repository.sh").read_text())
                for suite, architecture in itertools.product(repository.SUITES, repository.ARCHITECTURES):
                    release = site / "dists" / suite / "InRelease"
                    run("gpg", "--batch", "--verify", release)
                    self.assertIn(f"Codename: {suite}", release.read_text())
                    packages = site / "dists" / suite / "main" / f"binary-{architecture}" / "Packages"
                    self.assertIn(f"Version: 1.0+{suite}", packages.read_text())
                    self.assertIn(f"Architecture: {architecture}\n", packages.read_text())
                    self.assertIn("Architecture: all\n", packages.read_text())
                    wrong = "amd64" if architecture == "arm64" else "arm64"
                    self.assertNotIn(f"Architecture: {wrong}\n", packages.read_text())
                    other = "bookworm" if suite == "trixie" else "trixie"
                    self.assertNotIn(f"Version: 1.0+{other}", packages.read_text())

                handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    for suite, architecture in itertools.product(repository.SUITES, repository.ARCHITECTURES):
                        apt = root / f"apt-{suite}-{architecture}"
                        (apt / "lists" / "partial").mkdir(parents=True)
                        (apt / "archives" / "partial").mkdir(parents=True)
                        (apt / "status").touch()
                        sources = apt / "sources.list"
                        sources.write_text(
                            f"deb [arch={architecture} signed-by={site}/rpi-astro.asc] "
                            f"http://127.0.0.1:{server.server_port} {suite} main\n"
                        )
                        options = ["-o", f"Dir::Etc::sourcelist={sources}",
                                   "-o", "Dir::Etc::sourceparts=-",
                                   "-o", f"Dir::State::lists={apt}/lists",
                                   "-o", f"Dir::State::status={apt}/status",
                                   "-o", f"Dir::Cache::archives={apt}/archives",
                                   "-o", f"APT::Architecture={architecture}",
                                   "-o", "APT::Get::List-Cleanup=0"]
                        run("apt-get", *options, "update", "--error-on=any")
                        run("apt-get", *options, "download", f"rpi-astro-test=1.0+{suite}", cwd=apt)
                        run("apt-get", *options, "download", f"rpi-astro-native=1.0+{suite}", cwd=apt)
                        self.assertEqual(len(list(apt.glob("*.deb"))), 2)
                        native = next(apt.glob("rpi-astro-native*.deb"))
                        self.assertEqual(run("dpkg-deb", "-f", native, "Architecture").strip(), architecture)
                        release = site / "dists" / suite / "InRelease"
                        original = release.read_bytes()
                        release.write_text(release.read_text().replace("Origin: RPi-Astro", "Origin: Tampered!"))
                        # HTTP dates have one-second precision. Force a changed Last-Modified
                        # so the server returns the modified bytes, not a cache-validating 304.
                        modified = release.stat().st_mtime + 2
                        os.utime(release, (modified, modified))
                        with self.assertRaises(subprocess.CalledProcessError):
                            run("apt-get", *options, "update", "--error-on=any")
                        release.write_bytes(original)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
                with self.assertRaises(ValueError):
                    repository.publish(root / "missing", root / "empty-site", fingerprint,
                                       "https://example.invalid")
                with self.assertRaisesRegex(ValueError, "Do not deploy"):
                    repository.publish(root / "packages", root / "oversized-site", fingerprint,
                                       "https://example.invalid", max_bytes=1)

                folder = root / "packages" / "bookworm"
                # Every target and its pinned manifest must be present.
                amd64 = folder / "amd64"
                amd64.rename(folder / "held")
                with self.assertRaisesRegex(ValueError, "Missing binaries"):
                    repository.collect_suite(folder)
                (folder / "held").rename(amd64)
                manifest = amd64 / "sources.json"
                manifest.write_text('{}\n')
                with self.assertRaisesRegex(ValueError, "Different source manifests"):
                    repository.collect_suite(folder)
                shutil.copy2(folder / "arm64/sources.json", manifest)
                wrong = next((folder / "arm64").glob("*_arm64.deb"))
                shutil.copy2(wrong, amd64)
                with self.assertRaisesRegex(ValueError, "Wrong architecture"):
                    repository.collect_suite(folder)
                (amd64 / wrong.name).unlink()
                shared = next(amd64.glob("*_all.deb"))
                shared.rename(amd64 / "held-all")
                with self.assertRaisesRegex(ValueError, "Missing architecture-independent"):
                    repository.collect_suite(folder)
                (amd64 / "held-all").rename(shared)
                # Identical semantic contents are accepted despite different tar timestamps.
                unpacked = root / "unpacked"
                run("dpkg-deb", "-R", shared, unpacked)
                os.utime(unpacked / "DEBIAN/control", (1234567890, 1234567890))
                run("dpkg-deb", "--build", unpacked, shared)
                repository.collect_suite(folder)
                (unpacked / "different-data").write_text("architecture-specific data is not all\n")
                run("dpkg-deb", "--build", unpacked, shared)
                with self.assertRaisesRegex(ValueError, "Architecture-independent package differs"):
                    repository.collect_suite(folder)
            finally:
                run("gpgconf", "--kill", "all")
                if previous is None:
                    os.environ.pop("GNUPGHOME", None)
                else:
                    os.environ["GNUPGHOME"] = previous


if __name__ == "__main__":
    unittest.main()
