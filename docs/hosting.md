# Hosting Cohort at /cohort

This is a preparation package for `https://lopen.linguistics.ntu.edu.tw/cohort/`. It does not install or publish the service. The current localhost installation remains intact. The requested migration preserves the saved graph, event log, account, corpus, vocabulary inputs, embeddings, attribution cache and model configuration.

## Boundary

Service ID: `service.cohort`. Governance remains **discovery**; the proposed runtime is always-on Compose. nginx terminates HTTPS, redirects `/cohort` to `/cohort/`, strips the prefix and forwards to a localhost-bound backend. Frontend assets and every API/help link work beneath that prefix. FastAPI/Uvicorn receive the explicit root path. Proxy trust is restricted to declared loopback addresses, and nginx replaces incoming forwarding headers.

| Responsibility | Prepared location |
|---|---|
| Reviewed code and deployment manifest | `/opt/lope/services/cohort` |
| Non-secret configuration | `/etc/lope/services/cohort/cohort.env` |
| Account verifier and model credentials | `/etc/lope/secrets/cohort` |
| Graph, event log and attribution cache | `/srv/lope/services/cohort/workspace` |
| Read-only serving copy of corpus and vocabulary data | `/srv/lope/services/cohort/inputs/radich` |
| Read-only embedding file | `/srv/lope/services/cohort/embeddings` |

`deploy/compose.yaml` requires an explicitly reviewed image reference and approved numeric runtime UID/GID. It has no public listener, no added privileges, a read-only root filesystem and explicit pre-existing mounts. `deploy/cohort.env.example` separates configuration from secrets. Copy only model credential variables into the private `model.env`; retain the existing model/model-pool settings in configuration. Never print a resolved Compose configuration containing secrets: use `config --quiet`.

Secrets directories remain root-controlled and unavailable to ordinary host users. The account verifier is owner-only and owned by the approved container UID, because the application verifies ownership. Bind that file read-only; do not weaken its permissions to make login work. Model credentials are read by Docker from the root-owned environment file, not placed in Git, command arguments or application logs. The workspace belongs to the runtime UID. Inputs must be readable inside their read-only mounts while their host parent remains protected.

The existing application still has **one account and shared research records**. This preparation adds no anonymous corpus access or new users. Cookie paths are not browser-origin isolation: other applications on the same public hostname must be trusted. A separate hostname would be needed to isolate Cohort from a compromised sibling application.

## Required decisions before activation

- Register `service.cohort` and the actual data/state dependencies in the authoritative fleet catalog, referencing a Notion ownership/acceptance record. Do not invent owner references or provenance entries to pass validation.
- Record the service owner, operational maintainer, data/access authority, backup owner and acceptance authority. The instruction is to preserve existing data and account access; broader access is outside this preparation.
- Approve the runtime UID/GID and resource envelope from target-host evidence. Blank values in the example deliberately prevent accidental startup.
- Choose a distinct protected backup destination, retention and recovery objectives, and verify a restore there. The local migration snapshot is recovery evidence, not an accepted off-host backup.
- Confirm the final source snapshot and immutable input checksums immediately before copying. Quiesce source writes at cutover so two workspaces cannot diverge.
- Authorize the exact canonical installation, protected data/credential transfer, nginx location installation/reload and source-runtime transition. No firewall or DNS change is needed for the observed existing HTTPS site.

The discovery contract is `lope-service.json`. It is not active, and absent fleet-catalog registration blocks cross-validation and deployment. Dependency declarations must be completed from the approved catalog before advancing its lifecycle. Nothing in this document waives a failed validator.

## Static validation

From the authoritative server-utils checkout, first run its catalog/review validator and focused validator/exporter tests. Then run the service checker from the actual installed skill directory:

```sh
uv run python scripts/validate_fleet_resource_review.py \
  --sources catalog/evidence-sources.json \
  --queue catalog/fleet-resource-review-queue.json \
  --decisions catalog/fleet-resource-review-decisions.json \
  --resources catalog/fleet-resources.json

uv run --script /home/richard/.agents/skills/lope-service-lifecycle/scripts/validate_service_contract.py \
  /path/to/cohort/lope-service.json --repository-root /path/to/cohort \
  --catalog catalog/fleet-resources.json
```

The installed skill path above is the one resolved for this preparation; another controller must locate its installed `SKILL.md` and use that directory. The draft can also be structurally checked without `--catalog`, but that is not deployment acceptance.

## Snapshot and transfer

`scripts/snapshot_ui.py` takes the graph's writer lock, uses SQLite's backup API (including WAL), copies the log, replays it independently and writes private checksums only after verification. It refuses an active writer and an existing destination. A failed directory without a valid manifest is incomplete; preserve it for diagnosis and retry to a new location.

```sh
uv run python scripts/snapshot_ui.py --db /path/to/current/research.sqlite \
  --log /path/to/current/research.jsonl --destination /path/to/new/private-snapshot
```

Transfer the verified database and event log together. Do not copy a live `.sqlite` file alone, seed a new graph, rewrite identifiers, or delete the original. Preserve the account verifier separately; do not transfer the plaintext initial-password note to the hosted service. Sessions intentionally do not migrate.

Copy the Radich directory, the existing embedding file and the matching attribution-cache/HMAC-key pair to their serving locations. Record per-file size/checksum and any symlink target privately, then verify the destination against that ledger. Keep the `/inputs/radich` container path unchanged because the attribution cache is keyed by that path. Configure the same corpus root, embedding file and models as before. Never expose the inputs through nginx or static-file mounts.

