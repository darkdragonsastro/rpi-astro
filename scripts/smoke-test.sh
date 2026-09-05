#!/usr/bin/env bash
# Run in a fresh, native arm64 container of the corresponding Debian suite.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
suite=${1:?Usage: smoke-test.sh bookworm|trixie}
apt-get update
# Start from distro packages to exercise an upgrade as well as dependency resolution.
apt-get install -y --no-install-recommends indi-bin kstars indi-gphoto indi-eqmod python3
apt-get install -y --no-install-recommends /packages/"$suite"/*.deb
apt-get check
dpkg-query -W indi-bin kstars libstellarsolver2 libxisf0
dpkg-query -W indi-3rdparty indi-3rdparty-libs indi-3rdparty-drivers
python3 /scripts/test-thirdparty.py
QT_QPA_PLATFORM=offscreen kstars --version
if ldd /usr/bin/kstars /usr/bin/indiserver | grep -q 'not found'; then
  echo "Missing shared libraries" >&2
  exit 1
fi
# Exercise the server and simulator over the actual INDI protocol.
indiserver indi_simulator_telescope &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
for _ in {1..20}; do
  if indi_getprop -t 2 '*.CONNECTION.*'; then
    exit 0
  fi
  sleep 1
done
echo "INDI simulator did not respond" >&2
exit 1
