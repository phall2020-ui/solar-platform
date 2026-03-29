"""
SolarEdge Monitoring Portal Browser Scraper client.

Uses Playwright to log in via the web portal and scrape inverter data headlessly.
"""

import re
import requests
from datetime import datetime
from typing import List, Optional
from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState

# Playwright import with fallback
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class SolarEdgeBrowserClient(BaseInverterClient):
    """Client for SolarEdge Monitoring Portal via headless browser scraping."""
    
    PLATFORM_NAME = "SolarEdge"
    PORTAL_URL = "https://monitoring.solaredge.com"
    
    MONITORING_API = "https://monitoringapi.solaredge.com"

    def __init__(self, config: dict):
        super().__init__(config)
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        self.api_key = config.get('api_key', '')   # Optional — enables meter data via REST API
        self._plants_cache: Optional[List[dict]] = None
    
    def validate_config(self) -> tuple[bool, str]:
        if not HAS_PLAYWRIGHT:
            return False, "Playwright not installed. Run: pip install playwright && python -m playwright install chromium"
        if not self.username:
            return False, "SolarEdge username/email is required"
        if not self.password:
            return False, "SolarEdge password is required"
        return True, ""
    
    def authenticate(self) -> bool:
        """
        Authenticate by scraping the web portal.
        Returns True if we can successfully load site data.
        """
        try:
            sites = self._scrape_sites()
            if sites:
                self._authenticated = True
                self._plants_cache = sites
                return True
            return False
        except Exception as e:
            print(f"SolarEdge browser auth error: {e}")
            return False
    
    def _scrape_sites(self) -> List[dict]:
        """Scrape site data from SolarEdge Monitoring Portal with detailed inverter counts."""
        sites = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            try:
                # Go to landing page first
                page.goto(self.PORTAL_URL, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                page.wait_for_timeout(3000)
                
                # Click "Log in" button on landing page
                login_link_selectors = [
                    'a:has-text("Log in")',
                    'a:has-text("Login")',
                    'button:has-text("Log in")',
                    '.login-link',
                    '[href*="login"]',
                ]
                
                for selector in login_link_selectors:
                    try:
                        elem = page.locator(selector).first
                        if elem.is_visible():
                            elem.click()
                            page.wait_for_load_state('networkidle', timeout=15000)
                            break
                    except Exception:
                        continue
                
                page.wait_for_timeout(2000)
                
                # Now fill the login form (new SolarEdge auth uses name="username")
                email_selectors = [
                    'input[name="username"]',
                    'input[type="email"]',
                    'input[name="j_username"]',
                    'input[placeholder*="Email"]',
                    'input[placeholder*="name@"]',
                    '#username',
                    'input[name="email"]',
                ]
                
                for selector in email_selectors:
                    try:
                        elem = page.locator(selector).first
                        if elem.is_visible():
                            elem.fill(self.username)
                            break
                    except Exception:
                        continue
                
                # Password field
                password_selectors = [
                    'input[name="password"]',
                    'input[type="password"]',
                    'input[name="j_password"]',
                    '#password',
                ]
                
                for selector in password_selectors:
                    try:
                        elem = page.locator(selector).first
                        if elem.is_visible():
                            elem.fill(self.password)
                            break
                    except Exception:
                        continue
                
                # Click login/sign in button
                submit_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Sign in")',
                    'button:has-text("Log in")',
                    'button:has-text("Login")',
                    '.login-button',
                ]
                
                for selector in submit_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible():
                            btn.click()
                            break
                    except Exception:
                        continue
                
                # Wait for dashboard to load
                page.wait_for_load_state('networkidle', timeout=30000)
                page.wait_for_timeout(8000)
                
                # Wait for ag-grid to be present
                try:
                    page.wait_for_selector('.ag-row, [role="row"]', timeout=10000)
                except Exception:
                    pass
                
                # First, extract site list with IDs from the page
                sites = self._extract_sites_with_ids(page)
                
                # Try to enable "Current Power" if we couldn't find it in the first pass
                if sites and all(s.get('power', 0) == 0 for s in sites):
                    try:
                        # Click the gear/settings icon for columns
                        # The selector from inspection was likely generic or dynamic
                        settings_btn = page.locator('.ant4162-sitelist-table-header-settings, i.anticon-setting').first
                        if settings_btn.is_visible():
                            settings_btn.click()
                            page.wait_for_timeout(1000)
                            
                            # Find and check checkboxes for "Power" and "Status"
                            for label_text in ["Current Power", "Communication Status", "Power", "Status"]:
                                try:
                                    checkbox = page.locator(f'span:has-text("{label_text}")').locator('xpath=./preceding-sibling::span//input|./parent::label//input').first
                                    if checkbox.is_visible() and not checkbox.is_checked():
                                        checkbox.check()
                                except Exception:
                                    continue
                                    
                            # Close settings or just wait for update
                            page.keyboard.press('Escape')
                            page.wait_for_timeout(3000)
                            # Re-extract with new columns
                            sites = self._extract_sites_with_ids(page)
                    except Exception:
                        pass

                # If we got sites, navigate into each one to get inverter counts
                if sites:
                    print(f"Found {len(sites)} SolarEdge sites, fetching inverter details...")
                    for i, site in enumerate(sites):
                        site_id = site.get('site_id')
                        if site_id:
                            try:
                                inverter_count = self._get_site_inverter_count(page, site_id)
                                site['inverter_count'] = inverter_count
                                print(f"  [{i+1}/{len(sites)}] {site['name']}: {inverter_count} inverters")
                            except Exception as e:
                                print(f"  [{i+1}/{len(sites)}] {site['name']}: error getting inverters")
                                site['inverter_count'] = 1  # Default fallback
                
            except PlaywrightTimeout as e:
                print(f"Timeout during SolarEdge scraping: {e}")
            except Exception as e:
                print(f"Error during SolarEdge scraping: {e}")
            finally:
                browser.close()
        
        return sites
    
    def _extract_sites_with_ids(self, page) -> List[dict]:
        """Extract sites with their IDs from the site list."""
        sites = []
        seen_names = set()
        
        skip_words = {
            'dashboard', 'sites', 'overview', 'power', 'energy', 'status',
            'alerts', 'settings', 'logout', 'search', 'filter', 'entire fleet',
            'group:', 'location:', 'account:', 'equipment:', 'actions', 'create site',
            'all', 'select', 'export', 'delete', 'edit', 'menu', 'sort', 'column'
        }
        
        # Try to get site links which contain siteId in the URL
        try:
            # Look for links to site dashboards
            site_links = page.locator('a[href*="siteId="], a[href*="site/"]').all()
            
            for link in site_links:
                try:
                    href = link.get_attribute('href') or ''
                    name = link.inner_text().strip()
                    
                    if not name or len(name) < 3:
                        continue
                    if name.lower() in seen_names:
                        continue
                    if any(skip.lower() in name.lower() for skip in skip_words):
                        continue
                    
                    # Extract site ID from URL
                    site_id = None
                    if 'siteId=' in href:
                        match = re.search(r'siteId=(\d+)', href)
                        if match:
                            site_id = match.group(1)
                    elif '/site/' in href:
                        match = re.search(r'/site/(\d+)', href)
                        if match:
                            site_id = match.group(1)
                    
                    if site_id:
                        # Find the parent row to extract other data (power, energy)
                        # SolarEdge uses ag-grid or similar where rows are siblings or parents
                        row_data = {}
                        try:
                            # Try to find the closest row element
                            row = link.locator('xpath=./ancestor::*[contains(@class, "ag-row") or contains(@class, "row")][1]')
                            if row.count() > 0:
                                row_text = row.inner_text()
                                parsed = self._parse_site_row(row_text)
                                if parsed:
                                    row_data = parsed
                        except Exception:
                            pass

                        seen_names.add(name.lower())
                        sites.append({
                            'id': name.lower().replace(' ', '_'),
                            'site_id': site_id,
                            'name': name,
                            'capacity': row_data.get('capacity', 0.0),
                            'power': row_data.get('power', 0.0),
                            'energy_today': row_data.get('energy_today', 0.0),
                            'status': row_data.get('status', 'online'),
                            'inverter_count': 1,
                            'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
                        })
                except Exception:
                    continue
        except Exception:
            pass
        
        # Fallback to original extraction if no sites found
        if not sites:
            sites = self._extract_site_data(page)
        
        return sites

    def _get_site_inverter_count(self, page, site_id: str) -> int:
        """Navigate to a site's Analysis page and count inverters from chart legend."""
        try:
            # Use full URL navigation with minimal wait
            analysis_url = f"{self.PORTAL_URL}/one#/commercial/analysis?siteId={site_id}"
            page.goto(analysis_url, wait_until='commit', timeout=20000)
            
            # Wait for the SPA to fully transition
            page.wait_for_timeout(5000)
            
            # Try to click on "Inverter" accordion using Playwright locator
            try:
                inverter_accordion = page.locator('text="Inverter"').first
                if inverter_accordion.is_visible(timeout=5000):
                    inverter_accordion.click()
                    page.wait_for_timeout(2000)
            except Exception:
                pass
            
            # Click on "Inverter Energy Generation" using Playwright locator
            try:
                energy_gen = page.locator('text="Inverter Energy Generation"').first
                if energy_gen.is_visible(timeout=5000):
                    energy_gen.click()
                    page.wait_for_timeout(5000)  # Wait for chart to load
            except Exception:
                pass
            
            # Count inverters from the chart legend or page content
            count_script = """
            () => {
                // Method 1: Look for "Energy Produced for" labels in chart legend
                const allSpans = Array.from(document.querySelectorAll('span'));
                const legendLabels = allSpans.filter(el => 
                    el.textContent && el.textContent.includes('Energy Produced for ')
                );
                if (legendLabels.length > 0) {
                    // Filter to only count actual inverters (contains "Inverter" in name)
                    const inverterLabels = legendLabels.filter(el => 
                        el.textContent.includes('Inverter ')
                    );
                    if (inverterLabels.length > 0) {
                        return { count: inverterLabels.length, method: 'chart-legend-inverter' };
                    }
                    return { count: legendLabels.length, method: 'chart-legend-all' };
                }
                
                // Method 2: Look for highcharts legend items
                const highchartsItems = document.querySelectorAll('.highcharts-legend-item');
                if (highchartsItems.length > 0) {
                    // Count only those containing "Inverter"
                    const inverterItems = Array.from(highchartsItems).filter(el => 
                        el.textContent && el.textContent.includes('Inverter')
                    );
                    if (inverterItems.length > 0) {
                        return { count: inverterItems.length, method: 'highcharts-legend' };
                    }
                }
                
                // Method 3: Count "Inverter X" patterns in page text
                const allText = document.body.innerText;
                const matches = allText.match(/Inverter\\s+\\d+/gi) || [];
                const unique = [...new Set(matches.map(m => m.toLowerCase()))];
                if (unique.length > 0) {
                    return { count: unique.length, method: 'text-regex' };
                }
                
                return { 
                    count: 0, 
                    method: 'none-found',
                    debug: {
                        hasInverterWord: allText.toLowerCase().includes('inverter'),
                        pageLength: allText.length
                    }
                };
            }
            """
            
            try:
                result = page.evaluate(count_script)
                if isinstance(result, dict):
                    count = result.get('count', 0)
                else:
                    count = result
            except Exception as e:
                self.logger.debug(f"JS error getting inverter count: {e}")
                count = 0

            return max(count, 1)  # At least 1 inverter

        except Exception as e:
            self.logger.debug(f"Navigation error getting inverter count: {e}")
            return 1  # Default to 1 if we can't get the count
    
    def _extract_site_data(self, page) -> List[dict]:
        """Extract site data from the dashboard page."""
        sites = []
        seen_names = set()
        
        # Skip these - they're UI elements, not site names
        skip_words = {
            'dashboard', 'sites', 'overview', 'power', 'energy', 'status',
            'alerts', 'settings', 'logout', 'search', 'filter', 'entire fleet',
            'group:', 'location:', 'account:', 'equipment:', 'actions', 'create site',
            'all', 'select', 'export', 'delete', 'edit', 'menu', 'sort', 'column'
        }
        
        # SolarEdge uses ag-grid for the site table
        # Try specific selectors for the data rows
        row_selectors = [
            '.ag-row',                    # ag-grid rows
            '.ag-row-even',
            '.ag-row-odd', 
            '[role="row"]',               # ARIA row role
            '.site-table-row',
            '.sites-list-row',
            'table tbody tr',
        ]
        
        for row_selector in row_selectors:
            rows = page.locator(row_selector).all()
            for row in rows:
                try:
                    text = row.inner_text()
                    site = self._parse_site_row(text)
                    if site and site['name']:
                        name_lower = site['name'].lower().strip()
                        # Skip if already seen or is a UI element
                        if name_lower in seen_names:
                            continue
                        if any(skip.lower() in name_lower for skip in skip_words):
                            continue
                        if name_lower.startswith('group') or name_lower.startswith('location'):
                            continue
                        # Looks like a valid site
                        seen_names.add(name_lower)
                        sites.append(site)
                except Exception:
                    continue
            if sites:
                break
        
        # If no rows found, try HTML extraction
        if not sites:
            page_content = page.content()
            sites = self._extract_from_html(page_content)
        
        return self._filter_sites(sites)
    
    def _parse_site_row(self, text: str) -> Optional[dict]:
        """Parse site information from a row element."""
        if not text or len(text) < 5:
            return None
        
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        if not lines:
            return None
        
        site = {
            'id': '',
            'name': '',
            'capacity': 0.0,
            'power': 0.0,
            'energy_today': 0.0,
            'status': 'online',
            'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        # First meaningful line is usually the site name
        for line in lines:
            if len(line) < 3:
                continue
            # Skip numeric-only lines (might be capacity or power)
            if re.match(r'^[\d.,\s%]+$', line):
                continue
            # Skip status words
            if line.lower() in ['active', 'inactive', 'error', 'online', 'offline', 'ok']:
                continue
            
            if not site['name']:
                site['name'] = line
                site['id'] = line.lower().replace(' ', '_')
                break
        
        # Parse numeric values more intelligently
        # Pattern 1: find kWp (Capacity)
        cap_match = re.search(r'([\d,.]+)\s*kWp', text, re.IGNORECASE)
        if cap_match:
            site['capacity'] = float(cap_match.group(1).replace(',', ''))

        # Pattern 2: Energy Today vs Energy Yesterday
        # The first instance of kWh is usually Energy Today
        energy_matches = re.findall(r'([\d,.]+)\s*kWh', text, re.IGNORECASE)
        if energy_matches:
            site['energy_today'] = float(energy_matches[0].replace(',', ''))
            
        # Pattern 3: Power (kW)
        # Look for a standalone kW value that isn't capacity or energy
        # Negative lookahead for 'p' (kWp) and 'h' (kWh)
        power_matches = re.findall(r'([\d,.]+)\s*kW(?![ph])', text, re.IGNORECASE)
        if power_matches:
            site['power'] = float(power_matches[0].replace(',', ''))

        # Pattern 4: Alerts
        # Look for alert impacts (often a red icon with a number)
        # In inner_text this might just appear as a standalone number in a specific range
        # or near other indicators.
        if 'error' in text.lower() or 'fault' in text.lower() or 'alert' in text.lower():
            site['status'] = 'warning'
        
        # Heuristic: if there's a standalone high number in a row (alert impact)
        for line in lines:
            if line.isdigit() and 1 <= int(line) <= 100:
                # If we see a standalone number like "6" or "10", it's likely an alert impact
                if int(line) > 0:
                    site['status'] = 'warning'
                    break
                    
        return site if site['name'] else None
    
    def _filter_sites(self, sites: List[dict]) -> List[dict]:
        """Filter and deduplicate site list."""
        seen = set()
        filtered = []
        
        for site in sites:
            name = site.get('name', '').strip().lower()
            name_key = name.replace('_', ' ').replace('-', ' ')
            
            if not name or name_key in seen:
                continue
            if len(name) < 3:
                continue
            
            seen.add(name_key)
            filtered.append(site)
        
        return filtered
    
    def _extract_from_html(self, html: str) -> List[dict]:
        """Extract site data from raw HTML as fallback."""
        sites = []
        
        # Look for site IDs or names in the HTML
        # SolarEdge often includes site data in JavaScript or data attributes
        site_patterns = [
            r'siteName["\s:]+([^"<>\n]+)',
            r'site-name["\s:>]+([^"<>\n]+)',
        ]
        
        for pattern in site_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                name = match.strip()
                if len(name) > 3 and name.lower() not in [s['name'].lower() for s in sites]:
                    sites.append({
                        'id': name.lower().replace(' ', '_'),
                        'name': name,
                        'capacity': 0.0,
                        'power': 0.0,
                        'energy_today': 0.0,
                        'status': 'online',
                        'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
                    })
        
        return sites
    
    def _get_site_meter_data(self, numeric_site_id: str) -> dict:
        """
        Fetch today's meter energy data from the SolarEdge monitoring API.

        Requires api_key to be set in config.  Returns a dict with keys:
          feedin_kwh   — energy exported/fed into the grid today (kWh)
          purchased_kwh — energy purchased/imported from grid today (kWh)

        Returns an empty dict if api_key is absent or the request fails.

        SolarEdge monitoring API endpoint:
          GET /site/{siteId}/energyDetails
              ?meters=PRODUCTION,FEEDIN,PURCHASED
              &timeUnit=DAY
              &startTime={today}%2000:00:00
              &endTime={today}%2023:59:59
              &api_key={api_key}
        """
        if not self.api_key or not numeric_site_id:
            return {}

        today = datetime.now().strftime('%Y-%m-%d')
        url = (
            f"{self.MONITORING_API}/site/{numeric_site_id}/energyDetails"
            f"?meters=PRODUCTION,FEEDIN,PURCHASED"
            f"&timeUnit=DAY"
            f"&startTime={today}%2000:00:00"
            f"&endTime={today}%2023:59:59"
            f"&api_key={self.api_key}"
        )

        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json().get('energyDetails', {})
            meters = data.get('meters', [])

            result = {}
            for meter in meters:
                meter_type = meter.get('type', '').upper()
                values = meter.get('values', [])
                if values:
                    raw = values[0].get('value')
                    if raw is not None:
                        kwh = float(raw) / 1000.0  # API returns Wh; convert to kWh
                        if meter_type == 'FEEDIN':
                            result['feedin_kwh'] = kwh
                        elif meter_type == 'PURCHASED':
                            result['purchased_kwh'] = kwh
            return result
        except Exception:
            return {}

    def get_sites(self) -> List[dict]:
        """Get all sites from cached scrape or re-scrape."""
        if self._plants_cache:
            return self._plants_cache

        sites = self._scrape_sites()
        self._plants_cache = sites
        return sites
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific site."""
        sites = self.get_sites()
        
        for site in sites:
            if site['id'] == site_id or site['name'] == site_id:
                status_str = site.get('status', 'unknown')
                if status_str == 'online':
                    state = InverterState.ONLINE
                elif status_str == 'warning':
                    state = InverterState.WARNING
                elif status_str == 'offline':
                    state = InverterState.OFFLINE
                else:
                    state = InverterState.UNKNOWN
                
                # Create inverter entries based on actual count
                inverter_count = site.get('inverter_count', 1)
                inverters = []
                for i in range(inverter_count):
                    inverters.append(InverterStatus(
                        inverter_id=f"{site['id']}_inv_{i+1}",
                        name=f"Inverter {i+1}",
                        state=state,
                        power_kw=site.get('power', 0.0) / inverter_count if inverter_count > 0 else 0,
                        energy_today_kwh=site.get('energy_today', 0.0) / inverter_count if inverter_count > 0 else 0,
                    ))
                
                # Fetch meter data via monitoring API if api_key is configured
                numeric_site_id = site.get('site_id', '')
                meter_data = self._get_site_meter_data(numeric_site_id)

                return SiteStatus(
                    site_id=site['id'],
                    site_name=site['name'],
                    platform=self.PLATFORM_NAME,
                    inverters=inverters,
                    total_power_kw=site.get('power', 0.0),
                    total_energy_today_kwh=site.get('energy_today', 0.0),
                    installed_capacity_kw=site.get('capacity', 0.0),
                    checked_at=datetime.now(),
                    last_data_time=site.get('dataTimestamp'),
                    meter_export_kwh=meter_data.get('feedin_kwh'),
                    meter_import_kwh=meter_data.get('purchased_kwh'),
                )
        
        return SiteStatus(
            site_id=site_id,
            site_name=site_id,
            platform=self.PLATFORM_NAME,
            error_message="Site not found"
        )
