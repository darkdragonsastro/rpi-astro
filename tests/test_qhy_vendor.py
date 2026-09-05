import hashlib
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
install = runpy.run_path(str(ROOT / "packaging/indi-3rdparty-libs/install-qhy.py"))["install"]


class QhyVendorTests(unittest.TestCase):
    def test_stages_only_required_payload_and_checks_library(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sdk = root / "sdk"
            for name in ("usr/local/lib", "usr/local/include", "lib/firmware/qhy", "lib/udev/rules.d"):
                (sdk / name).mkdir(parents=True)
            (sdk / "usr/local/lib/libqhyccd.so.26.7.28.15").write_bytes(b"sdk")
            (sdk / "usr/local/lib/libqhyccd.a").write_bytes(b"do not ship")
            for name in ("qhyccd.h", "qhyccderr.h", "qhyccdcamdef.h", "qhyccdstruct.h", "config.h"):
                (sdk / "usr/local/include" / name).write_text(name)
            (sdk / "lib/firmware/qhy/camera.img").write_bytes(b"firmware")
            (sdk / "lib/udev/rules.d/85-qhyccd.rules").write_text("rules")
            metadata = {"version": "26.7.28.15", "suite": "bookworm", "architecture": "amd64",
                        "library_sha256": hashlib.sha256(b"sdk").hexdigest()}
            destination = root / "package"
            install(sdk, destination, metadata, "x86_64-linux-gnu")
            self.assertEqual((destination / "usr/lib/x86_64-linux-gnu/libqhyccd.so").read_bytes(), b"sdk")
            self.assertTrue((destination / "usr/include/libqhy/config.h").is_file())
            self.assertTrue((destination / "usr/lib/firmware/qhy/camera.img").is_file())
            self.assertFalse(list(destination.rglob("*.a")))
            with self.assertRaisesRegex(AssertionError, "amd64 only"):
                install(sdk, root / "wrong-arch", metadata, "aarch64-linux-gnu")
            metadata["library_sha256"] = "0" * 64
            with self.assertRaisesRegex(AssertionError, "checksum mismatch"):
                install(sdk, root / "bad-library", metadata, "x86_64-linux-gnu")
