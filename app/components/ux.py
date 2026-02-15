"""
Lightweight UX helpers: breadcrumbs, empty states, drag/drop uploads, onboarding.
"""
from __future__ import annotations

import copy
import html
from collections.abc import Iterable, Sequence

import streamlit as st


def render_breadcrumbs(trail: Sequence[str]):
    """Render a simple breadcrumb trail."""
    if not trail:
        return

    parts = []
    last_idx = len(trail) - 1
    for i, label in enumerate(trail):
        safe = html.escape(str(label))
        if i != last_idx:
            parts.append(f'<span class="crumb">{safe}</span><span class="crumb-sep">/</span>')
        else:
            parts.append(f'<span class="crumb active">{safe}</span>')

    st.markdown(
        f"""
        <div class="breadcrumb-wrap">
            {' '.join(parts)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(message: str, help_text: str | None = None, icon: str = "🛈"):
    """Display a consistent empty-state block."""
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-icon">{icon}</div>
            <div class="empty-state-body">
                <div class="empty-state-title">{message}</div>
                {f"<div class='empty-state-help'>{help_text}</div>" if help_text else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def drag_drop_uploader(label: str, **kwargs):
    """Reusable drag-and-drop wrapper around Streamlit's file_uploader."""
    st.markdown(
        """
        <div class="dropzone-hint">
            Drag & drop files here or click to browse.
        </div>
        """,
        unsafe_allow_html=True,
    )
    return st.file_uploader(label, **kwargs)


def render_onboarding_tour(steps: Iterable[str], state_key: str = "show_onboarding_tour"):
    """Show a compact onboarding tour in the sidebar."""
    if state_key not in st.session_state:
        st.session_state[state_key] = True

    if not st.session_state[state_key]:
        return

    with st.sidebar.expander("Quick tour", expanded=True):
        for idx, step in enumerate(steps, start=1):
            st.markdown(f"{idx}. {step}")

        if st.button("Got it", key="dismiss_onboarding"):
            st.session_state[state_key] = False
            st.rerun()


class UndoRedoBuffer:
    """Tiny undo/redo helper for session-managed objects."""

    def __init__(self, history_key: str, future_key: str, max_items: int = 20):
        self.history_key = history_key
        self.future_key = future_key
        self.max_items = max_items
        st.session_state.setdefault(self.history_key, [])
        st.session_state.setdefault(self.future_key, [])

    def push(self, snapshot):
        history: list = st.session_state[self.history_key]
        history.append(copy.deepcopy(snapshot))
        st.session_state[self.history_key] = history[-self.max_items :]
        st.session_state[self.future_key] = []

    def undo(self, current):
        history: list = st.session_state.get(self.history_key, [])
        if not history:
            return None
        snapshot = history.pop()
        st.session_state[self.history_key] = history
        future: list = st.session_state.get(self.future_key, [])
        future.append(copy.deepcopy(current))
        st.session_state[self.future_key] = future[-self.max_items :]
        return snapshot

    def redo(self, current):
        future: list = st.session_state.get(self.future_key, [])
        if not future:
            return None
        snapshot = future.pop()
        st.session_state[self.future_key] = future
        history: list = st.session_state.get(self.history_key, [])
        history.append(copy.deepcopy(current))
        st.session_state[self.history_key] = history[-self.max_items :]
        return snapshot
