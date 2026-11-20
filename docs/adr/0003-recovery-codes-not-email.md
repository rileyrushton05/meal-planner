# 0003: Recovery codes instead of password-reset email

## Context

A forgotten password usually means an emailed link. That needs an email
provider, a sending domain (which costs money and DNS setup), and hands
every user's address to a third party. Without a domain, free providers
will only send to the account owner.

## Decision

At signup the app shows a **recovery code** once: 16 characters, 80 random
bits. Only its SHA-256 is stored (a code that random needs no slow hash).
Recovering with email and code sets a new password, issues the next code,
and ends every session. A wrong email and a wrong code get the same answer,
and guesses share login's throttle. The code can be replaced from the
Account page, with the password.

## Alternatives rejected

- **Email via a provider.** A paid domain, a dependency, and users'
  addresses leaving the app.
- **Security questions.** Guessable and widely discouraged.

## Consequences

- The app never sends email, so the email address is only a login name.
- Lose both the password and the code, and only whoever runs the
  deployment can help (`python -m app.cli set-password`, documented in
  `docs/operations.md`).
- The code never enters the frontend's cache or its saved copy of the last
  visit; a test checks that.
