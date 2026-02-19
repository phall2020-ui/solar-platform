"""Playwright test: click Shading Analysis in sidebar and capture the result."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Collect console errors
        errors = []
        page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

        print("Navigating to app...")
        await page.goto("http://localhost:8502", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Click the Shading Analysis button in the sidebar
        print("Looking for Shading Analysis button...")
        shading_btn = page.locator("button", has_text="Shading Analysis")
        count = await shading_btn.count()
        print(f"Found {count} Shading Analysis button(s)")

        if count > 0:
            await shading_btn.first.click()
            print("Clicked Shading Analysis")
            await page.wait_for_timeout(8000)  # Wait for page to load and analysis to run

            # Get the page content
            content = await page.content()

            # Check for error messages
            error_elements = await page.locator(".stAlert").all()
            for el in error_elements:
                text = await el.inner_text()
                print(f"ALERT: {text}")

            # Check for st.error specifically
            error_msgs = await page.locator('[data-testid="stErrorMessage"]').all()
            if not error_msgs:
                error_msgs = await page.locator(".stException").all()
            for el in error_msgs:
                text = await el.inner_text()
                print(f"ERROR: {text}")

            # Check for warning messages
            warn_msgs = await page.locator('[data-testid="stNotification"]').all()
            for el in warn_msgs:
                text = await el.inner_text()
                print(f"WARNING: {text}")

            # Look for shading-specific content
            heading = await page.locator("text=Shading Analysis").count()
            print(f"Shading Analysis heading found: {heading > 0}")

            metric_elements = await page.locator('[data-testid="stMetric"]').all()
            print(f"Metric cards found: {len(metric_elements)}")
            for m in metric_elements:
                text = await m.inner_text()
                print(f"  METRIC: {text.strip()}")

            # Check for charts
            charts = await page.locator(".js-plotly-plot").all()
            print(f"Charts found: {len(charts)}")

            # Check for any visible text content
            main_content = page.locator('[data-testid="stAppViewContainer"]')
            if await main_content.count() > 0:
                visible_text = await main_content.inner_text()
                # Print first 500 chars
                print(f"\nPAGE CONTENT (first 500 chars):\n{visible_text[:500]}")

            # Take a screenshot
            await page.screenshot(path="/tmp/shading_page.png")
            print("\nScreenshot saved to /tmp/shading_page.png")

        if errors:
            print(f"\nCONSOLE ERRORS ({len(errors)}):")
            for e in errors:
                print(f"  {e}")

        await browser.close()


asyncio.run(main())
