# Cohort hosting preparation

**Goal:** Prepare the existing application for HTTPS hosting at `/cohort/` without changing a live proxy, publishing restricted data or replacing the current workspace.

**Architecture:** nginx strips `/cohort` and forwards to a localhost-bound Compose service. Relative frontend assets and a shared URL helper keep every tab and illustrated guide under that prefix. Explicit launcher settings declare the ASGI root path, public HTTPS origin and trusted loopback proxy addresses; native localhost serving keeps its existing defaults.

**Constraints:** Absolute Python imports; no model output-token cap; no corpus or credential contents in Git; one graph writer; authentication remains required for normal launch. Public hosting uses Secure, HttpOnly, SameSite cookies scoped to the application path. The existing home deployment stays available as rollback evidence. No live fleet, DNS, account, catalog or proxy mutation is part of this preparation.

- [ ] Add failing tests for prefixed requests/assets and hosted login origin/cookie behavior; implement shared path handling and explicit launch settings.
- [ ] Prepare canonical Compose/config/nginx artifacts and a discovery service contract; record catalog, ownership, data-access and backup gates.
- [ ] Verify synthetic HTTPS proxy/browser workflows, restore and restart behavior, Python/frontend suites, ruff, ty, and service validators. Obtain an independent review and publish the preparation branch.

Canonical boundaries: `/opt/lope/services/cohort` (code), `/etc/lope/services/cohort` (configuration), `/etc/lope/secrets/cohort` (credentials), `/srv/lope/services/cohort` (state). Service ID: `service.cohort`.
