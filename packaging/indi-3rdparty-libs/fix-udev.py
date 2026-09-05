"""Adapt staged camera rules: working FX3 loader and no global USB permissions."""
from pathlib import Path

rules = Path("debian/indi-3rdparty-libs/usr/lib/udev/rules.d")
qhy = rules / "85-qhyccd.rules"
text = qhy.read_text()
assert "/sbin/fxload" in text and "-D $env{DEVNAME}" in text
# This pinned release references QHY492.img but does not ship that firmware.
# Do not run a guaranteed-failing upload; keep the general QHY permission rules.
text = "\n".join(line for line in text.splitlines() if "QHY492.img" not in line) + "\n"
qhy.write_text(text.replace("/sbin/fxload", "/usr/lib/rpi-astro/fxload")
              .replace("-D $env{DEVNAME}", "-p $env{BUSNUM},$env{DEVNUM}"))
asi = rules / "99-asi.rules"
text = asi.read_text()
start = text.index("# Set permissions for USB bind/unbind operations")
end = text.index("# access EFWmini")
# These global sysfs permissions serve the separate, unbuilt ASI power driver.
# The camera/filter-wheel/focuser drivers only need the vendor-specific rules.
asi.write_text(text[:start] + text[end:])
