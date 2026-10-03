# Run Cohort with Docker Compose

This version is on `feat/docker-runner`, based on `feat/auth-i18n-tour`. It includes the login script, English/Traditional Chinese interface and quick-start tour. A checkout of `main` does not yet include those changes.

Docker builds the frontend and Python dependencies. You do not need Node or a Python virtual environment on the host. The image contains code only; credentials, licensed source material, embeddings and saved research stay outside it.

## First start

Use Linux with Docker Engine and Compose v2. This configuration uses host networking so the existing server can bind to `127.0.0.1`. Docker Desktop needs its host-networking option enabled (Desktop 4.34 or later); that environment has not been tested here. See [Docker's host-networking documentation](https://docs.docker.com/engine/network/drivers/host/).

From this checkout:

```sh
mkdir -p data/container
cp -n .env.docker.example .env.docker
printf '\nCOHORT_UID=%s\nCOHORT_GID=%s\n' "$(id -u)" "$(id -g)" >> .env.docker
chmod 600 .env.docker
docker compose --env-file .env.docker build
docker compose --env-file .env.docker run --rm cohort \
  python scripts/setup_ui_auth.py --credentials /state/ui-auth.json
docker compose --env-file .env.docker up -d
```

Do the copy and UID/GID append once. Preserve an existing configuration. The account command prompts for a username and password; there is no default password. The container runs as your host UID/GID so it can read owner-only credentials and write its own state without running as root.

Open **http://127.0.0.1:18766/** and sign in. Initially Graph and Findings are empty. First startup creates an empty research workspace; it never seeds example claims or overwrites an existing graph.

If Docker reports permission denied on its socket, use your machine's authorized Docker access method. This setup does not change host group memberships or daemon permissions.

## Start, restart and stop

```sh
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 50
docker compose --env-file .env.docker restart
docker compose --env-file .env.docker stop
docker compose --env-file .env.docker up -d
```

To apply code changes, use `up -d --build`. To apply configuration changes, use `up -d --force-recreate`; `restart` alone does not reload Compose environment settings. There is one server per state directory because the evidence graph has a single writer. Stop a native server using the same state or port before starting this container.

The restart policy is `unless-stopped`: Docker restarts a crashed container and starts it after a daemon restart unless you deliberately stopped it. An unhealthy status reports a failed check; it does not itself restart a running process. The Docker daemon must be running.

## Corpus, vocabulary and related passages

The host's `data/` is mounted read-only at `/inputs`. Set paths in `.env.docker` using **container paths**, for example:

```dotenv
LOCAL_CORPUS_ROOT=/inputs/radich/corpus/T-stripped
COHORT_RADICH_ROOT=/inputs/radich
EVIDENCE_EMBEDDINGS_PATH=/inputs/embeddings/windows.npz
COHORT_ALLOW_WRITES=1
COHORT_ALLOW_RUNS=1
```

Use your actual directory names. The corpus needs its existing manifest and the vocabulary index needs the catalogue/string files. Precomputed embeddings are supplied separately. Model credentials and model names go in this ignored file too; they are not copied into the image. No output-token cap is added. Enabling runs retains the native per-run monetary threshold. To disable that threshold explicitly, set `COHORT_NO_BUDGET=1`. Starting agent runs can spend money.

For data elsewhere on the host, set `COHORT_DATA_DIR` in `.env.docker` to that existing directory. `COHORT_STATE_DIR` changes the writable state location; it must also exist and belong to your UID. Those host paths become `/inputs` and `/state` inside the container. Missing bind-mount paths fail instead of creating root-owned directories silently.

You can alternatively supply the CBETA archive/index environment variables shown in `.env.docker.example`, using `/inputs/...` paths. For full flags and feature limits, see [the researcher UI](ui.md) and [the Taiwan Mandarin guide](quickstart-zh-TW.md).

## Saved research and account changes

The writable directory holds `research.sqlite`, `research.jsonl`, `ui-auth.json` and caches. The event log is authoritative. Stop the service before backing up the directory; preserve the database and event log together. `stop`, `restart` and container recreation retain this bind-mounted state. Do not delete it to reset a container.

To resume existing research, stop the original server first and copy its database and matching event log into this state directory under the names above. Keep the originals as rollback copies. Do not copy a live SQLite database without its WAL state. Start only one server against the new location.

To change the account:

```sh
docker compose --env-file .env.docker run --rm cohort \
  python scripts/setup_ui_auth.py --credentials /state/ui-auth.json --overwrite
docker compose --env-file .env.docker restart
```

This replaces the local account intentionally. Existing sessions end on restart. Login still protects one shared research workspace; it does not add per-user permissions or licence governance.

## Remote access

The service remains bound to localhost. Forward the port over SSH:

```sh
ssh -N -L 18766:127.0.0.1:18766 USER@SERVER
```

Then open the same localhost URL on your laptop. No proxy, firewall, host service or public deployment is created by these repository changes.

## Verification for this change

On 2026-10-03, the image was built with Docker Engine 29.3.1 / Compose 2.35.1 on Linux. An isolated Compose test used a synthetic account and empty state directory. It verified owner-only credential setup, an unauthenticated graph response of 401, successful sign-in, the built frontend, a non-root/read-only runtime, and one saved research question remaining after a container restart. The test container was removed afterwards.

The Python suite passed 609 tests; Ruff and ty passed. No real licensed data or paid model calls were used in the container test. Docker Desktop, real-corpus startup duration and public deployment were not tested.
