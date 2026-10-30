# Maintaining and publishing

## First-time GitHub setup

1. Authenticate the GitHub CLI on this host: `gh auth login` (do not paste a token in chat).
2. Create the public repository and push:

   ```sh
   git add . && git commit -m "Add T3 Code server container, releases and Helm chart"
   gh repo create OWNER/t3-code-k8s --public --source . --remote origin --push
   ```

3. Enable GitHub Actions and repository **Code security** features: dependency graph,
   Dependabot alerts/security updates, secret scanning and push protection where available.
   CodeQL is configured through the advanced workflow; do not also enable a duplicate default setup.
   Actions use the repository `GITHUB_TOKEN`; no long-lived registry credentials are required.
4. Run `gh workflow run track-upstream.yml`. Stable/nightly releases build independently.
5. After the first package pushes, **set both GHCR packages to public** in package settings
   (the image and `charts/t3-code`); public source repositories do not guarantee public package
   visibility. Check an unauthenticated pull, including the OCI chart. Subsequent pushes must
   have repository Actions access to both packages. Forks use their own repository path.
6. Publish the chart: `git tag chart-v0.1.0 && git push origin chart-v0.1.0`, or manually run
   `release-chart.yml`. The tag must match `Chart.yaml`'s version. Manual publishing uses that
   same version and creates the release tag only after publishing succeeds.
7. Protect `main`, require review and CI, and restrict tag creation/Actions workflow changes.
   If Actions are disabled by org policy, explicitly allow the pinned actions used here.
8. Optionally install/authorize the Renovate GitHub App. `renovate.json` alone doesn't run it.
   Dependabot runs without that app, but does not update Docker base digests here.

GitHub may delay scheduled workflows or disable schedules in inactive public repositories.
Monitor failed Actions runs; manual workflow dispatch remains available. These workflows do
not open issues or send external notifications automatically.

## Image release and recovery

```sh
gh workflow run release-stable.yml
gh workflow run release-nightly.yml
# Rebuild current stable after packaging/OS changes:
gh workflow run release-stable.yml -f force=true
# Choose a specific published version (channel is validated):
gh workflow run release-stable.yml -f version=0.1.5 -f force=true
```

`track-upstream.yml` polls GitHub's latest stable release and the 100 most recent releases
for the newest published nightly. Previews and drafts are excluded. If no nightly appears
in that window the check fails visibly rather than selecting a wrong channel. Already-published
`stable-vVERSION` / `nightly-vVERSION` GitHub releases are the success markers; they are written
only after scans, tests, manifest assembly and signing pass. Checks run again inside each
channel's concurrency lock. A failed stable lookup does not suppress a detected nightly update.
No branch commits, PAT-triggered workflows or mutable cache-based state are needed.

Manual releases can move channel aliases to an older version: this is intentional, so verify
the version you select. Force rebuilds refresh OS packages (`no-cache`); they retain upstream
version aliases but create unique build tags and replace the digest in release metadata.
Deployments pinned to a digest do not update automatically. Packaging changes do **not**
automatically force an image release; use the explicit dispatch after CI passes.

Staging tags are published before testing but **never deployed** by the chart. Both native
architecture jobs must succeed before channel aliases move. A vulnerability gate failure leaves
the previous alias intact. Investigate the SARIF finding; update the base/upstream dependency
and retry. Do not broadly suppress CVEs to make a release green. Daily scans report all
HIGH/CRITICAL findings, including unfixed vulnerabilities; the release gate blocks only fixable
HIGH/CRITICAL findings. Use a full local Trivy scan when reviewing lower-severity issues too.

Clean old `staging-*` / `build-*` GHCR versions according to your retention policy, preserving
referenced digests, signatures and attestations. Cleanup is not automatic: registry artifacts
can contain multiple tags/referrers and careless deletion can break pinned deployments.

## Chart release

Increment `charts/t3-code/Chart.yaml:version` for every chart change, test, merge, and push
`chart-vX.Y.Z`. Chart versions are independent of upstream stable/nightly. The chart workflow
publishes an OCI artifact, keyless signature, a GitHub release archive and archive checksums.
A Helm repository index/GitHub Pages site is unnecessary; Helm installs OCI charts natively.
The chart's `appVersion` is informative; `image.tag`/`image.digest` select the deployed server.
Don't overwrite an already-published chart version with changed contents; bump it instead.

## Verification

Install [Cosign](https://docs.sigstore.dev/cosign/system_config/installation/), then use the
artifact digest from the release. The signing job is in the reusable implementation workflow;
verify its exact identity, not an arbitrary owner-wide regex:

```sh
cosign verify ghcr.io/OWNER/t3-code-k8s@sha256:DIGEST \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity https://github.com/OWNER/t3-code-k8s/.github/workflows/release-image.yml@refs/heads/main

cosign verify ghcr.io/OWNER/t3-code-k8s/charts/t3-code@sha256:DIGEST \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity https://github.com/OWNER/t3-code-k8s/.github/workflows/release-chart.yml@refs/tags/chart-v0.1.0
```

A manually dispatched chart release uses `@refs/heads/main`, not a tag, in its identity.
For image SBOM/provenance, inspect the image index with Docker Buildx; the architecture
manifests carry BuildKit SPDX and SLSA attestations:

```sh
docker buildx imagetools inspect ghcr.io/OWNER/t3-code-k8s@sha256:DIGEST \
  --format '{{json .SBOM}}'
docker buildx imagetools inspect ghcr.io/OWNER/t3-code-k8s@sha256:DIGEST \
  --format '{{json .Provenance}}'
```

Signing uses GitHub OIDC and Sigstore's public transparency log. No private signing keys
are stored in the repository. Do not release from an unreviewed branch, and don't relax
identity verification to match one.

## Local development

Requirements: Python 3.10+, Helm 3.17+, Docker/Buildx, curl. Test-only Python dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
# Also run actionlint, shellcheck scripts/*.sh and kubeconform when installed.

python3 scripts/upstream.py --channel stable > /tmp/t3-release.json
# Pass version and BOTH checksums from that JSON, not unpinned dist-tags:
docker build -t t3-server:test \
  --build-arg T3_VERSION=VERSION \
  --build-arg T3_SHA256_AMD64=SHA256 \
  --build-arg T3_SHA256_ARM64=SHA256 .
bash scripts/smoke.sh t3-server:test
```

CI tests the resolver with mocked releases/checksums/failures, Helm defaults and variants,
values validation, Kubernetes schema validation and native runtime startup/pairing/restart.
The release jobs repeat runtime tests natively on AMD64 and ARM64; no QEMU is used.
The smoke test deliberately avoids printing logs or pairing tokens.
