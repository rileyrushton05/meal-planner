import { Component, type ErrorInfo, type ReactNode } from "react";

import { CrashScreen } from "@/components/CrashScreen";
import { reportCrash } from "@/lib/monitoring";

/**
 * Catches a crash anywhere below it: shows the crash screen instead of a
 * blank page, and reports it when error tracking is on. Written here rather
 * than taken from the Sentry SDK, so the page does not load the SDK before
 * it can render (src/lib/monitoring.ts).
 */
export class CrashBoundary extends Component<
  { children: ReactNode },
  { crashed: boolean; reference?: string }
> {
  state: { crashed: boolean; reference?: string } = { crashed: false };

  static getDerivedStateFromError() {
    return { crashed: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    this.setState({ reference: reportCrash(error, info.componentStack ?? undefined) });
  }

  render() {
    return this.state.crashed ? <CrashScreen reference={this.state.reference} /> : this.props.children;
  }
}
