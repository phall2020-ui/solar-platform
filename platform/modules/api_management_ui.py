"""
API Management UI Module.
Provides interface for managing API keys and viewing API documentation.
"""
import json

import streamlit as st

from services.api_service import APIDocumentation, APIService
from services.auth_service import get_current_user
from unified_config import config


def render():
    """Render the API management page."""
    user = get_current_user()

    st.markdown("## 🔌 API Management")
    st.markdown("Manage API keys and access programmatic endpoints")

    # Check if user has permission
    if user is None:
        st.warning("Please log in to access API management")
        return

    if not user.has_permission("manage_settings"):
        st.warning("You need admin permissions to manage API keys")
        # Show read-only documentation
        render_api_documentation()
        return

    # Initialize API service
    if "api_service" not in st.session_state:
        st.session_state.api_service = APIService(
            toolkit_db=config.TOOLKIT_DB,
            reporting_db=config.REPORTING_DB
        )

    api_service = st.session_state.api_service

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "API Keys", "Create Key", "Documentation", "Usage Statistics"
    ])

    with tab1:
        render_api_keys(api_service, user)

    with tab2:
        render_create_key(api_service, user)

    with tab3:
        render_api_documentation()

    with tab4:
        render_usage_statistics(api_service)


def render_api_keys(api_service: APIService, user):
    """Render existing API keys."""
    st.markdown("### Your API Keys")

    keys = api_service.list_api_keys(user.user_id)

    if not keys:
        st.info("You don't have any API keys yet. Create one in the 'Create Key' tab.")
        return

    for key in keys:
        with st.expander(f"🔑 {key.name}", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Created:** {key.created_at}")
                st.markdown(f"**Last Used:** {key.last_used or 'Never'}")
                st.markdown(f"**Status:** {'Active' if key.is_active else 'Revoked'}")

            with col2:
                st.markdown("**Permissions:**")
                for perm in key.permissions:
                    st.markdown(f"- {perm}")

            if key.is_active:
                if st.button("Revoke Key", key=f"revoke_{key.key_id}"):
                    api_service.revoke_api_key(key.key_id)
                    st.success(f"API key '{key.name}' has been revoked")
                    st.rerun()


def render_create_key(api_service: APIService, user):
    """Render create API key form."""
    st.markdown("### Create New API Key")

    st.info("Create an API key to access the Solar Portfolio Manager programmatically. Keep your API keys secure and never share them publicly.")

    with st.form("create_api_key_form"):
        key_name = st.text_input(
            "API Key Name",
            placeholder="e.g., Production Integration, Development Testing"
        )

        st.markdown("**Select Permissions:**")

        permissions = []
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.checkbox("Read", value=True):
                permissions.append("read")
            if st.checkbox("Write"):
                permissions.append("write")

        with col2:
            if st.checkbox("Export"):
                permissions.append("export")
            if st.checkbox("Delete"):
                permissions.append("delete")

        with col3:
            if st.checkbox("Manage Users"):
                permissions.append("manage_users")
            if st.checkbox("Manage Settings"):
                permissions.append("manage_settings")

        submit = st.form_submit_button("Generate API Key")

        if submit:
            if not key_name:
                st.error("Please provide a name for the API key")
            elif not permissions:
                st.error("Please select at least one permission")
            else:
                # Create the API key
                api_key = api_service.create_api_key(
                    user.user_id,
                    key_name,
                    permissions
                )

                st.success("API Key created successfully!")
                st.markdown("### ⚠️ Important: Save Your API Key")
                st.warning("This is the only time you'll see this key. Copy it now and store it securely.")

                st.code(api_key, language=None)

                st.markdown("**Usage Example:**")
                st.code(f"""
import requests

headers = {{
    "X-API-Key": "{api_key}"
}}

response = requests.get("http://localhost:8501/api/plants", headers=headers)
print(response.json())
                """, language="python")


def render_api_documentation():
    """Render API documentation."""
    st.markdown("### 📚 API Documentation")

    st.markdown("""
    The Solar Portfolio Manager API provides programmatic access to your solar plant data,
    performance metrics, and analytics.

    **Base URL:** `http://localhost:8501/api` (or your deployed URL)

    **Authentication:** Include your API key in the `X-API-Key` header for all requests.
    """)

    # Endpoints
    st.markdown("### Available Endpoints")

    for endpoint, details in APIDocumentation.ENDPOINTS.items():
        with st.expander(f"`{endpoint}`", expanded=False):
            st.markdown(f"**Description:** {details.get('description', 'N/A')}")

            perms = details.get('permissions', [])
            if perms:
                st.markdown(f"**Required Permissions:** {', '.join(perms)}")

            params = details.get('parameters', {})
            if params:
                st.markdown("**Parameters:**")
                for param, desc in params.items():
                    st.markdown(f"- `{param}`: {desc}")

            example = details.get('example')
            if example:
                st.markdown("**Example Request:**")
                st.code(example.get('request', ''), language=None)

                st.markdown("**Example Response:**")
                st.code(json.dumps(example.get('response', {}), indent=2), language="json")

    # OpenAPI spec download
    st.markdown("---")
    st.markdown("### Download OpenAPI Specification")

    if st.button("Download OpenAPI 3.0 Spec"):
        spec = APIDocumentation.get_openapi_spec()
        spec_json = json.dumps(spec, indent=2)

        st.download_button(
            label="Download openapi.json",
            data=spec_json,
            file_name="solar_portfolio_api_openapi.json",
            mime="application/json"
        )


def render_usage_statistics(api_service: APIService):
    """Render API usage statistics."""
    st.markdown("### 📊 API Usage Statistics")

    st.info("Usage statistics will be available after API calls are made.")

    # Placeholder for usage stats
    st.markdown("#### Recent API Calls")
    st.markdown("No API usage data available yet.")

    # Example visualization
    st.markdown("#### Usage by Endpoint")
    st.markdown("Coming soon: Charts showing API usage patterns")

    st.markdown("#### Rate Limiting")
    st.info("""
    **Current Rate Limits:**
    - 100 requests per minute per API key
    - 10,000 requests per day per API key

    Contact your administrator to adjust rate limits.
    """)


def render_api_testing_console():
    """Render interactive API testing console."""
    st.markdown("### 🧪 API Testing Console")

    st.markdown("Test API endpoints directly from this interface.")

    _endpoint = st.selectbox(
        "Select Endpoint",
        options=list(APIDocumentation.ENDPOINTS.keys())
    )

    _method = st.selectbox("Method", options=["GET", "POST", "PUT", "DELETE"])

    _api_key = st.text_input("API Key", type="password")

    _params = st.text_area("Parameters (JSON)", value="{}")

    if st.button("Send Request"):
        st.markdown("#### Response:")
        st.code("Response will appear here", language="json")
