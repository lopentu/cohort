# Login, language and first use

The authenticated bilingual UI is included on `main`. React 18 and Vite remain the frontend; Radix UI supplies shared interactive primitives, and i18next/react-i18next supply localization. The graph still uses vis-network.

For a container installation, use the [Docker guide](docker.md); it builds the frontend and supplies persistent state. The native instructions below still apply.

## Create the account

After `uv sync --extra dev --extra ui --extra evidence`, run:

```sh
uv run python scripts/setup_ui_auth.py
```

The command prompts for a username, a password of at least twelve characters, and confirmation. It saves only a salted scrypt verifier in `data/ui-auth.json`, with owner-only permissions. No default password is shipped. Never pass a password in a command argument or commit the credentials file.

To replace the account, run the same command with `--overwrite`, then restart the server. Existing sessions end when the server stops. Keep the credential file on the machine that runs the server; it is not needed on an SSH client laptop.

## Start and connect

Continue using `scripts/serve_ui.py` with your existing `--db`, `--log`, `--corpus`, `--radich`, and run/write options. Login is required by default. An alternative credentials location can be supplied with `--auth-file /path/to/ui-auth.json`.

```sh
uv run python scripts/serve_ui.py --db data/session/research.sqlite \
  --log data/session/research.jsonl --corpus --allow-writes --allow-runs \
  --radich /path/to/radich --host 127.0.0.1 --port 18766
```

Open `http://127.0.0.1:18766/` and sign in. For a remote server, keep the application bound to localhost and use SSH forwarding:

```sh
ssh -N -L 18766:127.0.0.1:18766 USER@SERVER
```

The normal server explicitly permits localhost HTTP for this arrangement and ignores forwarded protocol headers. Direct non-local HTTP login is refused; programmatic deployments using HTTPS set a Secure cookie. This change does not publish the service or set up a public HTTPS deployment.

`--no-auth` is an explicit opt-out for controlled localhost development. It is not the recommended way to start a research session. Programmatic callers of `create_app` must provide `auth=AuthManager.from_file(...)` to enable the same protection; the factory's default remains compatible with existing local tests and scripts.

## Language and tour

Use the language selector on the login screen or top toolbar to choose English or 繁體中文. The selection is saved in that browser. Switching language changes interface controls and explanations, not source passages, saved questions, model output or graph identifiers.

The quick-start tour appears on first entry. It covers only the features enabled on this server, can be skipped, and can be reopened from Quick start / 快速上手. Open this tab closes the tour and takes you to the selected feature. The tour never launches a model run, accepts a proposal or writes research data.

## Session behavior and scope

Sessions have a thirty-minute idle timeout and an eight-hour absolute limit. Sign out revokes the session. If it expires, the interface returns to login; research records remain saved. Background polling counts as server activity, so an open active view may keep the idle timer fresh, but not the absolute timer. Login/logout do not stop a running inquiry; server shutdown interrupts unfinished runs.

There is one researcher account and one shared set of research records. Login protects HTTP access; it does not create personal workspaces, change the evidence-graph researcher identity, or implement corpus licence governance. ATELIER remains separate and unconnected.

Localhost HTTP assumes that local processes and other services on the same browser hostname are trusted. Cookies are not isolated by port: a malicious service visited at another port on `127.0.0.1` can receive the session cookie. HttpOnly prevents JavaScript from reading it, and SameSite blocks cross-site requests; neither provides port isolation. For stronger separation, use a dedicated hostname with HTTPS and review that deployment separately. Keep the current server behind localhost and SSH forwarding.

Login attempts are limited per client and across the server before password hashing. Forwarded client addresses do not bypass that limit. A local process can still exhaust it and temporarily prevent sign-in; the limit protects guessing and hashing cost, not availability against hostile local software.

On 2026-10-03, the authentication suite passed 40 synthetic tests, including every registered research route, encoded paths, copied-cookie replay after logout, tokens from another session, oversized streamed login bodies and spoofed forwarded addresses. An independent code review found no authentication bypass within the localhost deployment. A live container check returned 401 before login, 200 after login and 401 when a logged-out cookie was replayed. These checks do not prove that every possible attack is excluded.

Credential setup, password verification, session handling and route protection live in `cohort/ui/auth.py` and `scripts/setup_ui_auth.py`. Frontend session handling lives in `src/auth/` and `src/request.js`; translation resources live beside `src/i18n.js`; shared Radix primitives live in `src/components/ui/`; onboarding lives in `src/onboarding/`.
