# RPi Astro

An open, signed APT repository for astronomy software on **Debian Bookworm and Trixie (amd64 and arm64)**, including **64-bit Raspberry Pi OS**. Packages are built from pinned upstream sources on native GitHub Actions runners, separately inside each matching Debian release.

The repository is live for ARM64; amd64 support is being validated for the next publication. CI builds all four suite/architecture targets, checks distro upgrades and INDI simulators, and verifies public APT installations, installed-file integrity and matching source downloads after deployment. Real desktop, camera, mount and imaging-session tests remain necessary before relying on a release in the field.

| Software | Initial upstream version | Packages |
| --- | --- | --- |
| [libXISF](https://gitea.nouspiro.space/nou/libXISF) | 0.2.13 | `libxisf0`, `libxisf-dev` |
| [INDI](https://github.com/indilib/indi) | 2.2.4.2 | `indi-bin`, shared libraries, `libindi-dev`, `libindi-data` |
| [INDI third-party](https://github.com/indilib/indi-3rdparty) | 2.2.4.1 | `indi-3rdparty`, `indi-3rdparty-drivers`, `indi-3rdparty-libs` |
| [StellarSolver](https://github.com/rlancaste/stellarsolver) | 2.8 | `libstellarsolver2`, `libstellarsolver-dev` |
| [KStars / Ekos](https://kstars.kde.org/) | 3.8.4 | `kstars`, `kstars-data` |

Exact revisions and the package revision are in [sources.json](sources.json). These are newer upstream builds, not a mirror of Debian's packages. Qt 5 is used consistently for KStars and StellarSolver on both releases. INDI core includes many telescope drivers and simulated devices. Third-party packaging adds upstream's default-enabled drivers for each architecture and supplied vendor libraries, firmware and udev rules. PHD2 and large plate-solving index files are not included.

## Install

The repository is hosted at:

<https://darkdragonsastro.github.io/rpi-astro/>

Archive signing-key fingerprint: `F5E24E97F7FD6F6DC5DBDB3191110672353D9DA6`.
The [public key](archive-key.asc) expires September 4, 2028.

Download and inspect the setup script, then run it:

```sh
curl -fLO https://darkdragonsastro.github.io/rpi-astro/install-repository.sh
less install-repository.sh
sudo bash install-repository.sh
sudo apt install indi-bin indi-3rdparty kstars
```

Or, if you trust the repository and want to skip manual inspection, use this one-liner:

```sh
curl -fL https://darkdragonsastro.github.io/rpi-astro/install-repository.sh -o install-repository.sh && sudo bash install-repository.sh && sudo apt install indi-bin indi-3rdparty kstars
```

This downloads the complete script before running it as root; each step must succeed before the next runs.

The script checks the OS suite, detects `arm64` or `amd64`, verifies the signing-key fingerprint, then creates a deb822 `.sources` file for that architecture with a repository-specific `Signed-By` key. The same command works on Raspberry Pi and Intel/AMD PCs. It enables `deb-src` too, so `apt source kstars` retrieves matching source and packaging. Compare the script's fingerprint with the independently recorded maintainer fingerprint before first use. It refuses to overwrite an existing repository configuration.

For an existing repository installation, run `sudo apt update && sudo apt install indi-3rdparty`. This installs both aggregate third-party packages. They replace conflicting individually packaged drivers/libraries (such as `indi-eqmod` and `indi-gphoto`); review APT's proposed changes if you have packages from another astronomy repository.

Third-party coverage follows the upstream default build, plus Webcam and NUT support. Upstream-default-off options (including AHP, GigE, libcamera, IMU and Celestron Origin) are not enabled. On ARM64, Pentax uses the upstream pktriggercord backend; amd64 also builds the Ricoh SDK backend. Pentax raw-I/O capabilities are not automatically granted. Vendor and component license notices are installed under `/usr/share/doc/indi-3rdparty-{libs,drivers}/upstream-notices/`.

QHY FX3 firmware loading uses a private `rpi-astro-fxload` helper built from pinned libusb examples; legacy SBIG/DSI rules use Debian's `fxload`. The pinned upstream release omits `QHY492.img`, so QHY492 firmware loading is not provided. ASI's optional power-driver rules that grant global USB sysfs write access are omitted; vendor-specific camera permissions remain. Reconnect USB equipment after installation so udev applies the new rules.

Use the suite matching your installed OS. Do not point Bookworm at Trixie packages. A 64-bit CPU running a 32-bit OS is not supported. Our build flags do not use `-march=native`; vendor SDK hardware requirements still apply. Ubuntu and other Debian derivatives are not tested targets.

KStars is a graphical application and requires a desktop session. INDI can run headlessly, for example:

```sh
indiserver indi_simulator_telescope indi_simulator_ccd
```

## Build and publish

Pull requests and pushes to `main` build both suites on both architectures and run upgrade/runtime smoke tests. ARM64 uses `ubuntu-24.04-arm` runners; amd64 uses `ubuntu-24.04`. Successful packages, source packages, build information and the source manifest are retained as architecture-qualified Actions artifacts for 30 days. No signing key is exposed to build jobs or pull requests.

To publish, configure Pages to use GitHub Actions and set:

- Repository secret `APT_SIGNING_KEY`: ASCII-armored private signing key, without a passphrase (a dedicated CI key, never a personal key).
- Repository variable `APT_SIGNING_FINGERPRINT`: the full public key fingerprint.

Keep a private offline backup and revocation certificate. Publish the fingerprint through a trusted channel. See [operations](docs/operations.md) for key management and release details.

For this initial setup, the local signing-key home and revocation certificate are in the ignored `keys/gnupg/` directory. Back up that directory privately; it must never be committed or uploaded as a public artifact.

Run **Build astronomy packages** manually from `main`, enabling **Publish all four tested suite/architecture targets to GitHub Pages**. This builds and tests every target before assembling and signing the site. One complete Pages deployment contains both suites and architectures; a failed build cannot publish a partial update. Fresh containers then verify installation from the public endpoint on all four targets.

ARM64 jobs supply each suite's canonical source packages. Architecture-independent binary packages are built on both architectures, checked for equivalent contents, and published once. Native packages must have matching names and versions across architectures; missing or mismatched targets stop publication.

The archive contains `.deb` files and corresponding Debian source packages. It has a 900 MB size gate below [GitHub Pages' 1 GB limit](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits). Large data sets and long-term binary retention will need a separate storage design as the project grows.

## Local development

On an ARM64 or amd64 host with Docker (builds use the host's native architecture):

```sh
docker build --build-arg SUITE=bookworm -f containers/Dockerfile -t rpi-astro:bookworm .
mkdir -p build dist
docker run --rm -e DEB_BUILD_OPTIONS=parallel=4 \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/packaging:/workspace/packaging:ro" \
  -v "$PWD/sources.json:/workspace/sources.json:ro" \
  -v "$PWD/build:/workspace/build" -v "$PWD/dist:/workspace/dist" \
  rpi-astro:bookworm python3 scripts/build.py bookworm
```

Substitute `trixie` to build that suite. Only build inputs and output directories are mounted; the private signing-key directory is not exposed to the container. Build directories are deliberately required to be fresh: move `build/<suite>/<architecture>` and `dist/<suite>/<architecture>` aside before retrying a whole build. `--only` accepts a source package name from `sources.json`, including `indi-3rdparty-libs` and `indi-3rdparty-drivers`; prerequisites must already be installed in the same disposable container. Publication always requires the complete four-target set.

Run repository integration tests on Debian/Ubuntu with `python3`, `reprepro`, `gnupg` and `dpkg-dev` installed:

```sh
python3 -m unittest discover -s tests -v
```

These create a disposable key and packages, verify suite/architecture isolation and shared-package equivalence, fetch packages through actual APT over HTTP, and prove tampered metadata and incomplete targets are rejected.

## Credits and scope

The dependency order and initial version selection were informed by Dušan Poizl's [astro-soft-build](https://gitea.nouspiro.space/nou/astro-soft-build). We use our own Debian packaging and Actions orchestration so APT owns installed files and dependencies. See [THIRD_PARTY.md](THIRD_PARTY.md).

The repository tooling is MIT licensed. Upstream software retains its own licenses; builds preserve upstream copyright notices and publish corresponding source packages. This is a community project, not an official Raspberry Pi, Debian, KDE or INDI repository.
