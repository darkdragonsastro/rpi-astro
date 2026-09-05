import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import runpy

spec = importlib.util.spec_from_file_location("thirdparty", Path(__file__).resolve().parents[1] / "scripts/thirdparty.py")
thirdparty = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thirdparty)


class ThirdPartyPackagingTests(unittest.TestCase):
    def test_camera_rule_adaptation(self):
        script = Path(__file__).resolve().parents[1] / "packaging/indi-3rdparty-libs/fix-udev.py"
        with tempfile.TemporaryDirectory() as folder:
            rules = Path(folder) / "debian/indi-3rdparty-libs/usr/lib/udev/rules.d"
            rules.mkdir(parents=True)
            (rules / "85-qhyccd.rules").write_text(
                'RUN+="/sbin/fxload -t fx3 -I /usr/lib/firmware/qhy/QHY268.img -D $env{DEVNAME}"\n'
                'RUN+="/sbin/fxload -t fx3 -I /usr/lib/firmware/qhy/QHY492.img -D $env{DEVNAME}"\n')
            (rules / "99-asi.rules").write_text(
                'ATTR{idVendor}=="03c3", MODE="0666"\n'
                '# Set permissions for USB bind/unbind operations\nunsafe global rule\n'
                '# access EFWmini\nKERNEL=="hidraw*", ATTRS{idVendor}=="03c3", MODE="0666"\n')
            previous = Path.cwd()
            try:
                os.chdir(folder)
                runpy.run_path(str(script))
            finally:
                os.chdir(previous)
            qhy = (rules / "85-qhyccd.rules").read_text()
            self.assertIn('/usr/lib/rpi-astro/fxload', qhy)
            self.assertIn('-p $env{BUSNUM},$env{DEVNUM}', qhy)
            self.assertNotIn('QHY492.img', qhy)
            asi = (rules / "99-asi.rules").read_text()
            self.assertNotIn('unsafe global rule', asi)
            self.assertIn('hidraw*', asi)
            self.assertIn('03c3', asi)

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
