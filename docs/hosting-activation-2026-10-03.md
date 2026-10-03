# Hosted instance — 2026-10-03

URL: <https://lopen.linguistics.ntu.edu.tw/cohort/>. Use the existing account.
This is a temporary hosted demonstration. The owner explicitly deferred formal
production onboarding. Do not describe it as a completed managed-service handoff.

Richard confirmed the service owner, maintainer, backup contact and acceptance
roles in the [deployment task](https://app.notion.com/p/Deploy-Cohort-at-cohort-with-preserved-research-workspace-3eec41a93bbd81618f75e68dc8b09d3e).
The same restricted account and data access remain in effect; no anonymous
research access or new accounts were added.

## Runtime

Reviewed application revision: `2a46bed`, including PRs #12–#16, merged into
main at `994800b`. Image `cohort:2a46bed`:
`sha256:ca9b47bed1040fa75b450a94e0c4ef06233234eb48750bc6d771a2c081e235be`.
The previous image `cohort:11b35aa` is retained for rollback.

Code is under `/opt/lope/services/cohort`; configuration under
`/etc/lope/services/cohort`; credentials under `/etc/lope/secrets/cohort`;
workspace and read-only inputs under `/srv/lope/services/cohort`.
Compose service: `cohort-hosted-cohort-1`, runtime UID/GID `1011:1012`.
The backend listens only on `127.0.0.1:18766`. The existing HTTPS nginx site
proxies `/cohort/` through `/etc/nginx/locations.d/cohort.conf`.
Docker starts the service again after reboot (`restart: unless-stopped`).
The original localhost container, image and workspace remain intact.

To restart on Lopen (unfinished inquiries will be interrupted):

```sh
sudo docker compose --env-file /etc/lope/services/cohort/cohort.env \
  -f /opt/lope/services/cohort/deploy/compose.yaml restart
```

Start and stop use the same command with `up -d --no-build` or `stop`.
Do not print resolved Compose configuration: it includes model credentials.

## Recovery evidence

The protected source snapshot and isolated NAS restore both replayed 1,281
events into 701 nodes and 722 edges. SQLite integrity passed. All 38,380
input/cache files matched their private size/checksum ledger at the NAS backup
and again after restore: 2,844,269,294 bytes. The account verifier also matched.
The source event log still matched the snapshot before installation.

Initial backup:
`/mnt/nas/projects/resources/cohort-backups/20261003-initial`, on the existing
`10.50.0.10:/volume1/projects` NFS mount. Backup directories are root-only;
credentials and licensed contents remain outside Git and ordinary logs.
Retain this initial snapshot until the owner decides otherwise. It predates
future hosted writes; scheduled Cohort backups and numeric RPO/RTO are not
configured or promised. The NAS is distinct from the application server;
an offsite replica of this specific snapshot was not verified.

Isolated restore and pre-change nginx/container/listener evidence:
`/var/backups/server-utils/cohort/20261003-hosted-activation`.
Restore graph and log together into a new workspace; verify checksums and
`Graph.open_read_only(...).rebuild(log_path=...)` before serving it.

## Rollback

Stop the hosted service with the command above. Remove only the newly added
`/etc/nginx/locations.d/cohort.conf`, run `sudo nginx -t`, and reload nginx.
Retain hosted records for reconciliation before returning to the original
localhost workspace; do not discard hosted writes or synchronize backward.
The original installation was not stopped or deleted during this deployment.

## Checks and remaining work

The valid-certificate HTTPS login page loads; anonymous research API requests
return 401; the new container is healthy; the existing site home still loads.
The help pages are intentionally public and contain no restricted corpus data.
The hosted UI check covers the existing login, secure scoped cookie, preserved
graph identifiers and vocabulary units, five tabs in both languages, guide links,
logout and requests staying under `/cohort/`. Final results are recorded in the
UI sweep document.

Formal service/catalog activation, long-term backup scheduling and a production
handoff remain deferred. Their discovery drafts are not live-service acceptance.

## Hosted account reset

At the owner's request on 2026-10-03, the hosted `researcher` password was
rotated and the Compose container recreated to load the new verifier and end
existing sessions. The new password was delivered through an owner-only local
file; no password value entered Git, chat, arguments or ordinary logs. The
previous verifier is retained in a root-only password-reset checkpoint beneath
`/var/backups/server-utils/cohort`. The initial migration backup contains the
previous verifier, so restoring it would require another authorized password
reset. HTTPS login with the new password passed, the previous password returned
401, and the graph still contained 701 nodes and 722 edges. No inquiry was
running at restart.

Later the same day, the owner created a chosen username/password through the
interactive setup tool. That verifier replaced the temporary generated login;
the hosted container was recreated and loaded it with valid ownership and
permissions. The saved graph again replayed 1,281 events, 701 nodes and 722
edges. The setup tool saved only the salted verifier, not the chosen password.

## Functional verification and analysis repair

A private copy of the hosted workspace completed a real worker/reviewer inquiry
through Chromium. It made eight tool calls and nine model calls; the recorded
spend was $0.11205135. The reviewer refused an initial citation check and
attested a corrected one. These checks changed only the isolated copy.

The hosted read-only audit passed 26 API checks. The complete regression suite
passed 651 tests; 12 frontend test files, ruff, ty and the UI build passed.
The rebuilt UI passed 38 synthetic browser states without accessibility,
overflow or page errors. Earlier expanded and stateful synthetic checks also
passed. The build still warns about its large application chunk.

PR #15 repairs a separate blocker: view analyses and follow-ups omitted the
spending budget, so bounded servers refused them before calling a model.
Both now use the advertised default budget. Independent review approved the
change; server spending ceilings and unlimited output tokens are unchanged.
The repair is merged into main at `9ba1078`. Its fix is included in the hosted `cohort:2a46bed` image described above.

Live Evidence and Graph analyses and a follow-up remain pending explicit
approval to send restricted corpus-derived material to OpenRouter. Automatic
approval review blocked those checks; do not describe them as verified.

## Top tab refinement

PR #16 removes the colored bottom underline from selected tabs, retaining the
selection background and bold label. Twenty tab states across desktop/mobile
sizes and light/dark themes passed browser checks; screenshots were inspected
using synthetic data. Frontend tests, build, ruff and ty passed. The design
detector reports pre-existing warnings elsewhere in the stylesheet; those
styles are outside this narrow refinement.

The image was activated with no graph writer running. Configuration changed
only the image setting. A protected checkpoint at
`/var/backups/server-utils/cohort/20261003-tab-accent` preserves configuration,
account verifier, workspace snapshot and the isolated AI check archive. The
old image remains available; activation had an automatic health rollback.
The new container is healthy, the chosen account verifier matches, and the
public HTTPS page serves the updated CSS. Anonymous research APIs still return
401. A fresh hosted read-only audit passed 26 checks and confirmed 701 nodes
and 722 edges, with no paid model calls or research writes. The external AI
analysis approval remains pending.
