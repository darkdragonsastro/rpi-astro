# RPi Astro

An open, signed APT repository for astronomy software on **64-bit Raspberry Pi OS Bookworm and Trixie**. Packages are built from pinned upstream sources on GitHub Actions ARM64 runners, separately inside each matching Debian release.

This project is being bootstrapped. A successful package build is not a hardware certification; real camera, mount and imaging-session tests remain necessary before relying on a release in the field.

| Software | Initial upstream version | Packages |
| --- | --- | --- |
| [libXISF](https://gitea.nouspiro.space/nou/libXISF) | 0.2.13 | `libxisf0`, `libxisf-dev` |
| [INDI](https://github.com/indilib/indi) | 2.2.4.2 | `indi-bin`, shared libraries, `libindi-dev`, `libindi-data` |
| [StellarSolver](https://github.com/rlancaste/stellarsolver) | 2.8 | `libstellarsolver2`, `libstellarsolver-dev` |
| [KStars / Ekos](https://kstars.kde.org/) | 3.8.4 | `kstars`, `kstars-data` |

Exact revisions and the package revision are in [sources.json](sources.json). These are newer upstream builds, not a mirror of Debian's packages. Qt 5 is used consistently for KStars and StellarSolver on both releases. INDI core includes many telescope drivers and simulated devices; the separate `indi-3rdparty` collection, vendor SDKs, PHD2 and large plate-solving index files are not included in the initial set.

## Install

After the first successful Pages publication, the repository will be at:

<https://darkdragonsastro.github.io/rpi-astro/>

Archive signing-key fingerprint: `F5E24E97F7FD6F6DC5DBDB3191110672353D9DA6`.
The [public key](archive-key.asc) expires September 4, 2028.

Download and inspect the setup script, then run it:

```sh
curl -fLO https://darkdragonsastro.github.io/rpi-astro/install-repository.sh
less install-repository.sh
sudo bash install-repository.sh
sudo apt install indi-bin kstars
```

The script checks the OS suite, ARM64 architecture and signing-key fingerprint, then creates a deb822 `.sources` file with a repository-specific `Signed-By` key. It enables `deb-src` too, so `apt source kstars` retrieves matching source and packaging. Compare the script's fingerprint with the independently recorded maintainer fingerprint before first use. It refuses to overwrite an existing repository configuration.

Use the suite matching your installed OS. Do not point Bookworm at Trixie packages. A 64-bit CPU running a 32-bit OS is not supported. Builds target generic ARM64 and do not use `-march=native`.

KStars is a graphical application and requires a desktop session. INDI can run headlessly, for example:

```sh
indiserver indi_simulator_telescope indi_simulator_ccd
```

## Build and publish

Pull requests and pushes to `main` build both suites and run an upgrade/runtime smoke test. Successful packages, source packages, build information and the source manifest are retained as Actions artifacts for 30 days. No signing key is exposed to build jobs or pull requests.

To publish, configure Pages to use GitHub Actions and set:

- Repository secret `APT_SIGNING_KEY`: ASCII-armored private signing key, without a passphrase (a dedicated CI key, never a personal key).
- Repository variable `APT_SIGNING_FINGERPRINT`: the full public key fingerprint.

Keep a private offline backup and revocation certificate. Publish the fingerprint through a trusted channel. See [operations](docs/operations.md) for key management and release details.

Run **Build astronomy packages** manually from `main`, enabling **Publish both tested suites to GitHub Pages**. This builds and tests both suites before assembling and signing the site. One complete Pages deployment contains both suites; a failed build cannot publish a partial update.

The archive contains `.deb` files and corresponding Debian source packages. It has a 900 MB size gate below [GitHub Pages' 1 GB limit](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits). Large data sets and long-term binary retention will need a separate storage design as the project grows.

## Local development

On an ARM64 host with Docker:

```sh
docker build --build-arg SUITE=bookworm -f containers/Dockerfile -t rpi-astro:bookworm .
docker run --rm -e DEB_BUILD_OPTIONS=parallel=4 \
  -v "$PWD:/workspace" rpi-astro:bookworm python3 scripts/build.py bookworm
```

Substitute `trixie` to build that suite. Build directories are deliberately required to be fresh: move `build/<suite>` and `dist/<suite>` aside before retrying a whole build. `--only libxisf|indi|stellarsolver|kstars` supports development, but prerequisites must already be installed in the same disposable container. Publication always requires the complete suite set.

Run repository integration tests on Debian/Ubuntu with `python3`, `reprepro`, `gnupg` and `dpkg-dev` installed:

```sh
python3 -m unittest discover -s tests -v
```

These create a disposable key and packages, verify suite isolation, fetch packages through actual APT over HTTP, and prove tampered metadata is rejected.

## Credits and scope

The dependency order and initial version selection were informed by Dušan Poizl's [astro-soft-build](https://gitea.nouspiro.space/nou/astro-soft-build). We use our own Debian packaging and Actions orchestration so APT owns installed files and dependencies. See [THIRD_PARTY.md](THIRD_PARTY.md).

The repository tooling is MIT licensed. Upstream software retains its own licenses; builds preserve upstream copyright notices and publish corresponding source packages. This is a community project, not an official Raspberry Pi, Debian, KDE or INDI repository.
