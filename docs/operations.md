# Operations

## Release inputs

`sources.json` fixes source revisions and the dependency build order: libXISF → INDI → third-party libraries → third-party drivers → StellarSolver → KStars. StellarSolver can also build before the third-party packages. Update revisions deliberately, keep Qt selection compatible, and increment `revision` whenever packaging changes could alter the output. Never publish different bytes under an already-published package version.

Third-party builds adapt the pinned upstream aggregate Debian control files with `scripts/thirdparty.py`; local rules are in `packaging/indi-3rdparty-*`. Two source packages build the same pinned upstream tree, libraries first. All upstream per-component Debian copyright files and in-tree license/notice files are preserved in both binary documentation trees. Their source archives also retain the original vendor binaries; supplying source packages does not imply proprietary SDK source code is available. Keep the Pages size gate enabled as SDKs grow.

`rpi-astro-fxload` compiles only the FX2/FX3 loader from libusb 1.0.26 against each suite's system libusb. It installs privately under `/usr/lib/rpi-astro/`, avoiding replacement of Debian's legacy loader. QHY udev rules use its bus/address syntax. The library packaging also omits the rule for absent upstream QHY492 firmware and removes ASI global USB sysfs permission changes for the unbuilt optional power driver.

Versions have the form `3.8.4-1+rpiastro1~deb12` or `~deb13`. KStars retains Debian's epoch `5:` so APT can upgrade it. The suite suffix both distinguishes artifacts and allows a Bookworm-to-Trixie package upgrade. A manifest commit and build information make the source and environment traceable; the moving Debian package mirrors and base image tags mean bit-for-bit reproducibility is not yet guaranteed.

Builds use native Debian ARM64 or amd64 containers for each suite. Raspberry Pi OS 64-bit is based on Debian's ARM64 userland. The 32-bit Raspberry Pi OS ABI is a separate target and cannot be added just by enabling Debian `armhf`.

Artifacts are isolated under `dist/<suite>/<architecture>`, with scratch trees under `build/<suite>/<architecture>`. ARM64 jobs produce canonical source packages (`dpkg-buildpackage -sa`); amd64 jobs use binary-only builds (`-b`) with identical source/packaging inputs and an architecture-neutral changelog. Publication requires matching manifests and native package names/versions across architectures. Both jobs build `Architecture: all` packages; publication compares their control and payload entries (including modes, ownership, symlinks and file contents, ignoring archive compression and timestamps) and publishes the ARM64 copy only if they agree. Sources and shared data are not duplicated per architecture.

QHY is the explicit SDK compatibility exception: Bookworm amd64 selects 26.2.1, while the other targets use the primary tree's 26.7.21. The `indi-3rdparty-libs` manifest entry pins a `qhybookworm` supplementary orig component (selected upstream SDK, headers, firmware, CMake files and notices). This component is present in source packages for both suites; `debian/rules` enables it only for `bookworm/amd64`. It uses no build-time unpinned download. Runtime tests query `GetQHYCCDSDKVersion`, and the binary package includes the component provenance and notices. Review this exception deliberately during upstream updates; a newer SDK is not necessarily compatible with Bookworm.

## Signing key

Use a dedicated repository key. Generate it in a private working directory, back up the key and revocation certificate offline, and export only the public key to the website. A sample manual setup is:

```sh
export GNUPGHOME="$(mktemp -d)"
chmod 700 "$GNUPGHOME"
gpg --batch --passphrase '' --quick-generate-key \
  'RPi Astro archive <rpi-astro@users.noreply.github.com>' rsa3072 sign 2y
gpg --list-keys --with-fingerprint
```

Use the displayed **full fingerprint** below:

```sh
gpg --armor --export-secret-keys FULL_FINGERPRINT | \
  gh secret set APT_SIGNING_KEY --repo darkdragonsastro/rpi-astro
gh variable set APT_SIGNING_FINGERPRINT --body FULL_FINGERPRINT \
  --repo darkdragonsastro/rpi-astro
```

The private key has no passphrase because it must sign unattended; GitHub's secret store protects it at rest. Its only use is in the publication job, after all four builds and tests pass. Protect `main`, review workflow changes, and restrict the `github-pages` environment to `main`. Configure environment reviewers if your release process needs human approval.

Track the expiry date and rotate well in advance. Existing users trust the installed key, so a new key requires a transition signed by the old key or independently verified reconfiguration; silently replacing the website key is not sufficient.

APT Release metadata is signed with both `InRelease` and `Release.gpg`. This initial archive has no `Valid-Until`, allowing a quiet repository to remain installable without periodic signing; that also means an old valid snapshot can be replayed. Add an expiry and a reliable metadata-refresh schedule together if freshness enforcement is needed.

## Publishing and rollback

Only manually dispatched builds of `main` with `publish=true` can deploy. Both suites and architectures are assembled from artifacts belonging to that same run. A single deployment replaces the entire snapshot. The public site contains no private keys, reprepro databases, or configuration. Post-deployment jobs verify the exact installer, package revisions, architecture selection, installed-file integrity, runtime checks and matching third-party source download in four fresh containers. A post-deployment failure is a release incident, not an automatic rollback.

The current snapshot keeps one version per package per suite. Older package URLs can disappear at the next publication; clients should run `apt update` before installation. Actions artifacts expire after 30 days and are not a permanent release archive. Before promising long-term rollback support, add immutable GitHub Release assets and a retention policy; keep large optional astronomy data outside Pages.

To revert a bad release, fix/revert the source and packaging with a **higher Debian package version**, then build, test and publish again. Simply deploying older versions will not automatically downgrade installed clients. Preserve logs and the old build artifacts while investigating a failure.

## Validation boundary

CI starts with Debian's `indi-bin`, `kstars`, `indi-eqmod` and `indi-gphoto`, upgrades to the built packages, checks dependencies and shared-library loading, runs `kstars --version` with an offscreen Qt backend, and queries an INDI simulator. Third-party tests check installed ELF architecture/dependencies, major driver coverage, XML executable references, firmware, udev rules and preserved notices. Repository tests exercise signatures and APT downloads independently.

Still required for a production release: testing on actual Debian PCs and Raspberry Pi OS installations of both suites, opening KStars/Ekos in a desktop session, and trying the supported hardware. Passing container checks does not certify camera SDK compatibility, USB/udev permissions, GPU rendering, or a complete imaging session.
