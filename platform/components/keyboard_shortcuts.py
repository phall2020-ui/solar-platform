"""
Keyboard Shortcuts System
Provides hotkey support for common actions and navigation.
"""
from collections.abc import Callable

import streamlit as st


class KeyboardShortcut:
    """Represents a keyboard shortcut."""
    
    def __init__(
        self,
        key: str,
        ctrl: bool = False,
        shift: bool = False,
        alt: bool = False,
        description: str = "",
        action: Callable | None = None,
        category: str = "General"
    ):
        """
        Initialize keyboard shortcut.
        
        Args:
            key: The key (e.g., 'k', 'Enter', 'ArrowUp')
            ctrl: Requires Ctrl key (Cmd on Mac)
            shift: Requires Shift key
            alt: Requires Alt key (Option on Mac)
            description: Human-readable description
            action: Callback function to execute
            category: Category for organization (General, Navigation, etc.)
        """
        self.key = key
        self.ctrl = ctrl
        self.shift = shift
        self.alt = alt
        self.description = description
        self.action = action
        self.category = category
    
    def get_display_string(self) -> str:
        """Get human-readable shortcut string."""
        parts = []
        if self.ctrl:
            parts.append("Ctrl")
        if self.shift:
            parts.append("Shift")
        if self.alt:
            parts.append("Alt")
        parts.append(self.key.upper())
        
        return "+".join(parts)
    
    def matches(self, key: str, ctrl: bool, shift: bool, alt: bool) -> bool:
        """Check if this shortcut matches the given key combination."""
        return (
            self.key.lower() == key.lower() and
            self.ctrl == ctrl and
            self.shift == shift and
            self.alt == alt
        )


class KeyboardShortcutManager:
    """Manages keyboard shortcuts for the application."""
    
    def __init__(self):
        """Initialize the shortcut manager."""
        self.shortcuts: dict[str, KeyboardShortcut] = {}
        self._register_default_shortcuts()
    
    def register(
        self,
        shortcut_id: str,
        key: str,
        ctrl: bool = False,
        shift: bool = False,
        alt: bool = False,
        description: str = "",
        action: Callable | None = None,
        category: str = "General"
    ):
        """
        Register a keyboard shortcut.
        
        Args:
            shortcut_id: Unique identifier for the shortcut
            key: The key
            ctrl: Requires Ctrl/Cmd
            shift: Requires Shift
            alt: Requires Alt/Option
            description: Description of what it does
            action: Callback to execute
            category: Organization category
        """
        shortcut = KeyboardShortcut(
            key=key,
            ctrl=ctrl,
            shift=shift,
            alt=alt,
            description=description,
            action=action,
            category=category
        )
        self.shortcuts[shortcut_id] = shortcut
    
    def get_shortcut(self, shortcut_id: str) -> KeyboardShortcut | None:
        """Get a shortcut by ID."""
        return self.shortcuts.get(shortcut_id)
    
    def get_shortcuts_by_category(self) -> dict[str, list[KeyboardShortcut]]:
        """Get all shortcuts grouped by category."""
        by_category = {}
        for shortcut in self.shortcuts.values():
            if shortcut.category not in by_category:
                by_category[shortcut.category] = []
            by_category[shortcut.category].append(shortcut)
        return by_category
    
    def find_shortcut(self, key: str, ctrl: bool, shift: bool, alt: bool) -> str | None:
        """
        Find shortcut ID matching the key combination.
        
        Returns:
            Shortcut ID if found, None otherwise
        """
        for shortcut_id, shortcut in self.shortcuts.items():
            if shortcut.matches(key, ctrl, shift, alt):
                return shortcut_id
        return None
    
    def execute_shortcut(self, shortcut_id: str):
        """Execute a shortcut's action."""
        shortcut = self.shortcuts.get(shortcut_id)
        if shortcut and shortcut.action:
            try:
                shortcut.action()
            except Exception as e:
                st.error(f"Error executing shortcut: {e}")
    
    def _register_default_shortcuts(self):
        """Register default application shortcuts."""
        
        # Navigation
        self.register(
            "search",
            key="k",
            ctrl=True,
            description="Open global search",
            category="Navigation"
        )
        
        self.register(
            "dashboard",
            key="h",
            ctrl=True,
            description="Go to Dashboard",
            category="Navigation"
        )
        
        self.register(
            "settings",
            key=",",
            ctrl=True,
            description="Open Settings",
            category="Navigation"
        )
        
        # Quick Actions
        self.register(
            "refresh",
            key="r",
            ctrl=True,
            description="Refresh current view",
            category="Quick Actions"
        )
        
        self.register(
            "new_report",
            key="n",
            ctrl=True,
            shift=True,
            description="Generate new report",
            category="Quick Actions"
        )
        
        self.register(
            "export",
            key="e",
            ctrl=True,
            description="Export current data",
            category="Quick Actions"
        )
        
        # Data Operations
        self.register(
            "upload",
            key="u",
            ctrl=True,
            shift=True,
            description="Upload data",
            category="Data Operations"
        )
        
        self.register(
            "clear_cache",
            key="Delete",
            ctrl=True,
            shift=True,
            description="Clear cache",
            category="Data Operations"
        )
        
        # View Controls
        self.register(
            "toggle_sidebar",
            key="b",
            ctrl=True,
            description="Toggle sidebar",
            category="View Controls"
        )
        
        self.register(
            "fullscreen",
            key="f",
            ctrl=True,
            description="Toggle fullscreen",
            category="View Controls"
        )
        
        # Help
        self.register(
            "help",
            key="?",
            shift=True,
            description="Show keyboard shortcuts",
            category="Help"
        )


