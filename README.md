# T3 Code server for containers and Kubernetes

Unofficial, server-only packaging of [pingdotgg/t3code](https://github.com/pingdotgg/t3code).
No desktop application, provider CLIs (Codex/Claude/etc.), browser dependencies, Docker socket,
SSH daemon, or development toolchain is installed. Upstream's web assets and bundled runtime
libraries are included; no separate Node/npm installation is needed.

> **Architecture:** T3 Code is not a stateless central coordinator. A T3 server normally
> runs providers and terminals on the machine hosting it. This lean image serves the UI/API
> but is deliberately **not prepared for local agent execution**. To run agents elsewhere,
> connect your browser/desktop to those separate T3 execution environments; the upstream
> clients keep their environment connections. Do not assume this pod will transparently
> proxy all work to remote agents. If you want this pod to execute agents, build an explicit
> derivative with provider CLIs, credentials and workspace tools; that is outside this image's scope.

## Published artifacts

Replace `OWNER` with this repository's GitHub owner (lowercase). Workflows derive the actual
registry path automatically; no registry secret or PAT is needed.

| Artifact | Location |
| --- | --- |
| Stable image | `ghcr.io/OWNER/t3-code-k8s:stable` (`latest` is an alias) |
| Nightly image | `ghcr.io/OWNER/t3-code-k8s:nightly` |
| Upstream-version image | `:stable-0.1.5`, `:nightly-0.1.6-nightly.20261030.3940`, etc. |
| Unique build | `:build-CHANNEL-RUN_ID-RUN_ATTEMPT` |
| Helm chart | `oci://ghcr.io/OWNER/t3-code-k8s/charts/t3-code` |
| Release downloads | GitHub Releases: image digest JSON, or chart `.tgz` + `SHA256SUMS` |

Images support **linux/amd64** and **linux/arm64**. Channel and upstream-version aliases
can move on an explicit security rebuild; use `@sha256:...` for an immutable deployment.
Charts have independent semantic versions (`chart-v0.1.0`, etc.); a new upstream image
release does not needlessly republish an unchanged chart.

## Docker

```sh
docker volume create t3-data
# Named Docker volumes need initialization; Kubernetes uses fsGroup instead.
docker run --rm --user 0 --entrypoint chown -v t3-data:/data \
  ghcr.io/OWNER/t3-code-k8s:stable 10001:10001 /data

docker run -d --name t3 --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  -v t3-data:/data -p 127.0.0.1:3773:3773 ghcr.io/OWNER/t3-code-k8s:stable

docker exec t3 t3 auth pairing create --ttl 5m --base-url http://127.0.0.1:3773
```

Open the generated one-time pairing link. For remote clients, use a reachable HTTPS URL,
not `127.0.0.1`. The container listens on `0.0.0.0:3773`; the host port above is intentionally
loopback-only. `/data` is the whole writable home, including `T3CODE_HOME=/data/.t3`.
Keep it private: it contains the database, session grants and other credentials.

## Helm

Requires Kubernetes 1.26+, Helm 3.17+ (also tested with Helm 4), a default StorageClass
or an existing PVC, and access to the published image/chart.

```sh
helm upgrade --install t3 oci://ghcr.io/OWNER/t3-code-k8s/charts/t3-code \
  --version 0.1.0 --namespace t3-code --create-namespace \
  --set image.repository=ghcr.io/OWNER/t3-code-k8s

kubectl -n t3-code port-forward svc/t3-t3-code 3773:3773
kubectl -n t3-code exec deploy/t3-t3-code -- \
  t3 auth pairing create --ttl 5m --base-url http://127.0.0.1:3773
```

For production, additionally set `image.digest=sha256:...` from the release. For nightly,
set `image.tag=nightly` (and clear/change any digest). Floating aliases with `IfNotPresent`
do not automatically roll pods; prefer digest-based GitOps updates.

### Ingress / TLS

Use [examples/ingress.yaml](examples/ingress.yaml) with your ingress controller and TLS
Secret. Configure WebSocket upgrades and long-lived connection timeouts on your controller.
The example uses ingress-nginx annotations; other controllers need their own settings.
`app.t3.codes` requires an HTTPS backend; desktop/direct local pairing can use LAN HTTP.

```sh
helm upgrade --install t3 oci://ghcr.io/OWNER/t3-code-k8s/charts/t3-code \
  --version 0.1.0 -n t3-code --create-namespace \
  --set image.repository=ghcr.io/OWNER/t3-code-k8s -f examples/ingress.yaml
kubectl -n t3-code exec deploy/t3-t3-code -- \
  t3 auth pairing create --ttl 5m --base-url https://t3.example.com
```

**Do not disable upstream authentication or use `T3CODE_DEV_AUTH_TOKEN` in production.**
Pairing links grant powerful permissions by default. Create narrower grants with repeated
`--scope` flags if appropriate. `serve` can print bootstrap pairing details to stdout;
restrict access to pod logs, backups and `kubectl exec` accordingly. Never publish logs
without checking for tokens. A reverse proxy must not strip WebSocket/auth headers.

### Optional Tailscale (recommended for private access)

1. Install and authenticate the [Tailscale Kubernetes operator](https://tailscale.com/kb/1236/kubernetes-operator).
2. Enable MagicDNS and HTTPS certificates for your tailnet; configure ACLs/grants and operator proxy tags.
3. Apply [examples/tailscale.yaml](examples/tailscale.yaml) instead of public ingress:

```sh
helm upgrade --install t3 oci://ghcr.io/OWNER/t3-code-k8s/charts/t3-code \
  --version 0.1.0 -n t3-code --create-namespace \
  --set image.repository=ghcr.io/OWNER/t3-code-k8s -f examples/tailscale.yaml
kubectl -n t3-code get ingress t3-t3-code-tailscale
# Use the assigned https://t3-code.<tailnet>.ts.net URL when creating a pairing link.
```

This creates an `ingressClassName: tailscale` HTTPS Ingress, **not Funnel**: it is private
to the tailnet. The operator manages the separate proxy pod. No auth keys, `NET_ADMIN`,
privileged sidecar, or `/dev/net/tun` access are given to T3. Native `t3 --tailscale-serve`
is intentionally not used because tailscaled is not running inside this pod. Tailnet ACLs
and T3 pairing are separate layers of access control. Public ingress and Tailscale exposure
are mutually exclusive in this chart.

### Configuration

All options and defaults: [charts/t3-code/values.yaml](charts/t3-code/values.yaml).

| Setting | Purpose |
| --- | --- |
| `image.repository`, `image.tag`, `image.digest` | Image selection (repository required, digest wins) |
| `service.type`, `service.port`, `server.port` | Service and container ports |
| `persistence.*` | 5Gi RWO PVC by default; existing claim/storage class supported |
| `server.env`, `server.envFrom`, `server.extraArgs` | Upstream configuration / existing Secret references |
| `ingress.*` / `tailscale.*` | Public/controller ingress or private tailnet HTTPS |
| `resources`, probes, `nodeSelector`, `tolerations`, `affinity` | Basic scheduling/runtime settings |
| `extraVolumes`, `extraVolumeMounts` | Explicit extra mounts (avoid hostPath and container sockets) |
| `networkPolicy.*` | Optional default-deny ingress/limited egress; customize selectors |

The server runs as UID/GID 10001 with a read-only root filesystem, dropped capabilities,
no API token and writable `/data` + bounded `/tmp`. Telemetry is disabled by default.
Resource sizing is for an idle server, not local agent or browser workloads.

Only **one replica** is supported. Deployment updates use **Recreate** (brief downtime),
not overlapping writers. There is deliberately no HPA, multi-replica switch or PDB implying HA.
Probes use the public static root page/TCP listener; upstream has no dedicated health endpoint.
NetworkPolicy is opt-in because controllers, Tailscale proxies and external services need
cluster-specific rules; see [examples/network-policy.yaml](examples/network-policy.yaml).

## Operations

- Back up the entire `/data` volume **with the pod stopped** (including SQLite WAL files).
  For live backups use SQLite's supported backup interface; copying an open database alone
  is unsafe. Encrypt and restrict backup access.
- Snapshot before upgrades. Upstream applies schema migrations; rollback may require restoring
  the matching data snapshot, not merely `helm rollback`. Never run old/new versions against
  the same live PVC.
- Chart-created PVCs are deleted on `helm uninstall`. For independent retention, create the
  PVC outside Helm and set `persistence.existingClaim`. Confirm your storage reclaim policy.
- Update via image/chart releases, not `t3 update` inside the container. `/opt/t3` is immutable.
- The image omits Chrome and its OS dependencies. Browser tabs/HTML renders and local agent
  execution are not supported by this minimal packaging.
- A writable home is not a security sandbox for untrusted agents. If extending this image,
  use separate isolated workloads; do not mount Kubernetes credentials or Docker sockets.

## Build and release automation

See [docs/maintaining.md](docs/maintaining.md) for initial GitHub setup, publishing,
security rebuilds, signatures, test commands and release recovery.

- Hourly upstream tracker selects published stable and nightly releases, never preview/alpha.
- Separate stable/nightly workflows run only when their successful-release marker is absent.
  A failed channel doesn't prevent the other from building; failed releases retry next poll.
- Downloads are exact-version archives verified against upstream `SHA256SUMS` for each arch.
- Both native architecture jobs must pass runtime smoke tests and Trivy's **fixable
  HIGH/CRITICAL** gate before signed multiarch images receive public channel aliases.
- BuildKit attaches SBOMs and provenance; Cosign keyless signatures bind artifacts to Actions.
- Daily Trivy rescans published images for newly disclosed CVEs; CodeQL scans Python and Actions,
  Trivy scans repository IaC/secrets/dependencies, and dependency review checks PR changes.
- Dependabot updates Actions/Python; Renovate configuration tracks the pinned Ubuntu base digest.

Upstream's checksum file is fetched from the same GitHub release as its binaries: this detects
corruption/mismatched assets, **not a compromised upstream publisher**. Container scanners also
cannot prove the absence of vulnerabilities inside every bundled single-executable dependency.
This repository packages upstream binaries; it does not rebuild or comprehensively audit upstream.

## License

Packaging/chart/scripts: [MIT](LICENSE). T3 Code is separately distributed under its
[upstream MIT license](https://github.com/pingdotgg/t3code/blob/main/LICENSE).
Upstream archives include third-party runtime dependencies and notices; their respective
licenses still apply. This project is not affiliated with or endorsed by T3 Tools.
