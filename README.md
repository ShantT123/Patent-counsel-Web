# Patent Counsel Workspace

A standalone, single-team website for Portfolio Strategy, Invention Intake and Filing Review. Members sign in with website accounts; no ChatGPT account or skill installation is required. The server owns one OpenAI API key.

## What works

- Administrator-created member/admin accounts, account disabling, expiring cookie sessions and command-line password reset.
- Shared matters, source notes/uploads, per-skill conversation history, saved drafts, original calculators, activity history and complete JSON exports.
- The exact installed skill instructions and all Markdown references are supplied to draft runs. The bundled original Python scripts execute calculator runs without network access. Skill file hashes and upstream commit are in `skill-manifest.json`.
- Every run retains source snapshots, input, skill hashes, result, actor and status. A submitted run ID is not replayed. The activity log is an application history, not an immutable compliance audit.
- Server-only OpenAI Responses API requests, no browser key field, `store:false`, explicit completion checks, no automatic retry, per-user run limits and source/input limits.

This build has not been connected to a real API key or publicly deployed. Mocked API tests verify request construction and persistence; they do not verify account access, billing or real model output.

## Run locally

Python 3.11+ is sufficient; the development server has no third-party dependencies. Create the first administrator interactively, so the password does not enter shell history:

```sh
python3 app.py create-admin --email you@example.com --name 'Your name'
APP_ENV=development APP_ORIGIN=http://127.0.0.1:8096 python3 app.py serve
```

Open http://127.0.0.1:8096. Without an API key/model the original calculators remain available and AI runs explain the missing configuration. The local server binds to loopback only.

To enable AI, supply `OPENAI_API_KEY` and `OPENAI_MODEL` using your hosting secret manager or a secure shell environment. `.env.example` documents the names; the app intentionally does not automatically load `.env` files. Never place a key in public assets, source control, a browser setting or chat.

## Production hosting

The included Dockerfile runs Gunicorn with one process and eight threads. Any Linux host supporting Python or Docker and persistent storage can run it. For a Python host: install `requirements.txt`, then start `gunicorn -c gunicorn.conf.py app:application`.

Set:

| Setting | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_ORIGIN` | Exact HTTPS site origin, e.g. `https://patents.example.com`, without a path |
| `DATA_DIR` | Path on an attached persistent disk, e.g. `/data` |
| `OPENAI_API_KEY` | Your project key, as a hosting secret |
| `OPENAI_MODEL` | A Responses-compatible model your API project can access; no model is silently selected |
| `BOOTSTRAP_ADMIN_EMAIL` | Optional first admin email |
| `BOOTSTRAP_ADMIN_NAME` | Optional first admin display name |
| `BOOTSTRAP_ADMIN_PASSWORD` | Optional first admin password of at least 14 characters, as a hosting secret |

An empty database plus both bootstrap credentials creates the first administrator. Remove the bootstrap password from hosting after first successful sign-in; it is not used to reset or recreate existing accounts. Alternatively use the interactive CLI on the host. The site provides no public signup. Admins add accounts from Team access and share credentials separately; the app sends no emails.

Use one service instance with persistent SQLite storage. Do not scale this configuration horizontally or run it on ephemeral storage. Configure HTTPS at the host, backups with restricted access and a retention/removal process. Use SQLite's backup API for consistent live backups, rather than copying only the database while WAL writes are active. Filesystem encryption and backup encryption are host responsibilities. Roles distinguish account administration; every active member can access every matter. This is not a multi-tenant customer portal.

If hosted on Render, the app needs a Git repository or built container image, a persistent disk and the secrets above. No Render service or paid resource has been created. The current workspace is not attached to a Git remote, so no deployment URL is claimed.

## Review and operations

- Text, Markdown, JSON and CSV uploads only: 100 KB per upload in the UI, 100,000 characters on the server; at most 12 sources and 180,000 source characters per matter. No PDF/Word/OCR parser is included.
- Up to 21 draft turns per skill/matter; earlier same-skill completed drafts accompany the next request. A bounded run snapshot includes all selected sources and history. Large matters are rejected rather than silently truncated.
- Calculator JSON must follow the skill's exact schema. Input requirements are available in the app. Numeric results are labelled separately from AI drafts.
- No web search, agent tool execution, legal docket actions or automatic filings. Runtime model output is treated as text, never executable HTML or code. AI source assertions still require human verification.
- Login sessions expire after 12 hours. Passwords are PBKDF2-HMAC-SHA256 hashes with independent salts and 600,000 iterations. Production cookies are HttpOnly, Secure and SameSite=Strict. Mutating requests check the configured Origin. Account disabling revokes sessions.
- Each user is limited to 20 run reservations per hour. This is not a monetary budget; configure project spend limits and monitor usage separately. A key/model being configured is not proof it works.
- Timed out/interrupted upstream requests may have incurred usage. No automatic retry occurs. A process interruption can leave a running reservation; after confirming the request has ended, use `python3 app.py resolve-interrupted-run --run-id UUID` (minimum five minutes old). This marks it unresolved, not replayed.
- Reset a password: `python3 app.py reset-password --email member@example.com`. Existing sessions are revoked. No self-service email reset/MFA/SSO is included.
- The UI has no source/matter deletion workflow or automated retention. Administrators must implement the team's retention policy before real confidential use. The built-in Data handling and Use and review pages describe behavior; they are not a legal/privacy compliance determination.

## Tests

```sh
python3 -m unittest discover -s tests -v
node --check public/app.js
```

Tests use isolated temporary databases, synthetic sources, original repository example inputs and a mocked network boundary. No API key is needed and no real model request is made.

## API and provenance references

- [OpenAI developer quickstart](https://developers.openai.com/api/docs/quickstart)
- [Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Original patent counsel skills](https://github.com/ShantT123/Patent-Counsel-Agent), bundled commit `3ea14dfd29ee7dc2c6e467d9f71f0b5e62011d5c`

Keep the upstream skill license with this package. Updating skills is a deliberate server deployment; team members never install them individually.
