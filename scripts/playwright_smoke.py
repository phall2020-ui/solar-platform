from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from pathlib import Path
import time

base = 'http://localhost:8503'
pages = ['/', '/?page=dashboard', '/?page=site_monitor', '/?page=live_site_data', '/?page=tariff_management']
out_dir = Path('platform/reports/tmp')
out_dir.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # wait for server to be ready (30s)
    start = time.time()
    while True:
        try:
            resp = page.goto(base, timeout=2000)
            break
        except Exception:
            if time.time() - start > 30:
                print('SERVER_NOT_READY')
                browser.close()
                raise SystemExit(2)
            time.sleep(1)

    print('SERVER_READY')

    for i, u in enumerate(pages, start=1):
        full = base + u
        try:
            t0 = time.perf_counter()
            resp = page.goto(full, timeout=30000)
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except PWTimeout:
                pass
            t1 = time.perf_counter()
            ms = int((t1 - t0) * 1000)
            status = resp.status if resp else None
            shot = out_dir / f'smoke_{i}.png'
            page.screenshot(path=str(shot))
            content = page.content()
            print(f'PAGE {u} status={status} time_ms={ms} screenshot={shot} len={len(content)}')
        except Exception as e:
            print(f'ERR {u} {e}')

    browser.close()
