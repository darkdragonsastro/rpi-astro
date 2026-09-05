#!/usr/bin/env python3
"""Build pinned sources in a disposable, native arm64 or amd64 Debian container."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
from thirdparty import prepare_packaging

ROOT = Path(__file__).resolve().parents[1]
SUITES = {"bookworm": 12, "trixie": 13}


def run(*args, cwd=None, **kwargs):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), cwd=cwd, check=True, **kwargs)


def add_components(package, checkout, work, source):
    """Create pinned supplementary orig archives alongside the main source archive."""
    for component in package.get("components", []):
        if "url" in component:
            add_archive_component(package, component, work, source)
            continue
        run("git", "-C", checkout, "fetch", "--depth=1", package["url"], component["commit"])
        fetched = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "FETCH_HEAD"], text=True
        ).strip()
        if fetched != component["commit"]:
            raise SystemExit(f"Unexpected source revision for {component['name']}")
        supplement = work / f"{package['name']}_{package['version']}.orig-{component['name']}.tar.xz"
        with supplement.open("wb") as stream:
            producer = subprocess.Popen(
                ["git", "-C", str(checkout), "archive", "--format=tar",
                 f"--prefix={component['name']}/", fetched, *component["paths"]], stdout=subprocess.PIPE,
            )
            try:
                run("xz", "-T2", "-6", "--stdout", stdin=producer.stdout, stdout=stream)
            finally:
                producer.stdout.close()
                status = producer.wait()
            if status:
                raise subprocess.CalledProcessError(status, producer.args)
        run("tar", "-xf", supplement, "-C", source)


def add_archive_component(package, component, work, source):
    """Keep a checksum-pinned vendor archive byte-for-byte in the source package."""
    supplement = work / f"{package['name']}_{package['version']}.orig-{component['name']}.tar.gz"
    run("curl", "--fail", "--silent", "--show-error", "--location", "--retry", "3", "--proto", "=https",
        "--proto-redir", "=https", "--output", supplement, component["url"])
    if hashlib.sha256(supplement.read_bytes()).hexdigest() != component["sha256"]:
        raise SystemExit(f"Checksum mismatch for {component['name']}")
    # Debian supplementary orig archives strip their single top-level directory.
    # Extract safely and reproduce that layout; never execute a vendor installer.
    with tempfile.TemporaryDirectory(dir=work) as directory:
        with tarfile.open(supplement) as archive:
            extract_vendor_archive(archive, directory)
        roots = list(Path(directory).iterdir())
        if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
            raise SystemExit(f"Expected one root directory in {component['name']}")
        shutil.move(roots[0], source / component["name"])


def extract_vendor_archive(archive, directory):
    """Validate before extracting, including on Bookworm's older Python tarfile."""
    members = archive.getmembers()
    links = {PurePosixPath(member.name) for member in members if member.issym()}
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts
                or not (member.isfile() or member.isdir() or member.issym())
                or any(parent in links for parent in path.parents)):
            raise ValueError(f"Unsafe vendor archive member: {member.name}")
        if member.issym():
            target = PurePosixPath(member.linkname)
            if target.is_absolute() or ".." in target.parts:
                raise ValueError(f"Unsafe vendor archive link: {member.name}")
    # No special files, traversal, absolute links, or writes through symlink parents.
    archive.extractall(directory)


