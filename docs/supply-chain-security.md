# Supply-Chain Security

This document records the controls that protect this repository against
supply-chain attacks — the Rust/Cargo analog of npm worm campaigns such as
"Shai-Hulud" (malicious package versions, install/build-time code execution,
credential theft, self-propagation).

## Threat model in brief

Cargo has **no install-time scripts** (no `npm postinstall`). Untrusted code
can only execute when we **build**, via:

- `build.rs` build scripts, and
- procedural macros (`syn`/`quote`/`serde_derive`/`darling`/…),

both of which run with the privileges of the building user/CI. The realistic
attack is therefore: a dependency version is compromised, we pull it, and its
build script/proc-macro runs in a context that holds secrets (CI tokens,
registry credentials). The controls below make that path hard to enter and
small in blast radius.

## Controls in place

| Control | Where | What it stops |
|---|---|---|
| Committed `Cargo.lock` + `--locked` everywhere (build/test/Docker/release) | repo, `Dockerfile*`, CI | A newly-published malicious version is not pulled until the lockfile is deliberately updated. |
| `cargo audit` (RustSec advisories) | `.github/workflows/ci.yml` (security job) | Known-vulnerable crates. |
| `cargo deny check` (advisories, bans, licenses, sources) | `deny.toml`, CI | Unknown registries/git sources (`unknown-registry/​unknown-git = deny`), disallowed licenses, yanked crates. |
| `cargo vet --locked` (trust gate) | `supply-chain/`, CI | New/updated crates that are **not** vouched for (by us, a trusted import, or an explicit exemption) fail CI — closes the "compromised version pulled on update" window that locking alone cannot. |
| Imported audits from Google, Mozilla, Bytecode Alliance, Embark, ISRG, ZcashFoundation | `supply-chain/config.toml` | Replaces blanket exemptions with real third-party review. |
| All GitHub Actions SHA-pinned (incl. the `rust-setup` composite action) | `.github/` | A repointed mutable action tag executing in CI. |
| Docker base images digest-pinned (`debian:trixie-slim`, `rust:slim`); `cargo-chef` version-pinned | `Dockerfile`, `Dockerfile.prebuilt` | A swapped base-image tag or build-tool release. |
| Release job split: build (no secrets) ↔ publish (no compilation) | `.github/workflows/release.yml` | A dependency build script can never run in the same job that holds registry tokens / `contents:write`. |
| Least-privilege `GITHUB_TOKEN` (top-level `contents: read`, per-job widening) | all workflows | Reduces blast radius if any step is compromised. |
| Branch protection ruleset on `main` requiring `Security (audit, deny, vet)` + `Checks (fmt, clippy, test)` | repo ruleset (admin bypass) | Merges/pushes that fail the supply-chain gates (for non-admins). |
| Dependabot (cargo, github-actions, docker) | `.github/dependabot.yml` | Stale dependencies / digests; timely CVE patching. |

## Operational requirement: `RELEASE_TOKEN`

`main` is protected by a ruleset that requires the CI checks. On a **personal**
(non-org) repo, GitHub will not let the GitHub Actions bot bypass a ruleset, so
the default `GITHUB_TOKEN` cannot push the release version-bump commit.

**Action required:** create a fine-grained Personal Access Token with
**`Contents: write`** on this repo and add it as the repository secret
**`RELEASE_TOKEN`**. The release workflow uses it (admin-owned ⇒ bypasses via
the admin role) for the bump commit + tag push. The `prepare` job fails fast
with a clear message if the secret is absent.

> Prefer the shortest practical expiry and rotate the PAT regularly; it is the
> one long-lived credential in the release path.

## Maintenance runbook

- **Vet a new/updated dependency:** CI fails with `missing [...]` →
  `cargo vet` (interactive) to audit, or `cargo vet regenerate exemptions`
  to baseline it, then commit `supply-chain/`.
- **Refresh imported audits:** `cargo vet` updates `supply-chain/imports.lock`;
  commit the result.
- **Refresh a Docker digest:** `docker buildx imagetools inspect <image:tag>
  --format '{{.Manifest.Digest}}'`, update the `@sha256:…` pin (Dependabot also
  proposes these).
- **Re-pin an action after a Dependabot bump:** keep the `# vX.Y.Z` comment in
  sync with the SHA.
- **Review audit suppressions:** `audit.toml` / `.cargo/audit.toml` /
  `deny.toml` ignores carry review dates — re-evaluate on schedule.
