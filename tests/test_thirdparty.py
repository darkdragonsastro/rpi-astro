import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("thirdparty", Path(__file__).resolve().parents[1] / "scripts/thirdparty.py")
thirdparty = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thirdparty)


class ThirdPartyPackagingTests(unittest.TestCase):
    def test_preserves_notices_and_pins_aggregate_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            upstream = source / "debian/indi-3rdparty-drivers"
            upstream.mkdir(parents=True)
            (upstream / "control").write_text(
                "Source: indi-3rdparty-drivers\nMaintainer: Upstream\n"
                "Build-Depends: cmake,\n libcurl4-openssl-dev\nStandards-Version: 4.6.2\n\n"
                "Package: indi-3rdparty-drivers\nArchitecture: any\n"
                "Depends: ${shlibs:Depends}, ${misc:Depends}, indi-3rdparty-libs\n"
                "conflicts: indi-asi\nreplaces: indi-asi\nDescription: drivers\n Drivers.\n"
            )
            (upstream / "copyright").write_text("Driver copyright\n")
            (source / "LICENSE").write_text("Root license\n")
            vendor = source / "libasi"
            vendor.mkdir()
            (vendor / "license.txt").write_bytes(b"Vendor notice\n")
            thirdparty.prepare_packaging(source, "indi-3rdparty-drivers")
            prepared = source / "rpiastro-packaging"
            control = (prepared / "control").read_text()
            self.assertIn("indi-3rdparty-libs (= ${binary:Version})", control)
            self.assertIn("Package: indi-3rdparty\n", control)
            self.assertIn("Architecture: arm64\n", control)
            self.assertIn("libcurl4-gnutls-dev", control)
            self.assertNotIn("libcurl4-openssl-dev", control)
            self.assertEqual((prepared / "upstream-notices/libasi/license.txt").read_bytes(), b"Vendor notice\n")
            self.assertTrue((prepared / "upstream-notices/debian/indi-3rdparty-drivers/copyright").is_file())
            self.assertTrue((upstream / "control").is_file())
