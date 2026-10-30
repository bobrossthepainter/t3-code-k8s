# Security policy

Supported packaging: the current main branch and current chart release. Nightly upstream
builds are experimental. This is unofficial packaging, not an upstream security support contract.

For a packaging vulnerability, use GitHub's **Security → Report a vulnerability** private
reporting feature if enabled. If unavailable, contact the repository owner privately through
their GitHub profile. Do not include tokens, pairing links, database files or pod logs in a
public issue. Report T3 Code application issues to the upstream project's security contact.

Image releases block fixable HIGH/CRITICAL Trivy findings on both architectures. Scheduled
rescans can detect newly disclosed issues after publication. CodeQL covers repository Python
and GitHub Actions; Trivy also covers IaC, secrets and recognized dependencies. Upstream's
bundled executable may contain dependencies scanners cannot identify. Scanning and signatures
are defense in depth, not a guarantee of safety or an audit of upstream application code.

Keep this service private where possible; use TLS, upstream pairing and narrow permissions.
Treat `/data`, backups, pairing URLs and startup logs as secrets. Never give this workload a
host Docker socket, privileged access or cluster-admin credentials.
