"""Ticket kanban board UI for Phase 4."""

from __future__ import annotations

from collections import defaultdict

import streamlit as st

from services.alerts import AlertRepository, TicketService, TicketStatus


BOARD_COLUMNS = [
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.BLOCKED,
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
]


def render() -> None:
    st.markdown("## 🧩 Ticket Kanban")
    repo = AlertRepository()
    ticketing = TicketService(repository=repo)

    all_tickets = repo.list_tickets()
    grouped = defaultdict(list)
    for ticket in all_tickets:
        grouped[ticket.status].append(ticket)

    cols = st.columns(len(BOARD_COLUMNS))
    for col, status in zip(cols, BOARD_COLUMNS):
        with col:
            st.markdown(f"### {status.value.replace('_', ' ').title()}")
            tickets = grouped.get(status, [])
            st.caption(f"{len(tickets)} tickets")
            for ticket in tickets:
                with st.container(border=True):
                    st.markdown(f"**{ticket.title}**")
                    st.caption(f"Plant: {ticket.plant_uid}")
                    st.caption(f"Priority: {ticket.priority.value}")
                    if ticket.assignee:
                        st.caption(f"Assignee: {ticket.assignee}")

                    next_status = _next_status_options(ticket.status)
                    if next_status:
                        selected = st.selectbox(
                            "Move to",
                            options=[s.value for s in next_status],
                            key=f"next_{ticket.id}",
                        )
                        if st.button("Apply", key=f"apply_{ticket.id}", use_container_width=True):
                            ticketing.transition(ticket.id, TicketStatus(selected))
                            st.rerun()

    st.markdown("---")
    st.markdown("### Create Ticket")
    c1, c2, c3 = st.columns(3)
    with c1:
        plant_uid = st.text_input("Plant UID")
    with c2:
        title = st.text_input("Title")
    with c3:
        priority = st.selectbox("Priority", options=["low", "medium", "high", "critical"], index=1)

    description = st.text_area("Description", value="")
    if st.button("Create Ticket", type="primary"):
        if not plant_uid or not title:
            st.error("Plant UID and title are required.")
        else:
            from services.alerts.models import TicketPriority

            ticketing.create_ticket(
                plant_uid=plant_uid,
                title=title,
                description=description,
                priority=TicketPriority(priority),
                created_by="ui",
            )
            st.success("Ticket created.")
            st.rerun()


def _next_status_options(status: TicketStatus) -> list[TicketStatus]:
    transitions = {
        TicketStatus.OPEN: [TicketStatus.IN_PROGRESS, TicketStatus.BLOCKED, TicketStatus.RESOLVED, TicketStatus.CLOSED],
        TicketStatus.IN_PROGRESS: [TicketStatus.BLOCKED, TicketStatus.RESOLVED, TicketStatus.CLOSED],
        TicketStatus.BLOCKED: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED],
        TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
        TicketStatus.CLOSED: [TicketStatus.IN_PROGRESS],
    }
    return transitions.get(status, [])
