# Operations

Deploying The Fridge Door, changing its schema, and the jobs and commands
that keep it running.

## Deployment

Vercel serves the frontend and the API from one origin, so there is no CORS
configuration and the client uses relative paths.

- **Framework preset:** Other (the build is defined in `vercel.json`)
- **Root directory:** the repository root
- **Environment variables** (Production scope):
  - `MEAL_PLANNER_DB_URL`: Neon's pooled URL for `meal_planner_app`, the
    role row-level security applies to, not the owner.
  - `MEAL_PLANNER_RATE_LIMIT_KEY`: a long random value; throttling hashes
    emails and addresses with it.
  - `SENTRY_DSN` (optional): turns on error tracking. Without it nothing is
    reported.
  - Never `MEAL_PLANNER_IMPORT_UNCHECKED_ORIGIN`. It exempts one origin
    from recipe import's public-address check, for the end-to-end tests'
    local fixture site, and is ignored whenever `VERCEL` is set; it does
    not belong in any Vercel environment regardless.
- **Region:** `syd1`, set in `vercel.json`. Functions default to `iad1`
  (Virginia); running them next to the database is worth more than any
  application-level optimisation here (see
  [Latency](../README.md#latency)).

`api/requirements.txt` sits next to the serverless entry point deliberately:
with a custom `buildCommand`, Vercel's Python builder does not pick up the
root file, and the function fails to import its dependencies.

## Migrations

Schema changes are versioned with Alembic:

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

Migrations run automatically at startup for a long-lived local server, but
**never on Vercel**: every cold start would re-check the schema, and
concurrent functions could race. Production is migrated by the
[`Migrate production`](../.github/workflows/migrate.yml) workflow, which runs
when a push to `main` changes `migrations/` (or the ingredient catalogue) and
waits for approval through a GitHub environment named `production`, with a
required reviewer, holding `MEAL_PLANNER_MIGRATION_DB_URL` (the owner's
direct, non-pooled URL). It refuses to run unless its target is Postgres, so
a missing secret cannot "succeed" against a throwaway SQLite file. After
migrating it loads the ingredient catalogue (`python -m app.jobs
sync-catalog`), which changes nothing when the catalogue is already loaded.

**Migrate first, then deploy.** Merging to `main` starts the Vercel deploy
and the migration at the same moment, and the migration waits for approval.
Code that reads a new column fails on every request until that column
exists, so a migration the new code depends on is applied *before* merging:
from the branch, with the owner's URL, on the `preview` Neon branch first
(which preview deployments also need) and then on production. Migrations
are written additively so the code already running is unaffected. After the
merge, the workflow finds nothing left to do.

In CI, `alembic check` fails the build if a model change ships without a
migration, the whole history is downgraded to an empty database to prove
each step is reversible, and a test checks that every index the models
declare survives the migrations.

## Scheduled jobs

`python -m app.jobs <job>` runs maintenance as the database owner, because
the work spans users and row-level security exists to stop the web app
doing that. Jobs print counts, never what people wrote, because Actions
logs on a public repository are public.

- **`purge-guests`**, nightly at 3:17 a.m. Brisbane time
  ([`jobs.yml`](../.github/workflows/jobs.yml)): guests idle for 30 days go,
  with everything they made, along with expired sessions and stale
  rate-limit records.
- **`sync-catalog`**, after every migration and by hand: loads
  `app/catalog.csv` and relinks every ingredient. Run locally with
  `--show-unmatched`, it also lists the ingredient names nothing matched,
  for adding aliases; only ever on your own terminal.

The workflow uses a GitHub environment named `jobs`, limited to `main` and
with no reviewer (it runs nightly), holding `MEAL_PLANNER_JOBS_DB_URL` (the
owner's direct URL). Run a job by hand from the Actions tab, where a dry run
is the default and only counts what would change.

## Health checks

`/health/live` answers without touching the database. `/health/ready` checks
every application table and required column without reading rows or writing
probe data; on Postgres it also checks the runtime role's table, sequence
and row-security-function permissions. Missing tables, columns or grants
return 503; compatible additive schema changes still pass. The probe does
not need access to Alembic's version table.

[`health-check.yml`](../.github/workflows/health-check.yml) asks
`/health/ready` hourly during Australian waking hours, with no credentials,
so a failed run (and GitHub's email about it) means the site or database is
down. It used to be a keep-warm ping every five minutes, but GitHub ran it
about every eight hours, so it kept nothing warm. Cold starts are handled
in the app instead: see [Cold starts](../README.md#cold-starts). Each cold
start logs one line, `"event": "cold_start"` with `import_ms`, which tells a
slow function start apart from a slow database in Vercel's logs.

## Owner commands

Connected as the database owner, with the URL read without echoing and the
host checked first:

```bash
read -rs 'MEAL_PLANNER_DB_URL?Owner URL: ' && export MEAL_PLANNER_DB_URL
python3 scripts/db_report.py        # the host, revision and row counts; read-only
python3 -m app.cli <command>
unset MEAL_PLANNER_DB_URL
```

(That `read` is zsh's; in bash, `read -rsp 'Owner URL: ' MEAL_PLANNER_DB_URL`.)
Check the host `db_report.py` prints before running anything that writes.

### Replacing a lost password

Someone who has lost both their password and their recovery code can be
given a new password:

```bash
python3 -m app.cli set-password
```

It asks for the account's email and the new password (twice, never printed),
applies the same password checks as signing up, and changes nothing until
you type `yes`. It then ends every session the account has, so any browser
still signed in with the old password is signed out.

### Claiming the data from before accounts

A one-off, kept for anyone deploying from an older database. The accounts
migration gave every existing meal and plan to one account with no email or
password, since a migration must not contain a secret. `python3 -m app.cli
claim-account` gives it a login: it shows how many meals the account holds,
asks for an email and a password (twice, read without echoing and never
printed), applies the same checks as signing up, and changes nothing until
you type `yes`.
