import { ArrowRight, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import { AppLink } from "@/components/AppLink";
import { buttonVariants } from "@/components/ui/button";

/**
 * What the app keeps about you, where, and how to take it away. Every
 * statement here is something the code does; when that changes, this page
 * and the README's privacy section change with it.
 */
export function PrivacyPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <section aria-labelledby="in-short" className="flex gap-4 rounded-xl border bg-card p-5">
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-primary-subtle text-primary-subtle-foreground">
          <ShieldCheck aria-hidden className="size-5" />
        </span>
        <div className="space-y-1">
          <h2 id="in-short" className="text-base font-semibold">
            In short
          </h2>
          <p className="text-sm text-muted-foreground">
            The Fridge Door keeps what it needs to plan your meals and nothing else. No ads, no
            analytics, no tracking, and it never emails you.
          </p>
        </div>
      </section>

      <Section id="stored" title="What's stored">
        <Facts
          items={[
            ["Your email", "Only as your login name. Nothing is ever sent to it."],
            [
              "Your password and recovery code",
              "Only as one-way hashes, so they can be checked but never read back, even by the app.",
            ],
            ["Your meals and plans", "The meals, ingredients and planned days you add, tied to your account."],
            [
              "Your session",
              "A cookie that keeps you signed in. The app stores only a hash of it, and it ends after 30 days.",
            ],
            [
              "Guest sessions",
              "No email or password at all. A guest session unused for 30 days is deleted with everything in it.",
            ],
            [
              "In your browser only",
              "Your light or dark choice, and the grocery items you've ticked off. Never sent anywhere.",
            ],
          ]}
        />
      </Section>

      <Section id="logs" title="Logs and error reports">
        <p>
          The app's logs never record email addresses, passwords, session tokens or IP addresses.
          To slow down password guessing, repeated failed logins are counted against a scrambled
          form of your email and network, never the values themselves, and the count is deleted
          after a day.
        </p>
        <p>
          When something breaks, an error report goes to Sentry with what went wrong, never who it
          happened to: no email, cookies, IP address or anything you typed.
        </p>
      </Section>

      <Section id="where" title="Where it's kept">
        <Facts
          items={[
            ["The app and your data", "Vercel and Neon, both in Sydney."],
            ["Error reports", "Sentry, in the EU."],
          ]}
        />
        <p>
          Vercel also keeps short-lived request logs of its own as part of running the site, and
          Neon keeps a short restore history of the database in case it needs recovering.
        </p>
      </Section>

      <Section id="leaving" title="Taking it with you, or deleting it">
        <p>
          On the Account page you can download everything you've made as a file, and delete your
          account. Deleting removes your account and everything in it straight away, and signs out
          every device. Guests can delete their session the same way.
        </p>
        <AppLink to="/account" className={buttonVariants({ variant: "outline" })}>
          Go to your account
          <ArrowRight aria-hidden />
        </AppLink>
      </Section>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3 rounded-xl border bg-card p-5">
      <h2 id={id} className="text-base font-semibold">
        {title}
      </h2>
      <div className="space-y-3 text-sm text-muted-foreground">{children}</div>
    </section>
  );
}

/** Label and explanation pairs, side by side where there is room. */
function Facts({ items }: { items: readonly (readonly [string, string])[] }) {
  return (
    <dl className="divide-y">
      {items.map(([label, detail]) => (
        <div key={label} className="grid gap-1 py-2.5 first:pt-0 last:pb-0 sm:grid-cols-[12rem_1fr] sm:gap-4">
          <dt className="font-medium text-foreground">{label}</dt>
          <dd>{detail}</dd>
        </div>
      ))}
    </dl>
  );
}
