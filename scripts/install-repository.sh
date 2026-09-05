#!/usr/bin/env bash
set -euo pipefail
base_url='@BASE_URL@'
fingerprint='@FINGERPRINT@'

if [[ $EUID != 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi
# shellcheck source=/dev/null
source /etc/os-release
case "${VERSION_CODENAME:-}" in
  bookworm|trixie) suite=$VERSION_CODENAME ;;
  *) echo "Only Debian or Raspberry Pi OS Bookworm and Trixie are supported." >&2; exit 1 ;;
esac
architecture=$(dpkg --print-architecture)
case "$architecture" in
  arm64|amd64) ;;
  *) echo "A supported 64-bit OS (arm64 or amd64) is required." >&2; exit 1 ;;
esac
keyring=/etc/apt/keyrings/rpi-astro.asc
sources=/etc/apt/sources.list.d/rpi-astro.sources
if [[ -e $keyring || -e $sources ]]; then
  echo "RPi Astro is already configured. Inspect $sources before changing it." >&2
  exit 1
fi
apt-get update
apt-get install -y ca-certificates curl gnupg
temp_dir=$(mktemp -d)
trap 'rm -f "$temp_dir/key.asc"; rmdir "$temp_dir"' EXIT
curl --fail --silent --show-error --location "$base_url/rpi-astro.asc" -o "$temp_dir/key.asc"
key_details=$(gpg --batch --show-keys --with-colons "$temp_dir/key.asc")
primary_keys=$(awk -F: '$1 == "pub" {n++} END {print n+0}' <<< "$key_details")
[[ $primary_keys == 1 ]] || { echo "Expected exactly one archive signing key." >&2; exit 1; }
actual=$(awk -F: '$1 == "fpr" {print $10; exit}' <<< "$key_details")
[[ $actual == "$fingerprint" ]] || { echo "Signing key fingerprint mismatch." >&2; exit 1; }
install -d -m 0755 /etc/apt/keyrings
install -m 0644 "$temp_dir/key.asc" "$keyring"
printf 'Types: deb deb-src\nURIs: %s\nSuites: %s\nComponents: main\nArchitectures: %s\nSigned-By: %s\n' \
  "$base_url" "$suite" "$architecture" "$keyring" > "$sources"
apt-get update
echo 'Repository added. Install with: sudo apt install indi-bin indi-3rdparty kstars'
