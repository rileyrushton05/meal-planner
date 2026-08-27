"""Grocery List tab: totals for the selected week, ready to take shopping."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.planner import GroceryItem, format_grocery_list, generate_weekly_grocery_list
from ui.services import Services


def render(services: Services, week_start: date) -> None:
    """Draw the whole Grocery List tab for the given week."""
    st.subheader(f"Grocery List — Week of {week_start.strftime('%b %d, %Y')}")

    # Cached per week so switching weeks doesn't show a stale list, and so
    # the list survives the reruns that other widgets trigger.
    cache_key = f"grocery_list_{week_start}"
    if st.button("Generate Grocery List", type="primary"):
        st.session_state[cache_key] = generate_weekly_grocery_list(
            services.db, week_start
        )

    items = st.session_state.get(cache_key)
    if items is None:
        return
    if not items:
        st.info("No meals assigned this week yet!")
        return

    for item in items:
        st.markdown(_grocery_row_html(item), unsafe_allow_html=True)

    as_text = format_grocery_list(items)
    st.text_area("Copy your list", value=as_text, height=150)
    st.download_button(
        "Download as .txt",
        data=as_text,
        file_name=f"grocery-list-{week_start}.txt",
        mime="text/plain",
    )


def _grocery_row_html(item: GroceryItem) -> str:
    return f"""
        <div class="grocery-row">
            <span>{item.name}</span>
            <span class="qty">{item.display_qty}</span>
        </div>
    """
