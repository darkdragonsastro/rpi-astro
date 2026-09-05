#!/usr/bin/env python3
"""Create a fresh signed APT snapshot with both supported suites."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

SUITES = ("bookworm", "trixie")


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def publish(packages, output, fingerprint, base_url, max_bytes=900_000_000):
    if not re.fullmatch(r"[A-Fa-f0-9]{40}", fingerprint):
        raise ValueError("Use the full 40-character signing key fingerprint")
    if not base_url.startswith("https://") or any(c.isspace() for c in base_url):
        raise ValueError("The public repository URL must use HTTPS and contain no whitespace")
    output.mkdir(parents=True, exist_ok=False)
    # Keep reprepro's database and configuration outside the public site.
    database = output.parent / f"{output.name}-database"
    database.mkdir(exist_ok=False)
    conf = database / "conf"
    conf.mkdir()
    (conf / "distributions").write_text("\n\n".join(
        f"Origin: RPi-Astro\nLabel: RPi Astro\nCodename: {suite}\nSuite: {suite}\n"
        f"Architectures: arm64 source\nComponents: main\n"
        f"Description: Astronomy software for Raspberry Pi OS {suite} arm64\n"
        f"SignWith: {fingerprint}\n" for suite in SUITES
    ))
    command = ["reprepro", "--basedir", database, "--outdir", output,
               "--export=never", "--keepunreferencedfiles"]
    inventory = {}
    for suite in SUITES:
        folder = packages / suite
        binaries, sources = sorted(folder.glob("*.deb")), sorted(folder.glob("*.dsc"))
        if not binaries or not sources:
            raise ValueError(f"Missing binaries or corresponding sources for {suite}")
        # Input comes only from the build jobs of this workflow run, never PR artifacts.
        for source in sources:
            run(*command, "-C", "main", "includedsc", suite, source)
        for binary in binaries:
            architecture = subprocess.check_output(
                ["dpkg-deb", "-f", str(binary), "Architecture"], text=True
            ).strip()
            if architecture not in ("arm64", "all"):
                raise ValueError(f"Wrong architecture in {binary}: {architecture}")
            run(*command, "-C", "main", "includedeb", suite, binary)
        inventory[suite] = [p.name for p in binaries]
        manifest = folder / "sources.json"
        if manifest.exists():
            shutil.copy2(manifest, output / f"sources-{suite}.json")
    run(*(arg for arg in command if arg != "--export=never"), "export")
    with (output / "rpi-astro.asc").open("wb") as key:
        run("gpg", "--batch", "--armor", "--export", fingerprint, stdout=key)
    if not (output / "rpi-astro.asc").stat().st_size:
        raise ValueError("The public signing key was not exported")
    (output / ".nojekyll").touch()
    (output / "packages.json").write_text(json.dumps(inventory, indent=2) + "\n")
    install = Path(__file__).with_name("install-repository.sh").read_text()
    # Installation is a downloaded, inspectable script with explicit origin and key pin.
    install = install.replace("@BASE_URL@", base_url.rstrip("/")).replace("@FINGERPRINT@", fingerprint.upper())
    (output / "install-repository.sh").write_text(install)
    rows = "".join(f"<h2>{suite} / arm64</h2><ul>" + "".join(
        f"<li>{html.escape(name)}</li>" for name in names
    ) + "</ul>" for suite, names in inventory.items())
    (output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RPi Astro APT repository</title><body>'
        '<h1>RPi Astro</h1><p>Astronomy packages for 64-bit Raspberry Pi OS.</p>'
        '<p>Supports Bookworm and Trixie. INDI core, KStars/Ekos, StellarSolver and libXISF.</p>'
        '<p>Download and inspect <a href="install-repository.sh">the repository setup script</a>, '
        'then run it with sudo. Install with <code>sudo apt install indi-bin kstars</code>.</p>'
        f'<p>Signing key: <code>{fingerprint.upper()}</code> '
        '<a href="rpi-astro.asc">Public key</a></p>'
        '<p>Source packages are available with <code>apt source</code>. '
        'Third-party vendor SDK drivers and large plate-solving index sets are not included.</p>'
        f'{rows}</body></html>\n'
    )
    size = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
    if size > max_bytes:
        raise ValueError(f"Site is {size:,} bytes; limit is {max_bytes:,}. Do not deploy.")
    print(f"Signed site: {size:,} bytes; signing key {fingerprint.upper()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("site"))
    parser.add_argument("--fingerprint", default=os.environ.get("APT_SIGNING_FINGERPRINT"), required=False)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    if not args.fingerprint:
        parser.error("--fingerprint or APT_SIGNING_FINGERPRINT is required")
    publish(args.packages.resolve(), args.output.resolve(), args.fingerprint, args.base_url)
