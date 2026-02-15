"""
Global Search Component
Provides fuzzy search across plants, reports, and analyses with keyboard shortcut support.
"""
from typing import Any

import streamlit as st
from fuzzywuzzy import fuzz

from solar_platform.db.utils import get_connection
from solar_platform.services.user_preferences import get_preferences

# Phase 2: Page registry integration for searching pages
try:
    from app.page_registry import PAGE_GROUPS, find_page
    _HAS_PAGE_REGISTRY = True
except ImportError:
    _HAS_PAGE_REGISTRY = False


class SearchResult:
    """Represents a search result."""
    
    def __init__(
        self, 
        title: str, 
        category: str, 
        identifier: str,
        score: int,
        metadata: dict[str, Any] | None = None,
        action_url: str | None = None
    ):
        self.title = title
        self.category = category  # Plant, Report, Analysis, Page, etc.
        self.identifier = identifier
        self.score = score
        self.metadata = metadata or {}
        self.action_url = action_url
    
    def __repr__(self):
        return f"SearchResult(title={self.title}, category={self.category}, score={self.score})"


class GlobalSearch:
    """Handles global search functionality."""
    
    def __init__(self, toolkit_db: str, reporting_db: str):
        """
        Initialize global search.
        
        Args:
            toolkit_db: Path to Solar Toolkit database
            reporting_db: Path to reporting database
        """
        self.toolkit_db = toolkit_db
        self.reporting_db = reporting_db
    
    def search(self, query: str, max_results: int = 20, min_score: int = 50) -> list[SearchResult]:
        """
        Perform global search across all indexed content.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            min_score: Minimum fuzzy match score (0-100)
            
        Returns:
            List of SearchResult objects sorted by relevance
        """
        if not query or len(query.strip()) < 2:
            return []
        
        query = query.strip().lower()
        results = []
        
        # Search plants
        results.extend(self._search_plants(query))
        
        # Search reports
        results.extend(self._search_reports(query))
        
        # Search pages/features
        results.extend(self._search_pages(query))
        
        # Search pages from registry (Phase 2)
        results.extend(self._search_registry_pages(query))
        
        # Search analyses (future)
        # results.extend(self._search_analyses(query))
        
        # Filter by score and sort
        results = [r for r in results if r.score >= min_score]
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:max_results]
    
    def _search_plants(self, query: str) -> list[SearchResult]:
        """Search plants from both databases."""
        results = []
        
        # Search Solar Toolkit plants
        try:
            with get_connection(self.toolkit_db) as conn:
                result = conn.execute("SELECT alias, plant_uid FROM plants").fetchall()
                
                for row in result:
                    alias, plant_uid = row
                    
                    # Fuzzy match on alias and plant_uid
                    alias_score = fuzz.partial_ratio(query, str(alias).lower())
                    uid_score = fuzz.partial_ratio(query, str(plant_uid or "").lower())
                    
                    score = max(alias_score, uid_score)
                    
                    if score > 0:
                        results.append(SearchResult(
                            title=alias,
                            category="Plant (Toolkit)",
                            identifier=plant_uid,
                            score=score,
                            metadata={"source": "toolkit"}
                        ))
        except Exception:
            # Table might not exist yet
            pass
        
        # Search Monthly Reporting plants
        try:
            with get_connection(self.reporting_db) as conn:
                result = conn.execute("SELECT DISTINCT plant_key FROM plant_metadata").fetchall()
                
                for row in result:
                    plant_key = row[0]
                    
                    score = fuzz.partial_ratio(query, str(plant_key).lower())
                    
                    if score > 0:
                        results.append(SearchResult(
                            title=plant_key,
                            category="Plant (Reporting)",
                            identifier=plant_key,
                            score=score,
                            metadata={"source": "reporting"}
                        ))
        except Exception:
            # Table might not exist yet
            pass
        
        return results
    
    def _search_reports(self, query: str) -> list[SearchResult]:
        """Search generated reports."""
        results = []
        
        try:
            with get_connection(self.reporting_db) as conn:
                # Check if reports table exists
                table_check = conn.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '_generated_reports'"
                ).fetchone()
                
                if table_check[0] > 0:
                    report_results = conn.execute("""
                        SELECT report_id, report_name, plant_key, generated_at
                        FROM _generated_reports
                        ORDER BY generated_at DESC
                        LIMIT 100
                    """).fetchall()
                    
                    for row in report_results:
                        report_id, report_name, plant_key, generated_at = row
                        
                        # Fuzzy match on report name and plant
                        name_score = fuzz.partial_ratio(query, str(report_name or "").lower())
                        plant_score = fuzz.partial_ratio(query, str(plant_key or "").lower())
                        
                        score = max(name_score, plant_score)
                        
                        if score > 0:
                            results.append(SearchResult(
                                title=report_name or f"Report {report_id}",
                                category="Report",
                                identifier=report_id,
                                score=score,
                                metadata={
                                    "plant": plant_key,
                                    "generated_at": generated_at
                                }
                            ))
        except Exception:
            # Table might not exist yet
            pass
        
        return results
    
    def _search_registry_pages(self, query: str) -> list[SearchResult]:
        """Search page names and descriptions from the page registry."""
        if not _HAS_PAGE_REGISTRY:
            return []
        
        results = []
        query_lower = query.lower()
        
        for group_name, group in PAGE_GROUPS.items():
            for page_name, page_config in group.pages.items():
                # Score based on fuzzy match of page name and description
                name_score = fuzz.partial_ratio(query_lower, page_name.lower())
                desc_score = fuzz.partial_ratio(query_lower, page_config.description.lower()) if page_config.description else 0
                best_score = max(name_score, desc_score)
                
                if best_score >= 60:  # Threshold for relevance
                    results.append(SearchResult(
                        title=f"{page_config.icon} {page_name}",
                        category="Page",
                        identifier=page_name,
                        score=best_score,
                        metadata={
                            "group": group_name,
                            "description": page_config.description,
                            "requires_plant": page_config.requires_plant,
                        },
                    ))
        
        return results

    def _search_pages(self, query: str) -> list[SearchResult]:
        """Search app pages and features."""
        # Define searchable pages with keywords
        pages = [
            {
                "title": "Dashboard",
                "category": "Page",
                "keywords": ["dashboard", "home", "overview", "main", "landing"],
                "identifier": "dashboard"
            },
            {
                "title": "Data Explorer",
                "category": "Page",
                "keywords": ["data", "explorer", "upload", "import", "etl", "health", "quality"],
                "identifier": "data_explorer"
            },
            {
                "title": "Monthly Reporting",
                "category": "Page",
                "keywords": ["monthly", "report", "reporting", "generation", "pdf"],
                "identifier": "monthly_reporting"
            },
            {
                "title": "Database Viewer",
                "category": "Page",
                "keywords": ["database", "viewer", "query", "sql", "tables", "schema"],
                "identifier": "database_viewer"
            },
            {
                "title": "Clipping Analysis",
                "category": "Feature",
                "keywords": ["clipping", "inverter", "loss", "analysis"],
                "identifier": "clipping"
            },
            {
                "title": "Fouling Analysis",
                "category": "Feature",
                "keywords": ["fouling", "soiling", "degradation", "cleaning"],
                "identifier": "fouling"
            },
            {
                "title": "Shading Analysis",
                "category": "Feature",
                "keywords": ["shading", "shadow", "loss", "analysis"],
                "identifier": "shading"
            },
            {
                "title": "Plant Management",
                "category": "Feature",
                "keywords": ["plant", "management", "register", "sites", "portfolio"],
                "identifier": "plant_mgmt"
            },
            {
                "title": "Settings & Preferences",
                "category": "Page",
                "keywords": ["settings", "preferences", "config", "configuration", "options"],
                "identifier": "settings"
            },
            {
                "title": "Background Jobs",
                "category": "Feature",
                "keywords": ["jobs", "background", "queue", "tasks", "async"],
                "identifier": "jobs"
            },
            {
                "title": "Cache Management",
                "category": "Feature",
                "keywords": ["cache", "performance", "optimization", "speed"],
                "identifier": "cache"
            }
        ]
        
        results = []
        
        for page in pages:
            # Check title match
            title_score = fuzz.partial_ratio(query, page["title"].lower())
            
            # Check keyword matches
            keyword_scores = [fuzz.partial_ratio(query, kw) for kw in page["keywords"]]
            max_keyword_score = max(keyword_scores) if keyword_scores else 0
            
            # Take the best score
            score = max(title_score, max_keyword_score)
            
            if score > 0:
                results.append(SearchResult(
                    title=page["title"],
                    category=page["category"],
                    identifier=page["identifier"],
                    score=score,
                    metadata={"keywords": page["keywords"]}
                ))
        
        return results
    
    def get_suggestions(self, partial_query: str, max_suggestions: int = 5) -> list[str]:
        """
        Get search suggestions based on partial query.
        
        Args:
            partial_query: Partial search query
            max_suggestions: Maximum suggestions to return
            
        Returns:
            List of suggested queries
        """
        if not partial_query or len(partial_query) < 2:
            # Return recent searches
            try:
                prefs = get_preferences()
                return prefs.get_recent_searches()[:max_suggestions]
            except Exception:
                return []
        
        # Get top results and extract their titles
        results = self.search(partial_query, max_results=max_suggestions)
        return [r.title for r in results]


