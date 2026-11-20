# Security

How The Fridge Door protects accounts and data, and the test that holds each
part in place. The short version is in the [README](../README.md#engineering-highlights);
what the app keeps about people, in plain terms, is in its
[Privacy](../README.md#privacy) section.

## Accounts

Everyone has an account. A first visit starts a **guest** account (no email,
no password) behind a session cookie, so the planner works immediately;
signing up attaches credentials to that same account, keeping everything the
guest made. Repositories are constructed for one user, so no query can run
unscoped, and someone else's meal answers 404, never 403.

- **Passwords:** argon2id (RFC 9106 parameters, upgraded at login if they
  change), length 8–128, and the 10,000 most common breached passwords are
  refused. No composition rules, per NIST SP 800-63B.
- **Sessions:** a random 256-bit token in an `HttpOnly`, `Secure`,
  `SameSite=Strict`, `__Host-` cookie. The database stores only its SHA-256,
  so a leaked table cannot be replayed. Sessions end after 30 days without a
  visit, and the token is replaced at login and signup (session fixation).
- **Login** answers identically, in identical time, whether the email is
  unknown or the password is wrong.
- **Recovery codes, not email:** a forgotten password is reset with a
  recovery code shown once at signup (16 characters, 80 random bits),
  rather than an emailed link. The app never sends email, so no third
  party ever receives users' addresses, and there is no provider to depend
  on. Only the code's SHA-256 is stored; each code works once (recovery
  issues the next); resetting ends every session; the refusal is the same
  whether the email or the code is wrong, and guesses share login's
  per-network throttle. They skip its account-wide ceiling, which anyone
  who knows the email can reach: the code is how the owner gets back in
  meanwhile, and 80 random bits need no such ceiling. Codes can be
  replaced from the Account page with the password.
  The trade-off: lose both the password and the code, and the account is
  gone, unless whoever runs the deployment gives it a new password
  ([`set-password`](operations.md#replacing-a-lost-password)).

## Requests

- **Cross-site requests:** besides `SameSite=Strict`, any write whose
  `Origin` (or `Sec-Fetch-Site`) says another website sent it is refused
  (`server/origin.py`).
- **Throttling:** five wrong passwords for one account from one network
  start a wait (1 minute, doubling to 15) during which even the right
  password is refused; a higher ceiling per account catches guesses spread
  across many networks. Anyone who knows the email can reach that ceiling,
  so a browser that has signed in to the account before carries a device
  cookie (OWASP's pattern: a random id with a keyed hash binding it to the
  email, nothing stored) and is throttled on its own instead: guesses from
  anywhere else never lock the owner out of their own browser. Failures
  from one network are also capped across every email (50 an hour, never
  reset by a success), which catches one password tried against many
  accounts and bounds the password-hashing work a stranger can cause.
  Guest sessions and "email already taken" answers are capped per network
  per hour. Emails and IP addresses are stored only as keyed hashes, and
  the address comes from the platform's header, never one a client can set.
- **Bounded work:** reading pasted ingredients takes at most 100 lines of
  200 characters, and the parser runs in time linear in the line (a test
  feeds it adversarial 10,000-character lines), so no request can make it
  work hard. It is rules, not a language model: nothing to prompt-inject,
  and no paid API for a caller to run up.
- **Recipe import fetches a page someone else chose**, so it is held to
  rules against server-side request forgery (`app/fetch.py`): http and
  https only, no credentials in the URL; every address the name resolves
  to must be public (not private, loopback, link-local, carrier-grade NAT,
  reserved or multicast, IPv4-mapped IPv6 included); the connection goes
  to the address that was checked, with the name sent as Host and as the
  TLS server name, so a second DNS answer cannot swap in an internal one
  (DNS rebinding) while the certificate is still verified; each of up to
  five redirects is checked again; 5 seconds in all, 2 MB at most, HTML
  only. Each user may import 20 recipes an hour, failures included. The
  page is read for its schema.org JSON-LD by a scan that is linear in its
  length: `html.parser` took minutes on two megabytes of `<`, and a test
  now holds every hostile shape found to under a second.
- **Every route needs a session:** a test walks the OpenAPI document and
  checks that every data route (all of `/api/` but signing in and out)
  answers 401 without one, so a new route cannot ship open. The one
  exception, the relay for the browser's error reports, which can matter
  most before a session exists, is named in the test with that reason.

## Data

- **Row-level security:** in Postgres, the app connects as a role that can
  only see and write rows belonging to the user its request declared.
  Repositories filter by user, and the database filters again, so a query
  that forgot its filter still returns nothing of anyone else's. The
  ingredient catalogue, which belongs to no one, is read-only to that role.
  The row-security tests run connected as the app's own role, against a
  schema built by the migrations.
  ([database-schema.md](database-schema.md#row-level-security-postgres))
- **Leaving:** the Account page downloads everything that is yours as
  readable JSON (meals, ingredients, every planned day; names rather than
  internal ids, and never a password hash or token), and deletes the
  account in one statement that cascades to every row it owns, ending every
  session. An account confirms with its password, throttled together with
  login so a stolen session cannot use it to guess; a guest needs nothing.
  Tests check that deletion leaves no row of the account's in any table
  (found from the models, so a new table is covered) and touches no one
  else's, including as the app's restricted role under row security.

## The browser

- **Security headers:** the web page runs under a Content-Security-Policy
  that allows only its own scripts, styles, fonts and API (nothing inline,
  nothing from another host) and cannot be framed. Vercel's CDN serves the
  page, so its headers live in `vercel.json`; the preview server the
  end-to-end tests use reads them from there, and every Playwright test fails
  on any violation. API responses get a stricter set from the app itself
  (`server/headers.py`): no content allowed at all, `no-store`, `nosniff`.

## Logs and error reports

- **Security events:** signups, logins, failures, throttling and refused
  cross-site requests are logged as JSON with the request id; passwords,
  tokens, emails and IP addresses never are, and a test checks the logs.
- **Error tracking:** unexpected failures in the API and crashes in the
  browser are reported to Sentry, each tagged with the request id that finds
  its log lines. The browser sends its reports through the app's own API
  (`server/routers/monitoring.py`), so the CSP stays `'self'`-only, and the
  relay forwards only reports addressed to this app's Sentry project. Reports
  carry no user, cookies, headers, bodies, query strings or local variables,
  and every email address is replaced, on both sides; tests check each of
  these. The SDK loads after the page has started, so the first paint never
  waits for it, and a crash shows a way back instead of a blank page. All of
  it is off unless `SENTRY_DSN` is set.