Before activation, run replay verification and SQLite integrity checks against the transferred copy; compare identifiers/counts with the snapshot manifest. Verify corpus/vocabulary unit identifiers and input checksums against the private source ledger. Bind both input mounts read-only. Protect backups and ledgers at least as strongly as the research data.

## Start

After the catalog, contract, responsibility, configuration and transfer gates pass, start only the canonical service. Build the reviewed revision using the root Dockerfile and record the resulting image ID before setting `COHORT_IMAGE`. Keep the previous image/configuration available for rollback.

```sh
docker compose --env-file /etc/lope/services/cohort/cohort.env \
  -f /opt/lope/services/cohort/deploy/compose.yaml config --quiet
docker compose --env-file /etc/lope/services/cohort/cohort.env \
  -f /opt/lope/services/cohort/deploy/compose.yaml up -d --no-build
```

Inspect health without dumping environment values. The local health route is `/api/auth/session`: expect `enabled: true`, `authenticated: false`, `username: null` and `csrf_token: null` without a cookie. A 200 by itself is insufficient.

Only after local and protected functional checks pass should the reviewed `deploy/nginx-cohort.conf` become the existing HTTPS vhost's `locations.d` entry. Capture the original proxy configuration first, run the installed nginx syntax check, and reload only after explicit cutover approval. Do not proxy to a home checkout. Do not overwrite another application's route.

## Stop

```sh
docker compose --env-file /etc/lope/services/cohort/cohort.env \
  -f /opt/lope/services/cohort/deploy/compose.yaml stop
```

Stop interrupts unfinished inquiries. Coordinate with the researcher first. Do not remove volumes, state or input directories as part of stop/restart.

## Functional check

Verify `/cohort` redirects to `/cohort/`, the built login screen loads, and unauthenticated graph, corpus, run and documentation requests return 401. Sign in over HTTPS; check a Secure, HttpOnly, SameSite cookie scoped to `/cohort/`. Wrong-host/foreign-origin requests and spoofed forwarding headers must not authorize actions.

Open every tab in English and Traditional Chinese, inspect an existing question/finding, search a short known phrase, fetch its source position and check the existing vocabulary and embedding settings. Compare preserved identifiers/counts against the verified snapshot; limited graph views are not whole-graph totals. Help links and network requests must stay under `/cohort/`.

Save a synthetic question in an isolated rehearsal copy, restart, sign in again and confirm it remains; sign out and confirm a copied session cookie no longer works. Never use a paid model run as a default deployment health check. A real inquiry needs separate spending authority and an available corpus/model; retain the existing monetary threshold.

## Recovery

Restore graph and log together into an isolated new workspace, never over live state. Verify checksums, SQLite integrity and `Graph.open_read_only(...).rebuild(log_path=...)`, then exercise the protected functional workflow. Restore input files from their named authority/verified serving-copy ledger, and restore credentials through the approved protected process. Model tokens and password notes must not enter ordinary recovery evidence.

A successful local snapshot/replay does not prove scheduled backup, retention, off-host recovery or owner acceptance. Those remain activation gates until tested and recorded.

## Rollback

Trigger rollback on failed replay/checksum, missing records, wrong corpus/model settings, authentication/prefix regression or a failed neighboring-site check. Disable the new route or restore the captured prior nginx file and validate/reload; stop the candidate service. Preserve candidate state/logs privately for diagnosis. Restore the pinned prior code/image and configuration when needed; never destructively synchronize databases backward.

Keep the original localhost code, image and workspace intact until acceptance closes the rollback window. If new hosted writes have occurred, preserve/reconcile that event log before resuming an older workspace: rolling back a proxy is not permission to discard research. Verify researcher access, graph replay and neighboring routes after rollback.

## Handoff

Repository preparation and synthetic tests do not mean the service is live. Record exact source/image revisions, destination checksums, responsibility decisions, backup/restore proof, catalog validation and acceptance in Git-owned technical evidence and Notion-owned task/server/maintenance records. Re-fetch every Notion write. Update the dashboard only with approved public-safe service status, never raw topology, credential paths or corpus details.

Before activation, keep unknown measurements null and missing ownership/catalog decisions explicit. The deployed contract may advance to `active` only after the gates and functional checks pass.

## Preparation verification

The preparation passed 650 Python tests, 35 frontend tests, ruff, ty and the Vite production build. The candidate nginx configuration passed an isolated syntax check. An isolated Compose container using synthetic inputs passed HTTPS login/logout, all five tabs in both languages, application-scoped help/API links, corpus search, vocabulary comparison and embedding availability. A saved synthetic question retained its graph identifiers after restart; sessions expired as intended. The existing monetary threshold remained unchanged. No paid model requests were made.

A protected snapshot of the current workspace passed independent event-log replay and SQLite integrity checks. A private input checksum ledger records the serving inputs and account verifier for later transfer verification. These checks do not establish an off-host backup.

The authoritative fleet catalog validator and its focused tests passed (320 tests and 118 subtests). The discovery service contract passed structural validation. **Catalog binding failed because `service.cohort` is missing from the fleet catalog. Activation remains blocked.** Ownership, backup and acceptance records must be completed before installation. No live proxy, DNS, firewall, fleet catalog or Notion records were changed during preparation.