def init_search_in_session(toolkit_db: str, reporting_db: str):
    """Initialize global search in session state."""
    if "_global_search" not in st.session_state:
        st.session_state._global_search = GlobalSearch(toolkit_db, reporting_db)
    return st.session_state._global_search


def get_search() -> GlobalSearch:
    """Get global search from session state."""
    if "_global_search" in st.session_state:
        return st.session_state._global_search
    
    # Initialize with default paths
    try:
        from app.config_compat import config
        return init_search_in_session(str(config.TOOLKIT_DB), str(config.REPORTING_DB))
    except Exception:
        raise RuntimeError("Global search not initialized.")


def render_search_dialog():
    """
    Render search dialog (modal-style).
    
    Call this in your app to show the search interface.
    Use with keyboard shortcut (Ctrl+K or Cmd+K).
    """
    search = get_search()
    prefs = get_preferences()
    
    # Search input
    query = st.text_input(
        "🔍 Search plants, reports, pages...",
        placeholder="Type to search (Ctrl+K)",
        key="global_search_input",
        label_visibility="collapsed"
    )
    
    if query:
        # Save to recent searches
        prefs.add_recent_search(query)
        
        # Perform search
        results = search.search(query)
        
        if results:
            st.markdown(f"**{len(results)} results**")
            
            # Group by category
            categories = {}
            for result in results:
                if result.category not in categories:
                    categories[result.category] = []
                categories[result.category].append(result)
            
            # Display results by category
            for category, cat_results in categories.items():
                st.markdown(f"**{category}**")
                
                for result in cat_results:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.write(f"• {result.title}")
                    
                    with col2:
                        st.caption(f"Score: {result.score}")
                    
                    with col3:
                        if st.button("Open", key=f"open_{result.identifier}_{result.category}"):
                            # Navigate to result (future implementation)
                            st.info(f"Navigate to: {result.title}")
                
                st.divider()
        else:
            st.info("No results found.")
    else:
        # Show recent searches
        recent = prefs.get_recent_searches()
        if recent:
            st.markdown("**Recent Searches**")
            for search_query in recent[:5]:
                if st.button(f"🕒 {search_query}", key=f"recent_{search_query}"):
                    st.session_state["global_search_input"] = search_query
                    st.rerun()


def render_search_bar_compact():
    """
    Render a compact search bar (for header/sidebar).
    
    Returns:
        Search query if submitted, None otherwise
    """
    col1, col2 = st.columns([5, 1])
    
    with col1:
        query = st.text_input(
            "Search",
            placeholder="Search... (Ctrl+K)",
            key="compact_search",
            label_visibility="collapsed"
        )
    
    with col2:
        search_clicked = st.button("🔍", key="compact_search_btn")
    
    if query or search_clicked:
        return query
    
    return None


def show_search_shortcut_hint():
    """Display a hint about the search keyboard shortcut."""
    st.markdown("""
    <style>
    .search-hint {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background-color: rgba(0, 0, 0, 0.7);
        color: white;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 12px;
        z-index: 1000;
    }
    </style>
    <div class="search-hint">
        Press <kbd>Ctrl</kbd>+<kbd>K</kbd> to search
    </div>
    """, unsafe_allow_html=True)
