# Operations

## Release inputs

`sources.json` fixes source revisions and the dependency build order: libXISF → INDI → third-party libraries → third-party drivers → StellarSolver → KStars. StellarSolver can also build before the third-party packages. Update revisions deliberately, keep Qt selection compatible, and increment `revision` whenever packaging changes could alter the output. Never publish different bytes under an already-published package version.

Third-party builds adapt the pinned upstream aggregate Debian control files with `scripts/thirdparty.py`; local rules are in `packaging/indi-3rdparty-*`. Two source packages build the same pinned upstream tree, libraries first. All upstream per-component Debian copyright files and in-tree license/notice files are preserved in both binary documentation trees. Their source archives also retain the original vendor binaries; supplying source packages does not imply proprietary SDK source code is available. Keep the Pages size gate enabled as SDKs grow.

Versions have the form `3.8.4-1+rpiastro1~deb12` or `~deb13`. KStars retains Debian's epoch `5:` so APT can upgrade it. The suite suffix both distinguishes artifacts and allows a Bookworm-to-Trixie package upgrade. A manifest commit and build information make the source and environment traceable; the moving Debian package mirrors and base image tags mean bit-for-bit reproducibility is not yet guaranteed.

The build container uses Debian's ARM64 userland, which Raspberry Pi OS 64-bit is based on. The 32-bit Raspberry Pi OS ABI is a separate target and cannot be added just by enabling Debian `armhf`.

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

The private key has no passphrase because it must sign unattended; GitHub's secret store protects it at rest. Its only use is in the publication job, after both builds and tests pass. Protect `main`, review workflow changes, and restrict the `github-pages` environment to `main`. Configure environment reviewers if your release process needs human approval.

Track the expiry date and rotate well in advance. Existing users trust the installed key, so a new key requires a transition signed by the old key or independently verified reconfiguration; silently replacing the website key is not sufficient.

APT Release metadata is signed with both `InRelease` and `Release.gpg`. This initial archive has no `Valid-Until`, allowing a quiet repository to remain installable without periodic signing; that also means an old valid snapshot can be replayed. Add an expiry and a reliable metadata-refresh schedule together if freshness enforcement is needed.

## Publishing and rollback

Only manually dispatched builds of `main` with `publish=true` can deploy. Both suites are assembled from artifacts belonging to that same run. A single deployment replaces the entire snapshot. The public site contains no private keys, reprepro databases, or configuration.

The current snapshot keeps one version per package per suite. Older package URLs can disappear at the next publication; clients should run `apt update` before installation. Actions artifacts expire after 30 days and are not a permanent release archive. Before promising long-term rollback support, add immutable GitHub Release assets and a retention policy; keep large optional astronomy data outside Pages.

To revert a bad release, fix/revert the source and packaging with a **higher Debian package version**, then build, test and publish again. Simply deploying older versions will not automatically downgrade installed clients. Preserve logs and the old build artifacts while investigating a failure.

## Validation boundary

CI starts with Debian's `indi-bin`, `kstars`, `indi-eqmod` and `indi-gphoto`, upgrades to the built packages, checks dependencies and shared-library loading, runs `kstars --version` with an offscreen Qt backend, and queries an INDI simulator. Third-party tests check installed ELF architecture/dependencies, major driver coverage, XML executable references, firmware, udev rules and preserved notices. Repository tests exercise signatures and APT downloads independently.

Still required for a production release: testing on actual Raspberry Pi OS installations of both suites, opening KStars/Ekos in a desktop session, and trying the supported hardware. Passing container checks does not certify camera SDK compatibility, USB/udev permissions, GPU rendering, or a complete imaging session.
