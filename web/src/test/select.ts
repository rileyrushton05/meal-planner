import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

/**
 * Choose an option from a Base UI Select.
 *
 * Not a native <select>, so userEvent.selectOptions does not apply: the
 * trigger opens a listbox rendered in a portal, and the option is clicked.
 */
export async function chooseOption(
  user: UserEvent,
  triggerName: string,
  optionName: string | RegExp,
) {
  await user.click(screen.getByRole("combobox", { name: triggerName }));
  const listbox = await screen.findByRole("listbox");
  await user.click(within(listbox).getByRole("option", { name: optionName }));
}
