"""
Sungrow iSolarCloud Browser Scraper client.

Uses Playwright to log in via the web portal and scrape inverter data headlessly.
This bypasses the API encryption requirement.
"""

import re
import json
from datetime import datetime
from typing import List, Optional
from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState

# Playwright import with fallback
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class SungrowBrowserClient(BaseInverterClient):
    """Client for Sungrow iSolarCloud via headless browser scraping."""
    
    PLATFORM_NAME = "Sungrow"
    
    # Regional portals
    PORTALS = {
        'eu': 'https://www.isolarcloud.eu',
        'com': 'https://www.isolarcloud.com',
        'hk': 'https://www.isolarcloud.com.hk',
        'au': 'https://auportal.isolarcloud.com',
    }
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        region = config.get('region', 'eu').lower()
        self.portal_url = self.PORTALS.get(region, self.PORTALS['eu'])
        self._plants_cache: Optional[List[dict]] = None
        self._devices_cache: dict = {}  # Cache devices per site: {site_id: [devices]}
    
    def validate_config(self) -> tuple[bool, str]:
        if not HAS_PLAYWRIGHT:
            return False, "Playwright not installed. Run: pip install playwright && python -m playwright install chromium"
        if not self.username:
            return False, "Sungrow username/email is required"
        if not self.password:
            return False, "Sungrow password is required"
        return True, ""
    
    def authenticate(self) -> bool:
        """
        Authenticate by scraping the web portal.
        Returns True if we can successfully load plant data.
        """
        # We don't maintain a persistent session, so just validate we can get data
        try:
            plants = self._scrape_plants()
            if plants:
                self._authenticated = True
                self._plants_cache = plants
                return True
            return False
        except Exception as e:
            print(f"Sungrow browser auth error: {e}")
            return False
    
    def _scrape_plants(self) -> List[dict]:
        """Scrape plant data from iSolarCloud portal."""
        plants = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            try:
                # Go to login page
                page.goto(f"{self.portal_url}/#/login", timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                page.wait_for_timeout(2000)  # Wait for form to fully render
                
                # iSolarCloud has multiple input fields - find the right ones
                # Account field is typically labeled with "Account" or "Email" 
                # and is not readonly like the Server dropdown
                
                # Try multiple strategies for the account field
                account_selectors = [
                    'input[placeholder*="Account"]',
                    'input[placeholder*="account"]',
                    'input[placeholder*="Email"]',
                    'input[placeholder*="email"]',
                    'input[placeholder*="User"]',
                    '.login-form input[type="text"]:not([readonly])',
                    'form input[type="text"]:not([readonly])',
                ]
                
                account_filled = False
                for selector in account_selectors:
                    try:
                        elements = page.locator(selector).all()
                        for elem in elements:
                            if elem.is_editable():
                                elem.fill(self.username)
                                account_filled = True
                                break
                        if account_filled:
                            break
                    except Exception:
                        continue
                
                if not account_filled:
                    # Fallback: click and type
                    page.keyboard.press('Tab')
                    page.keyboard.type(self.username)
                
                # Password field
                password_selectors = [
                    'input[type="password"]',
                    'input[placeholder*="Password"]',
                    'input[placeholder*="password"]',
                ]
                
                for selector in password_selectors:
                    try:
                        elem = page.locator(selector).first
                        if elem.is_visible():
                            elem.fill(self.password)
                            break
                    except Exception:
                        continue
                
                # Click login button
                login_selectors = [
                    'button:has-text("Login")',
                    'button:has-text("Sign in")',
                    'button:has-text("Log in")',
                    '.login-btn',
                    'button[type="submit"]',
                ]
                
                for selector in login_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible():
                            btn.click()
                            break
                    except Exception:
                        continue
                
                # Wait for dashboard to load
                page.wait_for_load_state('networkidle', timeout=30000)
                page.wait_for_timeout(5000)  # Longer wait for data to fully populate
                
                # Try to extract plant data from the page
                plants = self._extract_plant_data(page)
                
            except PlaywrightTimeout as e:
                print(f"Timeout during Sungrow scraping: {e}")
            except Exception as e:
                print(f"Error during Sungrow scraping: {e}")
            finally:
                browser.close()
        
        return plants
    
    def _extract_plant_data(self, page) -> List[dict]:
        """Extract plant data from the dashboard page."""
        plants = []
        seen_names = set()
        
        # Skip these - they're UI elements, not plant names
        skip_words = {
            'search', 'create', 'plant name', 'normal', 'fault', 'offline',
            'c&i pv', 'remark', 'alarm', 'warning', 'online', 'installed',
            'capacity', 'power', 'energy', 'status', 'address', 'uk', 'united kingdom'
        }
        
        # Try to find plant cards - iSolarCloud uses table rows for plants
        # Each plant row contains: name, address, status, type, capacity, power
        rows = page.locator('table tbody tr, .el-table__row, [class*="table"] tr').all()
        
        for row in rows:
            try:
                text = row.inner_text()
                plant = self._parse_plant_row(text)
                if plant and plant['name'].lower() not in seen_names:
                    # Filter out non-plant entries
                    name_lower = plant['name'].lower()
                    if not any(skip in name_lower for skip in skip_words):
                        seen_names.add(name_lower)
                        plants.append(plant)
            except Exception:
                continue
        
        # Only use HTML extraction as fallback if we found few/no table plants
        if len(plants) < 4:  # Expected to have 4 Sungrow plants
            page_content = page.content()
            html_plants = self._extract_from_html(page_content)
            
            # Merge HTML plants - only add if not already found
            for hp in html_plants:
                hp_name_key = hp['name'].lower().replace(' ', '_').replace('-', '_')
                # Check if this plant already exists
                already_exists = False
                for existing in plants:
                    existing_key = existing['name'].lower().replace(' ', '_').replace('-', '_')
                    if hp_name_key == existing_key or hp['name'].lower() == existing['name'].lower():
                        already_exists = True
                        break
                
                if not already_exists:
                    seen_names.add(hp['name'].lower())
                    plants.append(hp)
        
        # Deduplicate and filter
        return self._filter_plants(plants)
    
    def _parse_plant_row(self, text: str) -> Optional[dict]:
        """Parse plant information from a table row."""
        if not text or len(text) < 10:
            return None
        
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return None
        
        plant = {
            'id': '',
            'name': '',
            'capacity': 0.0,
            'power': 0.0,
            'status': 'unknown',
            'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        # First line is usually the plant name
        for line in lines:
            # Skip very short lines or known non-name entries
            if len(line) < 3:
                continue
            if line.lower() in ['normal', 'fault', 'offline', 'online', 'c&i pv', '--']:
                continue
            if line.lower().startswith('remark'):
                continue
            if re.match(r'^[\d.,]+\s*(kw|mw)', line.lower()):
                continue
            if ', uk' in line.lower() or 'united kingdom' in line.lower():
                continue
                
            # This looks like a plant name
            if not plant['name']:
                plant['name'] = line
                plant['id'] = line.lower().replace(' ', '_')
                continue
        
        # Look for capacity and power values
        # The row format is typically: Name | Address | Status | Type | Capacity | Real-time Power
        # We need to be careful to identify the right values
        
        power_found = False
        for line in lines:
            line_stripped = line.strip()
            
            # Capacity: in kWp or MWp (always has 'p' suffix)
            cap_match = re.search(r'^(\d+\.?\d*)\s*(kWp|MWp)$', line_stripped, re.IGNORECASE)
            if cap_match and plant['capacity'] == 0:
                value = float(cap_match.group(1))
                if 'mw' in cap_match.group(2).lower():
                    value *= 1000
                plant['capacity'] = value
                continue
            
            # Real-time power: in kW or MW (no 'p' suffix)
            # Only match if it's a standalone value on a line (the last column)
            power_match = re.search(r'^(\d+\.?\d*)\s*(kW|MW)$', line_stripped, re.IGNORECASE)
            if power_match and not power_found:
                value = float(power_match.group(1))
                if 'mw' in power_match.group(2).lower():
                    value *= 1000
                plant['power'] = value
                power_found = True
        
        # Determine status
        text_lower = text.lower()
        if 'normal' in text_lower:
            plant['status'] = 'online'
        elif 'fault' in text_lower or 'alarm' in text_lower:
            plant['status'] = 'warning'
        elif 'offline' in text_lower or 'disconnect' in text_lower:
            plant['status'] = 'offline'
        
        return plant if plant['name'] else None
    
    def _filter_plants(self, plants: List[dict]) -> List[dict]:
        """Filter and deduplicate plant list."""
        seen = set()
        filtered = []

        for plant in plants:
            # Normalize name - replace non-breaking spaces with regular spaces
            name = plant.get('name', '').replace('\xa0', ' ').strip()
            plant['name'] = name  # Update the plant dict with normalized name

            # Normalize for comparison
            name_lower = name.lower()
            name_key = name_lower.replace('_', ' ').replace('-', ' ')

            # Skip empty or duplicate names
            if not name or name_key in seen:
                continue
            # Skip UI element names
            if name_key in ['search', 'create plant', 'plant name', 'c&i pv']:
                continue
            # Skip if name is too short
            if len(name) < 4:
                continue

            seen.add(name_key)
            # Update the ID to use normalized name
            plant['id'] = name.lower().replace(' ', '_')
            filtered.append(plant)

        return filtered
    
    def _extract_from_html(self, html: str) -> List[dict]:
        """Extract plant data from raw HTML if structured extraction fails."""
        plants = []
        
        # Known plant name patterns for this account
        patterns = [
            r'Iceland\s+Shrewsbury',
            r'Iceland\s+Teesbay', 
            r'Iceland\s+Waterloovile',
            r'FYLDE\s+SOLAR\s+2025',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                name = matches[0]
                # Check status from nearby HTML
                status = 'online'
                if f'{name}' in html:
                    # Look for status indicator near the name
                    idx = html.find(name)
                    nearby = html[max(0, idx-200):idx+500]
                    if 'fault' in nearby.lower() or 'alarm' in nearby.lower():
                        status = 'warning'
                    elif 'offline' in nearby.lower():
                        status = 'offline'
                
                plants.append({
                    'id': name.lower().replace(' ', '_'),
                    'name': name,
                    'capacity': 0.0,
                    'power': 0.0,
                    'status': status,
                    'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
                })
        
        return plants
    
    def _scrape_devices_for_site(self, site_name: str) -> List[dict]:
        """Scrape individual devices from the global Device list, filtered by site."""
        devices = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            try:
                # Go to login page
                page.goto(f"{self.portal_url}/#/login", timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                page.wait_for_timeout(2000)
                
                # Accept cookies if present
                try:
                    cookie_btn = page.locator('text="Yes, I agree"').first
                    if cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass
                
                # Use JavaScript to set credentials more reliably
                page.evaluate('''([username, password]) => {
                    const inputs = document.querySelectorAll('input');
                    const accountInput = Array.from(inputs).find(i => 
                        i.placeholder && (i.placeholder.includes('Account') || i.placeholder.includes('Email')));
                    const passwordInput = Array.from(inputs).find(i => i.type === 'password');
                    if (accountInput) {
                        accountInput.value = username;
                        accountInput.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    if (passwordInput) {
                        passwordInput.value = password;
                        passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }''', [self.username, self.password])
                
                # Try filling via selectors as backup
                try:
                    account_input = page.locator('input[placeholder*="Account"], input[placeholder*="Email"]').first
                    if account_input.is_visible():
                        account_input.fill(self.username)
                except Exception:
                    pass
                    
                try:
                    password_input = page.locator('input[type="password"]').first
                    if password_input.is_visible():
                        password_input.fill(self.password)
                except Exception:
                    pass
                
                # Click login button
                try:
                    login_btn = page.locator('button:has-text("Login"), button:has-text("Sign in")').first
                    if login_btn.is_visible():
                        login_btn.click()
                except Exception:
                    page.keyboard.press('Enter')
                
                # Wait for login and dashboard load
                page.wait_for_load_state('networkidle', timeout=30000)
                page.wait_for_timeout(5000)
                
                # Navigate to global Device list (Inverter tab)
                # Navigate directly to global device list
                page.goto(f"{self.portal_url}/#/device/list", timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                page.wait_for_timeout(5000)

                # Click on "Inverter" tab if present
                try:
                    inverter_tab = page.locator('text=/Inverter/i').first
                    if inverter_tab.is_visible():
                        inverter_tab.click()
                        page.wait_for_timeout(3000)
                        page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass
                
                # Try to expand page size to 100
                try:
                    # Look for pagination dropdown - common patterns in Element UI
                    page_size_selectors = [
                        'text=/\\d+\\/page/i',
                        '.el-pagination__sizes',
                        '[class*="page-size"]',
                        'select[class*="pagination"]'
                    ]

                    for selector in page_size_selectors:
                        try:
                            page_size = page.locator(selector).first
                            if page_size.is_visible():
                                page_size.click()
                                page.wait_for_timeout(500)
                                # Try to select 100/page or max available
                                for size_text in ['100/page', '100', '200/page', '200']:
                                    try:
                                        size_option = page.locator(f'text="{size_text}"').first
                                        if size_option.is_visible():
                                            size_option.click()
                                            page.wait_for_timeout(3000)
                                            page.wait_for_load_state('networkidle', timeout=15000)
                                            break
                                    except Exception:
                                        continue
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print(f"Could not change page size: {e}")
                
                # Extract all devices from the page
                # Pass site_name for context, but return all devices found
                devices = self._extract_devices_from_page(page, site_name)
                
            except PlaywrightTimeout as e:
                print(f"Timeout during device scraping for {site_name}: {e}")
            except Exception as e:
                print(f"Error during device scraping for {site_name}: {e}")
            finally:
                browser.close()
        
        return devices
    
    def _extract_devices_from_page(self, page, site_filter: str = None) -> List[dict]:
        """Extract device information from the device list page."""
        devices_from_cards = []
        devices_from_html = []

        try:
            # Get page content
            content = page.content()

            # Try multiple selectors for rows
            row_selectors = [
                'table tbody tr',
                '.el-table__row',
                '.el-card',
                '[class*="device-card"]',
                '[class*="device-item"]',
                '[class*="list-item"]'
            ]

            all_rows = []
            for selector in row_selectors:
                try:
                    rows = page.locator(selector).all()
                    all_rows.extend(rows)
                except Exception:
                    continue

            # Extract from each row
            for row in all_rows:
                try:
                    text = row.inner_text()

                    # Skip if not an inverter - look for "Inverter" keyword
                    if 'Inverter' not in text and 'inverter' not in text.lower():
                        continue

                    device = self._parse_device_info(text)
                    if device:
                        devices_from_cards.append(device)

                except Exception as e:
                    continue

            # Also extract from HTML to get serial numbers
            devices_from_html = self._extract_devices_from_html(content, site_filter)

            # Merge the two sources
            # Cards have names, HTML fallback often has better serial numbers
            # If we have both sources, prefer card data but enrich with HTML data
            if devices_from_cards and devices_from_html:
                # Create lookup by name for HTML devices
                html_by_name = {}
                for dev in devices_from_html:
                    name = dev.get('name', '').lower()
                    if name:
                        html_by_name[name] = dev

                # Enrich card devices with serial numbers from HTML
                for dev in devices_from_cards:
                    name = dev.get('name', '').lower()
                    if name in html_by_name and not dev.get('serial_number'):
                        html_dev = html_by_name[name]
                        if html_dev.get('serial_number'):
                            dev['serial_number'] = html_dev['serial_number']
                            dev['id'] = html_dev['serial_number']

                return devices_from_cards
            elif devices_from_cards:
                return devices_from_cards
            else:
                return devices_from_html

        except Exception as e:
            print(f"Error extracting devices: {e}")

        return devices_from_cards or devices_from_html
    
    def _parse_device_info(self, text: str) -> Optional[dict]:
        """Parse device information from text."""
        if not text or 'Inverter' not in text:
            return None

        device = {
            'id': '',
            'name': '',
            'serial_number': '',
            'plant': '',
            'status': 'unknown',
            'power_w': 0.0,
            'energy_today_kwh': 0.0,
            'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        }

        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Find inverter name - look for lines with "Inverter" but not status words
        for line in lines:
            if 'Inverter' in line and len(line) < 100:
                # Skip lines that are just status words
                line_lower = line.lower()
                if line_lower in ['inverter', 'inverters']:
                    continue
                # Clean up the name
                name = line.strip()
                if name and not any(skip in line_lower for skip in ['device type', 'type:', 'model:']):
                    device['name'] = name
                    break

        # Find serial number (S/N)
        sn_match = re.search(r'S/N[:\s]*([A-Z0-9]+)', text, re.IGNORECASE)
        if sn_match:
            device['serial_number'] = sn_match.group(1)
            device['id'] = sn_match.group(1)
        elif device['name']:
            device['id'] = device['name'].lower().replace(' ', '_')

        # Find plant name (look for known patterns and also generic "Plant:" pattern)
        plant_patterns = [
            r'Plant[:\s]*([^\n\t]+?)(?:\n|\t|$)',
            r'(FYLDE\s+SOLAR\s+\d+)',
            r'(Iceland\s+\w+)',
        ]
        for pattern in plant_patterns:
            plant_match = re.search(pattern, text, re.IGNORECASE)
            if plant_match:
                plant_name = plant_match.group(1).strip()
                # Clean up plant name
                if plant_name and not plant_name.lower() in ['normal', 'fault', 'offline', 'online']:
                    device['plant'] = plant_name
                    break

        # Find status
        text_lower = text.lower()
        if 'fault' in text_lower:
            device['status'] = 'fault'
        elif 'normal' in text_lower:
            device['status'] = 'normal'
        elif 'offline' in text_lower or 'disconnect' in text_lower:
            device['status'] = 'offline'
        elif 'warning' in text_lower or 'alarm' in text_lower:
            device['status'] = 'warning'

        # Find power (W or kW)
        power_match = re.search(r'(\d+(?:\.\d+)?)\s*W(?:\s|$|[^a-zA-Z])', text)
        if power_match:
            device['power_w'] = float(power_match.group(1))
        else:
            power_kw_match = re.search(r'(\d+(?:\.\d+)?)\s*kW(?:\s|$)', text)
            if power_kw_match:
                device['power_w'] = float(power_kw_match.group(1)) * 1000

        # Find yield/energy today
        yield_match = re.search(r'(\d+(?:\.\d+)?)\s*kWh', text)
        if yield_match:
            device['energy_today_kwh'] = float(yield_match.group(1))

        return device if device['name'] or device['serial_number'] else None
    
    def _extract_devices_from_html(self, html: str, site_filter: str = None) -> List[dict]:
        """Extract devices from raw HTML content."""
        devices = []
        seen_sns = set()
        
        # Pattern to find inverter entries with serial numbers
        # Format variations seen: "Inverter A07", "Inverter1", etc.
        # S/N format: A23C2500502, A25428B1405, etc.
        
        sn_pattern = r'S/N[:\s]*([A-Z]\d{2}[A-Z0-9]{5,})'
        matches = re.findall(sn_pattern, html, re.IGNORECASE)
        
        for sn in matches:
            if sn in seen_sns:
                continue
            seen_sns.add(sn)
            
            # Try to find associated info near this S/N
            idx = html.find(sn)
            if idx == -1:
                continue
            
            nearby = html[max(0, idx-500):idx+300]
            
            # Extract inverter name
            name_match = re.search(r'(Inverter\s*[A-Z0-9]+)', nearby, re.IGNORECASE)
            name = name_match.group(1) if name_match else f"Inverter {sn[-4:]}"
            
            # Extract status
            status = 'unknown'
            if 'fault' in nearby.lower():
                status = 'fault'
            elif 'normal' in nearby.lower():
                status = 'normal'
            elif 'offline' in nearby.lower():
                status = 'offline'
            
            # Extract power
            power = 0.0
            power_match = re.search(r'(\d+)\s*W(?:\s|<|$)', nearby)
            if power_match:
                power = float(power_match.group(1))
            
            # Extract energy today
            energy = 0.0
            energy_match = re.search(r'(\d+(?:\.\d+)?)\s*kWh', nearby)
            if energy_match:
                energy = float(energy_match.group(1))
            
            devices.append({
                'id': sn,
                'name': name,
                'serial_number': sn,
                'status': status,
                'power_w': power,
                'energy_today_kwh': energy,
                'dataTimestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
            })
        
        return devices
    
    def get_devices_for_site(self, site_name: str) -> List[dict]:
        """Get all devices/inverters for a specific site, using cache if available."""
        site_key = site_name.lower().replace(' ', '_')

        if site_key in self._devices_cache:
            return self._devices_cache[site_key]

        all_devices = self._scrape_devices_for_site(site_name)

        # Deduplicate devices - use serial number or name as key
        seen = set()
        unique_devices = []
        site_name_lower = site_name.lower()

        for device in all_devices:
            # Create unique key
            sn = device.get('serial_number', '')
            name = device.get('name', '')
            plant = device.get('plant', '').lower()

            # Skip if no identifying info
            if not sn and not name:
                continue

            # Filter by plant name if available - be lenient with matching
            # Since we're on a GLOBAL device list, devices MUST have plant info to be included
            # Otherwise we can't tell which site they belong to
            if not plant:
                # Skip devices with no plant info - can't determine which site they belong to
                continue

            # Normalize both for comparison
            plant_normalized = plant.replace('_', ' ').replace('-', ' ').strip()
            site_normalized = site_name_lower.replace('_', ' ').replace('-', ' ').strip()

            if site_normalized not in plant_normalized and plant_normalized not in site_normalized:
                # Device belongs to different plant
                continue

            # Use SN as primary key, fall back to name
            key = sn if sn else name.lower()

            if key in seen:
                continue
            seen.add(key)

            # Use name as ID if no serial number
            if not device.get('id'):
                device['id'] = sn if sn else name.lower().replace(' ', '_')

            unique_devices.append(device)

        self._devices_cache[site_key] = unique_devices
        return unique_devices
    
    def get_sites(self) -> List[dict]:
        """Get all power plants from cached scrape or re-scrape."""
        if self._plants_cache:
            return self._plants_cache
        
        plants = self._scrape_plants()
        self._plants_cache = plants
        return plants
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific plant with all its individual inverters."""
        sites = self.get_sites()
        
        for site in sites:
            if site['id'] == site_id or site['name'] == site_id:
                site_name = site['name']
                
                # Get individual devices for this site
                devices = self.get_devices_for_site(site_name)
                
                inverters = []
                total_power_kw = 0.0
                total_energy_today_kwh = 0.0
                
                if devices:
                    # Create InverterStatus for each physical device
                    for device in devices:
                        # Map status
                        status_str = device.get('status', 'unknown').lower()
                        if status_str == 'normal':
                            state = InverterState.ONLINE
                        elif status_str in ['fault', 'warning', 'alarm']:
                            state = InverterState.WARNING
                        elif status_str in ['offline', 'disconnect']:
                            state = InverterState.OFFLINE
                        else:
                            state = InverterState.UNKNOWN
                        
                        power_kw = device.get('power_w', 0.0) / 1000.0
                        energy_kwh = device.get('energy_today_kwh', 0.0)
                        
                        inverters.append(InverterStatus(
                            inverter_id=device.get('serial_number') or device.get('id', ''),
                            name=device.get('name', 'Unknown Inverter'),
                            state=state,
                            power_kw=power_kw,
                            energy_today_kwh=energy_kwh,
                        ))
                        
                        total_power_kw += power_kw
                        total_energy_today_kwh += energy_kwh
                else:
                    # Fallback: create a single inverter representing the plant
                    status_str = site.get('status', 'unknown')
                    if status_str == 'online':
                        state = InverterState.ONLINE
                    elif status_str == 'warning':
                        state = InverterState.WARNING
                    elif status_str == 'offline':
                        state = InverterState.OFFLINE
                    else:
                        state = InverterState.UNKNOWN
                    
                    inverters = [InverterStatus(
                        inverter_id=site['id'],
                        name=site['name'],
                        state=state,
                        power_kw=site.get('power', 0.0),
                        energy_today_kwh=0.0,
                    )]
                    total_power_kw = site.get('power', 0.0)
                
                return SiteStatus(
                    site_id=site['id'],
                    site_name=site['name'],
                    platform=self.PLATFORM_NAME,
                    inverters=inverters,
                    total_power_kw=total_power_kw,
                    total_energy_today_kwh=total_energy_today_kwh,
                    installed_capacity_kw=site.get('capacity', 0.0),
                    checked_at=datetime.now(),
                    last_data_time=site.get('dataTimestamp'),
                )
        
        return SiteStatus(
            site_id=site_id,
            site_name=site_id,
            platform=self.PLATFORM_NAME,
            error_message="Plant not found"
        )
