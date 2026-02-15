"""
Authentication UI Components.
Provides login page, user management interface, and authentication widgets.
"""

import streamlit as st

from solar_platform.services.auth import get_current_user, init_session_auth, logout


def render_login_page():
    """Render the login page."""
    init_session_auth()

    st.markdown("## 🔐 Solar Portfolio Manager")
    st.markdown("### Sign In")

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submit = st.form_submit_button("Sign In", use_container_width=True)

        if submit:
            if not username or not password:
                st.error("Please enter both username and password")
            else:
                user = st.session_state.auth_service.authenticate(username, password)
                if user:
                    st.session_state.user = user
                    st.success(f"Welcome back, {user.full_name}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")

    st.markdown("---")
    st.info("Default credentials: **admin** / **admin123**")


def render_user_menu():
    """Render user menu in the sidebar."""
    user = get_current_user()

    if user is None:
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown(f"### 👤 {user.full_name}")
        st.markdown(f"*{user.role.title()}*")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Profile", use_container_width=True):
                st.session_state.show_profile = True
        with col2:
            if st.button("Logout", use_container_width=True):
                logout()
                st.rerun()

        if user.has_permission("manage_users"):
            if st.button("👥 Manage Users", use_container_width=True):
                st.session_state.current_page = "User Management"
                st.rerun()


def render_user_profile():
    """Render user profile page."""
    user = get_current_user()
    if user is None:
        return

    st.markdown("## 👤 User Profile")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Personal Information")
        st.text_input("Username", value=user.username, disabled=True)
        st.text_input("Full Name", value=user.full_name, disabled=True)
        st.text_input("Email", value=user.email, disabled=True)
        st.text_input("Role", value=user.role.title(), disabled=True)

    with col2:
        st.markdown("### Change Password")
        with st.form("change_password_form"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submit = st.form_submit_button("Update Password")

            if submit:
                if not all([current_password, new_password, confirm_password]):
                    st.error("All fields are required")
                elif new_password != confirm_password:
                    st.error("New passwords do not match")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                else:
                    # Verify current password
                    auth_user = st.session_state.auth_service.authenticate(
                        user.username, current_password
                    )
                    if auth_user:
                        st.session_state.auth_service.change_password(
                            user.user_id, new_password
                        )
                        st.success("Password updated successfully!")
                    else:
                        st.error("Current password is incorrect")

    st.markdown("---")
    st.markdown("### Permissions")
    permissions = []
    if user.has_permission("read"):
        permissions.append("✓ View data and reports")
    if user.has_permission("write"):
        permissions.append("✓ Create and edit content")
    if user.has_permission("delete"):
        permissions.append("✓ Delete content")
    if user.has_permission("export"):
        permissions.append("✓ Export data")
    if user.has_permission("manage_users"):
        permissions.append("✓ Manage users")
    if user.has_permission("manage_settings"):
        permissions.append("✓ Manage system settings")

    for perm in permissions:
        st.markdown(perm)


def render_user_management():
    """Render user management page (admin only)."""
    user = get_current_user()
    if user is None or not user.has_permission("manage_users"):
        st.error("You do not have permission to manage users")
        return

    st.markdown("## 👥 User Management")

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["Users", "Add User", "Audit Log"])

    with tab1:
        st.markdown("### All Users")
        users = st.session_state.auth_service.list_users()

        for u in users:
            with st.expander(f"{u.full_name} (@{u.username})", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Email:** {u.email}")
                    st.markdown(f"**Role:** {u.role.title()}")
                with col2:
                    status = "Active" if u.is_active else "Inactive"
                    st.markdown(f"**Status:** {status}")
                with col3:
                    if u.user_id != user.user_id:
                        new_role = st.selectbox(
                            "Change Role",
                            options=["admin", "manager", "analyst", "viewer"],
                            index=["admin", "manager", "analyst", "viewer"].index(u.role),
                            key=f"role_{u.user_id}"
                        )
                        if st.button("Update Role", key=f"update_{u.user_id}"):
                            st.session_state.auth_service.update_user(u.user_id, role=new_role)
                            st.success("Role updated!")
                            st.rerun()

                        if u.is_active:
                            if st.button("Deactivate", key=f"deactivate_{u.user_id}"):
                                st.session_state.auth_service.delete_user(u.user_id)
                                st.success("User deactivated!")
                                st.rerun()

    with tab2:
        st.markdown("### Add New User")
        with st.form("add_user_form"):
            new_username = st.text_input("Username")
            new_email = st.text_input("Email")
            new_full_name = st.text_input("Full Name")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", options=["viewer", "analyst", "manager", "admin"])

            submit = st.form_submit_button("Create User")
            if submit:
                if not all([new_username, new_email, new_full_name, new_password]):
                    st.error("All fields are required")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                else:
                    success = st.session_state.auth_service.create_user(
                        new_username, new_email, new_full_name, new_password, new_role
                    )
                    if success:
                        st.success(f"User {new_username} created successfully!")
                    else:
                        st.error("Username or email already exists")

    with tab3:
        st.markdown("### Audit Log")
        logs = st.session_state.auth_service.get_audit_log(limit=50)

        if logs:
            import pandas as pd
            df = pd.DataFrame(logs)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No audit log entries found")


def show_permission_warning(permission: str):
    """Show a warning when user lacks permission."""
    st.warning(f"You need '{permission}' permission to access this feature")


def check_permission_decorator(permission: str):
    """Decorator to check permissions before rendering a page."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user and user.has_permission(permission):
                return func(*args, **kwargs)
            else:
                show_permission_warning(permission)
                return None
        return wrapper
    return decorator