def init_shortcuts_in_session():
    """Initialize keyboard shortcuts in session state."""
    if "_keyboard_shortcuts" not in st.session_state:
        st.session_state._keyboard_shortcuts = KeyboardShortcutManager()
    return st.session_state._keyboard_shortcuts


def get_shortcuts() -> KeyboardShortcutManager:
    """Get keyboard shortcuts manager from session state."""
    if "_keyboard_shortcuts" in st.session_state:
        return st.session_state._keyboard_shortcuts
    return init_shortcuts_in_session()


def render_keyboard_shortcuts_help():
    """Render keyboard shortcuts help dialog."""
    st.title("⌨️ Keyboard Shortcuts")
    
    manager = get_shortcuts()
    shortcuts_by_category = manager.get_shortcuts_by_category()
    
    for category, shortcuts in sorted(shortcuts_by_category.items()):
        st.subheader(category)
        
        # Create table
        rows = []
        for shortcut in shortcuts:
            rows.append({
                "Shortcut": f"`{shortcut.get_display_string()}`",
                "Description": shortcut.description
            })
        
        if rows:
            # Display as markdown table
            st.markdown("| Shortcut | Description |")
            st.markdown("|----------|-------------|")
            for row in rows:
                st.markdown(f"| {row['Shortcut']} | {row['Description']} |")
        
        st.divider()
    
    # Tips
    st.info("""
    💡 **Tips:**
    - Press `Shift+?` anytime to see this help
    - `Ctrl` on Windows/Linux, `Cmd` on Mac
    - Shortcuts work from most pages
    """)


