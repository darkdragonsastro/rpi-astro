#!/usr/bin/env python3
"""Validate installed third-party payloads without connecting physical devices."""

from pathlib import Path
import ctypes
import os
import re
import signal
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET


def check_qhy_excluded(paths):
    """Reject QHY runtime payloads, while allowing retained source notices."""
    for value in paths:
        if value.startswith("/usr/share/doc/"):
            continue
        path = Path(value)
        assert not (path.name.startswith(("indi_qhy", "qhy_ccd_test", "libqhyccd", "85-qhyccd"))
                    or "libqhy" in path.parts or "/firmware/qhy" in value), f"Unexpected QHY payload: {value}"


def check():
    architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    machine = {"arm64": b"\xb7\x00", "amd64": b"\x3e\x00"}[architecture]
    bookworm = "VERSION_CODENAME=bookworm" in Path("/etc/os-release").read_text()
    with_qhy = not (bookworm and architecture == "amd64")
    if with_qhy:
        qhy = ctypes.CDLL("libqhyccd.so.20")
        version = [ctypes.c_uint32() for _ in range(4)]
        qhy.GetQHYCCDSDKVersion.argtypes = [ctypes.POINTER(ctypes.c_uint32)] * 4
        qhy.GetQHYCCDSDKVersion.restype = ctypes.c_uint32
        result = qhy.GetQHYCCDSDKVersion(*(ctypes.byref(part) for part in version))
        actual_qhy = tuple(part.value for part in version[:3])
        assert result == 0 and actual_qhy == (26, 7, 21), f"Unexpected QHY SDK: {actual_qhy}"
        print(f"QHY SDK {actual_qhy} verified from the loaded library")
    packages = ("indi-3rdparty-libs", "indi-3rdparty-drivers")
    paths = set()
    for package in packages:
        paths.update(subprocess.check_output(["dpkg-query", "-L", package], text=True).splitlines())
        notices = Path("/usr/share/doc") / package / "upstream-notices"
        assert (notices / "INDEX").is_file(), f"Missing notices for {package}"
        assert (notices / "libasi/license.txt").is_file(), "Missing vendor redistribution notice"
    if not with_qhy:
        check_qhy_excluded(paths)
        print("QHY driver and SDK excluded on Bookworm amd64")
    assert not any("NOTFOUND" in path for path in paths), "Unresolved CMake installation directory"
    # Make a silently disabled major driver or missing SDK a test failure.
    required = ["indi_asi_ccd", "indi_atik_ccd", "indi_playerone_ccd",
                "indi_toupcam_ccd", "indi_eqmod_telescope", "indi_gphoto_ccd",
                "indi_sbig_ccd", "indi_qsi_ccd", "indi_fli_ccd", "indi_sx_ccd"]
    if with_qhy:
        required.append("indi_qhy_ccd")
    for driver in required:
        assert Path("/usr/bin", driver).is_file(), f"Missing {driver}"
    for definition in ("indi_asi.xml", "indi_eqmod.xml", "indi_playerone.xml"):
        assert Path("/usr/share/indi", definition).is_file(), f"Missing {definition}"
    assert Path("/usr/lib/udev/rules.d/99-asi.rules").is_file(), "Missing ASI rules"
    assert Path("/sbin/fxload").is_file(), "Missing legacy firmware loader"
    loader = Path("/usr/lib/rpi-astro/fxload")
    help_result = subprocess.run([str(loader), "-h"], text=True, capture_output=True, timeout=5)
    assert "fx3" in help_result.stderr, "Missing FX3 firmware-loader support"
    if with_qhy:
        assert Path("/usr/share/indi/indi_qhy.xml").is_file(), "Missing QHY definition"
        assert any(Path("/usr/lib/firmware/qhy").iterdir()), "Missing QHY firmware"
        qhy_rules = Path("/usr/lib/udev/rules.d/85-qhyccd.rules").read_text()
        assert str(loader) in qhy_rules and "-D $env{DEVNAME}" not in qhy_rules
        for line in qhy_rules.splitlines():
            if not line.lstrip().startswith("#"):
                for firmware in re.findall(r'(?:-I|-s) ([^\s"]+)', line):
                    assert Path(firmware).is_file(), f"Missing referenced firmware: {firmware}"
    asi_rules = Path("/usr/lib/udev/rules.d/99-asi.rules").read_text()
    assert "/sys/bus/usb/drivers/usb/bind" not in asi_rules, "Global USB permission override"
    count = 0
    for value in sorted(paths):
        path = Path(value)
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            header = stream.read(20)
        if header[:4] != b"\x7fELF":
            continue
        assert header[4:6] == b"\x02\x01" and header[18:20] == machine, f"Non-{architecture} ELF: {path}"
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
    print(f"Validated {count} {architecture} ELF files, driver definitions, firmware and license notices")
    # Exercise a real third-party driver without connecting to a mount.
    with tempfile.TemporaryFile(mode="w+") as log:
        server = subprocess.Popen(["indiserver", "-r", "0", "-p", "17624", "indi_eqmod_telescope"],
                                  stdout=log, stderr=log, start_new_session=True)
        try:
            for _ in range(10):
                result = subprocess.run(["indi_getprop", "-p", "17624", "-t", "2", "EQMod Mount.CONNECTION.*"],
                                        text=True, capture_output=True, timeout=5)
                if result.returncode == 0 and "DISCONNECT=On" in result.stdout:
                    print("EQMod answered an INDI property query without attached hardware")
                    break
                if server.poll() is not None:
                    raise RuntimeError("EQMod server exited")
                time.sleep(0.5)
            else:
                log.seek(0)
                raise RuntimeError("EQMod did not respond:\n" + log.read())
        finally:
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            server.wait(timeout=5)


if __name__ == "__main__":
    check()