def build(suite, only=None):
    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    os_release = Path("/etc/os-release").read_text()
    if arch not in ("arm64", "amd64") or f"VERSION_CODENAME={suite}" not in os_release:
        raise SystemExit(f"Run in a native arm64 or amd64 Debian {suite} container")
    manifest = json.loads((ROOT / "sources.json").read_text())
    output = ROOT / "dist" / suite / arch
    output.mkdir(parents=True, exist_ok=True)
    for package in manifest["packages"]:
        name, version = package["name"], package["version"]
        if only and name != only:
            continue
        work = ROOT / "build" / suite / arch / name
        work.mkdir(parents=True, exist_ok=False)
        checkout = work / "checkout"
        run("git", "init", checkout)
        run("git", "-C", checkout, "fetch", "--depth=1", package["url"], package["commit"])
        actual = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "FETCH_HEAD"], text=True
        ).strip()
        if actual != package["commit"]:
            raise SystemExit(f"Unexpected source revision for {name}")
        timestamp = subprocess.check_output(
            ["git", "-C", str(checkout), "show", "-s", "--format=%ct", "FETCH_HEAD"], text=True
        ).strip()
        os.environ["SOURCE_DATE_EPOCH"] = timestamp
        source = work / f"{name}-{version}"
        if package.get("upstream_packaging"):
            # Large SDK trees compress much better with xz, keeping Pages below its cap.
            archive = work / f"{name}_{version}.orig.tar.xz"
            with archive.open("wb") as stream:
                producer = subprocess.Popen(
                    ["git", "-C", str(checkout), "archive", "--format=tar", f"--prefix={source.name}/", "FETCH_HEAD"],
                    stdout=subprocess.PIPE,
                )
                try:
                    run("xz", "-T2", "-6", "--stdout", stdin=producer.stdout, stdout=stream)
                finally:
                    producer.stdout.close()
                    status = producer.wait()
                if status:
                    raise subprocess.CalledProcessError(status, producer.args)
        else:
            archive = work / f"{name}_{version}.orig.tar.gz"
            run("git", "-C", checkout, "archive", "--format=tar.gz",
                f"--prefix={source.name}/", f"--output={archive}", "FETCH_HEAD")
        run("tar", "-xf", archive, "-C", work)
        # Supplementary orig components travel with the Debian source package on
        # every target when requested by the manifest.
        add_components(package, checkout, work, source)
        copyright_text = (source / package["copyright"]).read_text()
        if package.get("upstream_packaging"):
            prepare_packaging(source, name)
            copyright_text = (source / "rpiastro-packaging" / "copyright").read_text()
        # This tree has just been extracted from the pinned archive, never a user's checkout.
        if (source / "debian").exists():
            shutil.rmtree(source / "debian")
        if package.get("upstream_packaging"):
            shutil.move(source / "rpiastro-packaging", source / "debian")
        else:
            shutil.copytree(ROOT / "packaging" / name, source / "debian")
        shutil.copytree(ROOT / "packaging" / name, source / "debian", dirs_exist_ok=True)
        for component in package.get("components", []):
            provenance = f"{component['name']}.json"
            (source / "debian" / provenance).write_text(json.dumps(component, indent=2) + "\n")
            with (source / "debian" / f"{name}.docs").open("a") as docs:
                docs.write(f"debian/{provenance}\n")
        if not (source / "debian" / "copyright").exists():
            (source / "debian" / "copyright").write_text(copyright_text)
        (source / "debian" / "source").mkdir(exist_ok=True)
        (source / "debian" / "source" / "format").write_text("3.0 (quilt)\n")
        epoch = f"{package['epoch']}:" if package.get("epoch") else ""
        deb_version = f"{epoch}{version}-1+rpiastro{manifest['revision']}~deb{SUITES[suite]}"
        date = datetime.datetime.fromtimestamp(int(timestamp), datetime.timezone.utc)
        (source / "debian" / "changelog").write_text(
            f"{name} ({deb_version}) {suite}; urgency=medium\n\n"
            f"  * Build upstream revision {actual} for Debian and Raspberry Pi OS.\n\n"
            f" -- RPi Astro maintainers <maintainers@darkdragonsastro.org>  "
            f"{date.strftime('%a, %d %b %Y %H:%M:%S %z')}\n"
        )
        (source / "debian" / "rules").chmod(0o755)
        # Resolve Build-Depends against this suite, including earlier locally installed builds.
        run("apt-get", "build-dep", "-y", "--no-install-recommends", ".", cwd=source)
        # One canonical source build per suite; packaging inputs are architecture-neutral.
        run("dpkg-buildpackage", "-us", "-uc", "-sa" if arch == "arm64" else "-b", cwd=source)
        binaries = sorted(work.glob("*.deb"))
        if not binaries:
            raise SystemExit(f"No binary packages produced for {name}")
        run("apt-get", "install", "-y", "--no-install-recommends", *binaries)
        patterns = ["*.deb", "*.buildinfo", "*.changes"]
        if arch == "arm64":
            patterns += ["*.dsc", "*.orig*.tar.*", "*.debian.tar.*"]
        for pattern in patterns:
            for artifact in work.glob(pattern):
                shutil.copy2(artifact, output / artifact.name)
    shutil.copy2(ROOT / "sources.json", output / "sources.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument("--only", choices=[p["name"] for p in json.loads((ROOT / "sources.json").read_text())["packages"]])
    args = parser.parse_args()
    build(args.suite, args.only)
