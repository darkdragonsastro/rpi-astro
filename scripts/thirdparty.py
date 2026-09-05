"""Adapt the pinned upstream aggregate packaging, retaining per-component notices."""

from pathlib import Path
import re
import shutil


EXTRA_DEPENDS = [
    "libcurl4-gnutls-dev", "libfftw3-dev", "libftdi-dev", "libgpiod-dev",
    "libhidapi-dev", "libavcodec-dev", "libavdevice-dev", "libavformat-dev",
    "libswscale-dev", "libavutil-dev", "libboost-regex-dev", "libboost-system-dev",
    "libbluetooth-dev", "libyaml-dev", "libtinyxml2-dev", "libnutclient-dev",
    "nlohmann-json3-dev", "libudev-dev", "python3",
]


def prepare_packaging(source: Path, name: str):
    """Run before replacing upstream debian/ in a freshly extracted source tree."""
    target = source / "rpiastro-packaging"
    shutil.copytree(source / "debian" / name, target)
    control = (target / "control").read_text()
    control = re.sub(r"(?m)^Maintainer:.*$", "Maintainer: RPi Astro maintainers <maintainers@darkdragonsastro.org>", control)
    control = control.replace("libcurl4-openssl-dev", "libcurl4-gnutls-dev")
    control = re.sub(r"(?ms)^Build-Depends: (.*?)(?=^[^ \n])",
                     lambda m: "Build-Depends: " + m[1].rstrip() + ",\n " + ",\n ".join(EXTRA_DEPENDS) + "\n", control, count=1)
    # Aggregate packages own common headers, firmware and rules, not coinstallable architectures.
    control = control.replace("Multi-Arch: same\n", "")
    control = control.replace("Architecture: any", "Architecture: arm64 amd64")
    if name.endswith("libs"):
        control = control.replace("Depends: ${shlibs:Depends}, ${misc:Depends}",
                                  "Depends: ${shlibs:Depends}, ${misc:Depends}, fxload, rpi-astro-fxload")
    if name.endswith("drivers"):
        control = control.replace("Depends: ${shlibs:Depends}, ${misc:Depends}, indi-3rdparty-libs",
                                  "Depends: ${shlibs:Depends}, ${misc:Depends}, indi-bin, indi-3rdparty-libs (= ${binary:Version})")
        control += "\n\nPackage: indi-3rdparty\nArchitecture: all\nDepends: ${misc:Depends}, indi-3rdparty-drivers (= ${source:Version})\nDescription: INDI third-party driver collection\n Installs the third-party drivers and their vendor support libraries.\n"
    # Supplement upstream's aggregate conflict list for other distro package names.
    extras = ("libapogee3v5, libqsi9, libqsi9t64, asi-common, firmware-ccd" if name.endswith("libs")
              else "indi-atik-efw, libusbp1, libusbp-dev, libpololu-tic-1, libpololu-tic-dev, pololu-tic")
    for field in ("conflicts", "replaces"):
        control = re.sub(rf"(?mi)^{field}: (.*)$", lambda m: f"{field.title()}: {m[1]}, {extras}", control)
    (target / "control").write_text(control.rstrip() + "\n")
    # The aggregate upstream copyright file alone does not describe vendor SDKs.
    # Preserve every component's Debian copyright and all in-tree license notices.
    notices = target / "upstream-notices"
    notices.mkdir()
    candidates = set(source.glob("debian/*/copyright"))
    for path in source.rglob("*"):
        if not path.is_file() or target in path.parents:
            continue
        if path.name.lower().startswith(("license", "licence", "copying", "copyright", "notice")):
            candidates.add(path)
    entries = []
    for path in sorted(candidates):
        relative = path.relative_to(source)
        destination = notices / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        entries.append(str(relative))
    (notices / "INDEX").write_text("Upstream notices, with original source paths:\n\n" + "\n".join(entries) + "\n")
    (target / "copyright").write_text(
        "This aggregate contains components under different upstream licenses.\n"
        "See upstream-notices/ (including its INDEX and debian/*/copyright)\n"
        "in this documentation directory for the preserved component notices.\n\n"
        + (source / "LICENSE").read_text()
    )
    (target / f"{name}.docs").write_text("debian/upstream-notices\n")
