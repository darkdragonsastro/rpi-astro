#!/usr/bin/env python3
"""Validate installed third-party payloads without connecting physical devices."""

from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def check():
    packages = ("indi-3rdparty-libs", "indi-3rdparty-drivers")
    paths = set()
    for package in packages:
        paths.update(subprocess.check_output(["dpkg-query", "-L", package], text=True).splitlines())
        notices = Path("/usr/share/doc") / package / "upstream-notices"
        assert (notices / "INDEX").is_file(), f"Missing notices for {package}"
        assert (notices / "libasi/license.txt").is_file(), "Missing vendor redistribution notice"
    # Make a silently disabled major driver or missing SDK a test failure.
    required = ["indi_asi_ccd", "indi_qhy_ccd", "indi_atik_ccd", "indi_playerone_ccd",
                "indi_toupcam_ccd", "indi_eqmod_telescope", "indi_gphoto_ccd",
                "indi_sbig_ccd", "indi_qsi_ccd", "indi_fli_ccd", "indi_sx_ccd"]
    for driver in required:
        assert Path("/usr/bin", driver).is_file(), f"Missing {driver}"
    for rule in ("99-asi.rules", "85-qhyccd.rules"):
        assert Path("/usr/lib/udev/rules.d", rule).is_file(), f"Missing {rule}"
    assert any(Path("/usr/lib/firmware/qhy").iterdir()), "Missing QHY firmware"
    count = 0
    for value in sorted(paths):
        path = Path(value)
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            header = stream.read(20)
        if header[:4] != b"\x7fELF":
            continue
        assert header[4:6] == b"\x02\x01" and header[18:20] == b"\xb7\x00", f"Non-ARM64 ELF: {path}"
        result = subprocess.run(["ldd", str(path)], text=True, capture_output=True)
        assert "not found" not in result.stdout + result.stderr, f"Missing dependency: {path}\n{result.stdout}{result.stderr}"
        if result.returncode:
            assert "not a dynamic executable" in result.stdout + result.stderr, f"ldd failed: {path}"
        count += 1
    assert count >= 50, f"Unexpectedly small ELF payload: {count}"
    # Only inspect device-list XML, not skeleton/property templates.
    for value in paths:
        path = Path(value)
        if path.suffix != ".xml" or path.parent != Path("/usr/share/indi"):
            continue
        root = ET.parse(path).getroot()
        if root.tag != "driversList":
            continue
        for node in root.iter("driver"):
            if node.text and node.text.strip():
                assert Path("/usr/bin", node.text.strip()).is_file(), f"Uninstalled driver in {path}: {node.text}"
    print(f"Validated {count} ARM64 ELF files, driver definitions, firmware and license notices")


if __name__ == "__main__":
    check()
