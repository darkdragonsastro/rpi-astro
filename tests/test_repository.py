"""Exercise real Debian metadata, signatures, suite isolation and APT downloads."""

import functools
import http.server
import importlib.util
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
                    folder = root / "packages" / suite
                    folder.mkdir(parents=True)
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
                site = root / "site"
                repository.publish(root / "packages", site, fingerprint, "https://example.invalid/astro")
                self.assertFalse((site / "conf").exists())
                self.assertFalse((site / "db").exists())
                self.assertIn(fingerprint, (site / "install-repository.sh").read_text())
                for suite in repository.SUITES:
                    release = site / "dists" / suite / "InRelease"
                    run("gpg", "--batch", "--verify", release)
                    self.assertIn(f"Codename: {suite}", release.read_text())
                    packages = site / "dists" / suite / "main" / "binary-arm64" / "Packages"
                    self.assertIn(f"Version: 1.0+{suite}", packages.read_text())
                    other = "bookworm" if suite == "trixie" else "trixie"
                    self.assertNotIn(f"Version: 1.0+{other}", packages.read_text())

                handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    for suite in repository.SUITES:
                        apt = root / f"apt-{suite}"
                        (apt / "lists" / "partial").mkdir(parents=True)
                        (apt / "archives" / "partial").mkdir(parents=True)
                        (apt / "status").touch()
                        sources = apt / "sources.list"
                        sources.write_text(
                            f"deb [arch=arm64 signed-by={site}/rpi-astro.asc] "
                            f"http://127.0.0.1:{server.server_port} {suite} main\n"
                        )
                        options = ["-o", f"Dir::Etc::sourcelist={sources}",
                                   "-o", "Dir::Etc::sourceparts=-",
                                   "-o", f"Dir::State::lists={apt}/lists",
                                   "-o", f"Dir::State::status={apt}/status",
                                   "-o", f"Dir::Cache::archives={apt}/archives",
                                   "-o", "APT::Architecture=arm64",
                                   "-o", "APT::Get::List-Cleanup=0"]
                        run("apt-get", *options, "update", "--error-on=any")
                        run("apt-get", *options, "download", f"rpi-astro-test=1.0+{suite}", cwd=apt)
                        self.assertEqual(len(list(apt.glob("*.deb"))), 1)
                        release = site / "dists" / suite / "InRelease"
                        release.write_text(release.read_text().replace("Origin: RPi-Astro", "Origin: Tampered!"))
                        with self.assertRaises(subprocess.CalledProcessError):
                            run("apt-get", *options, "update", "--error-on=any")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
                with self.assertRaises(ValueError):
                    repository.publish(root / "missing", root / "empty-site", fingerprint,
                                       "https://example.invalid")
            finally:
                run("gpgconf", "--kill", "all")
                if previous is None:
                    os.environ.pop("GNUPGHOME", None)
                else:
                    os.environ["GNUPGHOME"] = previous


if __name__ == "__main__":
    unittest.main()
