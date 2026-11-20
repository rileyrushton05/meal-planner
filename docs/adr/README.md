# Decision records

Short records of the decisions that shaped The Fridge Door: what forced
each one, what was chosen, what was turned down, and what it costs. Each
names the code and tests that hold it in place.

| # | Decision |
|---|---|
| [0001](0001-row-level-security.md) | Every query scoped in code, and again by Postgres row-level security |
| [0002](0002-guests-are-real-accounts.md) | A first visit is a real, if anonymous, account |
| [0003](0003-recovery-codes-not-email.md) | Recovery codes instead of password-reset email |
| [0004](0004-rules-not-a-language-model.md) | Ingredient lines read by rules, not a language model |
| [0005](0005-fetching-a-url-someone-else-chose.md) | Recipe import connects to the address it checked |
| [0006](0006-open-on-the-last-visit.md) | Cold starts answered in the browser, not by keeping servers awake |
