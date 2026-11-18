import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
export type AuthMode = "signup" | "login" | "recover";

/** What the form holds. `recoveryCode` is used only to recover, where
 *  `password` is the new password. */
export interface AuthValues {
  email: string;
  password: string;
  recoveryCode: string;
}

const COPY = {
  signup: {
    title: "Create an account",
    description:
      "Keep your meals and plans, and use them on any device. Everything you've made so far comes with you.",
    submit: "Create account",
    switchPrompt: "Already have an account?",
    switchTo: "Log in",
  },
  login: {
    title: "Log in",
    description:
      "Log in to your account. Meals made in this guest session stay behind.",
    submit: "Log in",
    switchPrompt: "New here?",
    switchTo: "Create an account",
  },
  recover: {
    title: "Reset your password",
    description:
      "Use the recovery code you saved when you signed up to set a new password. You'll be signed in, and given a new code.",
    submit: "Reset password",
    switchPrompt: "Remembered it?",
    switchTo: "Log in",
  },
} as const;

const SWITCH_TO: Record<AuthMode, AuthMode> = {
  signup: "login",
  login: "signup",
  recover: "login",
};

/**
 * Sign up, log in, or reset a forgotten password with the recovery code, in
 * one dialog: the forms differ by a field at most. The error shown is the
 * server's own sentence (a weak password, a taken email, wrong
 * credentials, a wait).
 */
export function AuthDialog({
  open,
  mode,
  onOpenChange,
  onModeChange,
  onSubmit,
}: {
  open: boolean;
  mode: AuthMode;
  onOpenChange: (open: boolean) => void;
  onModeChange: (mode: AuthMode) => void;
  onSubmit: (mode: AuthMode, values: AuthValues) => Promise<unknown>;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const copy = COPY[mode];

  const reset = () => {
    setPassword("");
    setRecoveryCode("");
    setError(null);
  };

  const switchTo = (next: AuthMode) => {
    setError(null);
    setPassword("");
    onModeChange(next);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onSubmit(mode, { email, password, recoveryCode });
      reset();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <div className="grid gap-1.5 pr-6">
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </div>

        <form onSubmit={submit} className="grid gap-3" noValidate>
          <div className="grid gap-1.5">
            <Label htmlFor="auth-email">Email</Label>
            <Input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          {mode === "recover" && (
            <div className="grid gap-1.5">
              <Label htmlFor="auth-recovery-code">Recovery code</Label>
              <Input
                id="auth-recovery-code"
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                placeholder="XXXX-XXXX-XXXX-XXXX"
                required
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value)}
                className="font-mono uppercase placeholder:normal-case"
              />
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="auth-password">
              {mode === "recover" ? "New password" : "Password"}
            </Label>
            <Input
              id="auth-password"
              type="password"
              // Lets password managers offer a new password at signup and
              // the saved one at login.
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={mode === "login" ? undefined : "auth-password-hint"}
            />
            {mode !== "login" && (
              <p id="auth-password-hint" className="text-xs text-muted-foreground">
                At least 8 characters. A few unrelated words work well.
              </p>
            )}
          </div>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <Button
            type="submit"
            disabled={pending || !email || !password || (mode === "recover" && !recoveryCode)}
          >
            {pending ? "Please wait…" : copy.submit}
          </Button>
        </form>

        <div className="grid gap-1 text-center text-sm text-muted-foreground">
          {mode === "login" && (
            <p>
              <Button variant="link" className="h-auto p-0" onClick={() => switchTo("recover")}>
                Forgot your password?
              </Button>
            </p>
          )}
          <p>
            {copy.switchPrompt}{" "}
            <Button
              variant="link"
              className="h-auto p-0"
              onClick={() => switchTo(SWITCH_TO[mode])}
            >
              {copy.switchTo}
            </Button>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
