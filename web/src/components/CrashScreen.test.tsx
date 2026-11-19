import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { CrashBoundary } from "@/components/CrashBoundary";
import { CrashScreen } from "@/components/CrashScreen";

afterEach(() => vi.restoreAllMocks());

function Broken(): never {
  throw new Error("render failed");
}

it("replaces a crashed page with a way back, instead of a blank screen", async () => {
  // React reports the error it caught; that noise is expected here.
  vi.spyOn(console, "error").mockImplementation(() => {});
  const reload = vi.fn();
  vi.stubGlobal("location", { ...window.location, reload });

  render(
    <CrashBoundary>
      <Broken />
    </CrashBoundary>,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  await userEvent.setup().click(screen.getByRole("button", { name: "Reload the page" }));
  expect(reload).toHaveBeenCalled();
  vi.unstubAllGlobals();
});

it("shows the report's reference when one was sent", () => {
  render(<CrashScreen reference="7fd59a6813dc435ab5f1079cbe609687" />);

  expect(screen.getByText("7fd59a68")).toBeInTheDocument();
});

it("shows no reference when nothing was reported", () => {
  render(<CrashScreen reference={null} />);

  expect(screen.queryByText(/Reference/)).not.toBeInTheDocument();
});