def inject_keyboard_handler():
    """
    Inject JavaScript keyboard event handler.
    
    This enables keyboard shortcuts to work in Streamlit.
    Call this once in your app.py.
    """
    
    # JavaScript to handle keyboard events
    keyboard_js = """
    <script>
    // Keyboard shortcut handler
    document.addEventListener('keydown', function(e) {
        // Don't intercept if user is typing in an input
        if (e.target.tagName === 'INPUT' || 
            e.target.tagName === 'TEXTAREA' || 
            e.target.isContentEditable) {
            return;
        }
        
        // Build shortcut key
        let shortcut = '';
        if (e.ctrlKey || e.metaKey) shortcut += 'ctrl+';
        if (e.shiftKey) shortcut += 'shift+';
        if (e.altKey) shortcut += 'alt+';
        shortcut += e.key.toLowerCase();
        
        // Map shortcuts to actions
        const shortcuts = {
            'ctrl+k': 'search',
            'ctrl+h': 'dashboard',
            'ctrl+,': 'settings',
            'ctrl+r': 'refresh',
            'ctrl+shift+n': 'new_report',
            'ctrl+e': 'export',
            'ctrl+shift+u': 'upload',
            'ctrl+b': 'toggle_sidebar',
            'ctrl+f': 'fullscreen',
            'shift+?': 'help'
        };
        
        const action = shortcuts[shortcut];
        if (action) {
            e.preventDefault();
            
            // Trigger Streamlit session state update
            window.parent.postMessage({
                type: 'streamlit:setComponentValue',
                key: '_keyboard_shortcut_triggered',
                value: action
            }, '*');
            
            // Visual feedback
            console.log('Keyboard shortcut triggered:', action);
        }
    });
    </script>
    """
    
    st.markdown(keyboard_js, unsafe_allow_html=True)


def handle_keyboard_shortcuts():
    """
    Handle triggered keyboard shortcuts.
    
    Call this in your main app loop to process shortcuts.
    """
    if "_keyboard_shortcut_triggered" in st.session_state:
        action = st.session_state._keyboard_shortcut_triggered
        
        # Execute action
        if action == "search":
            st.session_state["show_search"] = True
        elif action == "dashboard":
            st.session_state["current_page"] = "Dashboard"
            st.rerun()
        elif action == "settings":
            st.session_state["current_page"] = "Settings"
            st.rerun()
        elif action == "refresh":
            st.rerun()
        elif action == "help":
            st.session_state["show_shortcuts_help"] = True
        elif action == "toggle_sidebar":
            # Toggle sidebar state
            pass  # Handled by Streamlit native
        
        # Clear the trigger
        del st.session_state._keyboard_shortcut_triggered


def show_shortcuts_badge():
    """Show a floating badge with keyboard shortcut hint."""
    st.markdown("""
    <style>
    .shortcuts-badge {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background-color: rgba(30, 30, 30, 0.9);
        color: white;
        padding: 10px 15px;
        border-radius: 8px;
        font-size: 13px;
        z-index: 1000;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        cursor: pointer;
        transition: all 0.2s;
    }
    .shortcuts-badge:hover {
        background-color: rgba(50, 50, 50, 0.95);
        transform: translateY(-2px);
    }
    .shortcuts-badge kbd {
        background-color: rgba(255, 255, 255, 0.1);
        padding: 2px 6px;
        border-radius: 3px;
        font-family: monospace;
        font-size: 12px;
    }
    </style>
    <div class="shortcuts-badge" onclick="alert('Press Shift+? for keyboard shortcuts')">
        ⌨️ <kbd>Shift</kbd>+<kbd>?</kbd> for shortcuts
    </div>
    """, unsafe_allow_html=True)


def register_custom_shortcut(
    shortcut_id: str,
    key: str,
    action: Callable,
    description: str = "",
    ctrl: bool = False,
    shift: bool = False,
    alt: bool = False,
    category: str = "Custom"
):
    """
    Register a custom keyboard shortcut.
    
    Args:
        shortcut_id: Unique identifier
        key: Key to bind
        action: Function to call when triggered
        description: What it does
        ctrl: Requires Ctrl/Cmd
        shift: Requires Shift
        alt: Requires Alt/Option
        category: Organization category
    """
    manager = get_shortcuts()
    manager.register(
        shortcut_id=shortcut_id,
        key=key,
        ctrl=ctrl,
        shift=shift,
        alt=alt,
        description=description,
        action=action,
        category=category
    )


# Example usage
if __name__ == "__main__":
    st.title("Keyboard Shortcuts Demo")
    
    # Initialize shortcuts
    init_shortcuts_in_session()
    
    # Inject handler
    inject_keyboard_handler()
    
    # Handle triggered shortcuts
    handle_keyboard_shortcuts()
    
    # Show help
    if st.button("Show Keyboard Shortcuts"):
        render_keyboard_shortcuts_help()
    
    # Show floating badge
    show_shortcuts_badge()
