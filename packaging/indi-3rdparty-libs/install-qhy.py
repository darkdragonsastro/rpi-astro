"""Stage the official Bookworm amd64 SDK without running its installer."""

import hashlib
import json
from pathlib import Path
import shutil
import sys


def install(source, destination, metadata, multiarch):
    assert multiarch == "x86_64-linux-gnu", "Vendor SDK is amd64 only"
    assert (metadata["suite"], metadata["architecture"]) == ("bookworm", "amd64")
    library_name = f"libqhyccd.so.{metadata['version']}"
    library = source / "usr/local/lib" / library_name
    assert hashlib.sha256(library.read_bytes()).hexdigest() == metadata["library_sha256"], "QHY library checksum mismatch"
    library_dir = destination / "usr/lib" / multiarch
    library_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(library, library_dir / library_name)
    (library_dir / library_name).chmod(0o644)
    (library_dir / "libqhyccd.so.20").symlink_to(library_name)
    (library_dir / "libqhyccd.so").symlink_to("libqhyccd.so.20")
    headers = destination / "usr/include/libqhy"
    headers.mkdir(parents=True, exist_ok=True)
    for name in ("qhyccd.h", "qhyccderr.h", "qhyccdcamdef.h", "qhyccdstruct.h", "config.h"):
        shutil.copyfile(source / "usr/local/include" / name, headers / name)
    firmware = destination / "usr/lib/firmware/qhy"
    shutil.copytree(source / "lib/firmware/qhy", firmware)
    for path in firmware.iterdir():
        path.chmod(0o644)
    rules = destination / "usr/lib/udev/rules.d"
    rules.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "lib/udev/rules.d/85-qhyccd.rules", rules / "85-qhyccd.rules")


if __name__ == "__main__":
    install(Path("qhybookworm"), Path("debian/indi-3rdparty-libs"),
            json.loads(Path("debian/qhybookworm.json").read_text()), sys.argv[1])
