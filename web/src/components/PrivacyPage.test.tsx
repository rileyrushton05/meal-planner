import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { PrivacyPage } from "@/components/PrivacyPage";

it("says what is stored, where, and how to delete it", () => {
  render(<PrivacyPage />);

  const stored = screen.getByRole("region", { name: "What's stored" });
  expect(within(stored).getByText("Your email")).toBeInTheDocument();
  expect(stored).toHaveTextContent("never read back");
  expect(stored).toHaveTextContent("unused for 30 days is deleted");

  expect(screen.getByRole("region", { name: "Where it's kept" })).toHaveTextContent("Sydney");
  const leaving = screen.getByRole("region", { name: "Taking it with you, or deleting it" });
  expect(within(leaving).getByRole("link", { name: "Go to your account" })).toHaveAttribute(
    "href",
    expect.stringMatching(/^\/account/),
  );
});
