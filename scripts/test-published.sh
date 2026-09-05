#!/usr/bin/env bash
# Run in a fresh native Debian container after deployment.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
base_url=${1:?Usage: test-published.sh BASE_URL FINGERPRINT}
fingerprint=${2:?Expected archive signing fingerprint}
architecture=$(dpkg --print-architecture)
apt-get update
apt-get install -y --no-install-recommends curl ca-certificates gnupg python3
curl -fLsS --retry 5 "$base_url/install-repository.sh" -o /tmp/published-setup.sh
sed -e "s|@BASE_URL@|$base_url|g" -e "s|@FINGERPRINT@|$fingerprint|g" \
  /scripts/install-repository.sh | cmp - /tmp/published-setup.sh
bash /tmp/published-setup.sh
grep -Fx "Architectures: $architecture" /etc/apt/sources.list.d/rpi-astro.sources
apt-get install -y --no-install-recommends indi-bin indi-3rdparty kstars
apt-get check
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

manifest = json.loads(Path('/sources.json').read_text())
release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
suite = release['VERSION_CODENAME'].strip('"')
number = {'bookworm': 12, 'trixie': 13}[suite]
binary_names = {'indi': 'indi-bin', 'libxisf': 'libxisf0', 'stellarsolver': 'libstellarsolver2'}
for package in manifest['packages']:
    name = binary_names.get(package['name'], package['name'])
    epoch = f"{package['epoch']}:" if package.get('epoch') else ''
    expected = f"{epoch}{package['version']}-1+rpiastro{manifest['revision']}~deb{number}"
    actual = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', name], text=True)
    assert actual == expected, f'{name}: expected {expected}, got {actual}'
PY
python3 /scripts/test-thirdparty.py
integrity=$(dpkg --verify indi-bin kstars kstars-data libindi-data \
  indi-3rdparty-libs indi-3rdparty-drivers rpi-astro-fxload)
test -z "$integrity" || { printf '%s\n' "$integrity"; exit 1; }
QT_QPA_PLATFORM=offscreen kstars --version
mkdir /tmp/astro-source
cd /tmp/astro-source
apt-get source --download-only indi-3rdparty-drivers indi-3rdparty-libs
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

manifest = json.loads(Path('/sources.json').read_text())
for package in manifest['packages']:
    for component in package.get('components', []):
        if 'url' in component:
            archive = Path(f"{package['name']}_{package['version']}.orig-{component['name']}.tar.gz")
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == component['sha256'], archive
PY
echo "Published installation, integrity and source download verified on $architecture"
