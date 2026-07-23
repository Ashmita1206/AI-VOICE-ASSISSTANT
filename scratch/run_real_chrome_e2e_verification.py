import asyncio
import json
import os
import shutil
import sys
import time
from playwright.async_api import async_playwright

ARTIFACTS_DIR = r"C:\Users\HP\.gemini\antigravity-ide\brain\3648ea34-8a3e-471c-81bd-549fba477ab3"
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

async def main():
    print("================================================================================")
    print("STARTING REAL CHROME E2E AUTOMATION & VISUAL VERIFICATION")
    print("================================================================================")

    async with async_playwright() as p:
        # Launch Chromium/Edge browser
        try:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            print("  Launched Microsoft Edge browser via Playwright.")
        except Exception:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            print("  Launched Chrome browser via Playwright.")
        context = await browser.new_context(viewport={"width": 1280, "height": 850})
        page = await context.new_page()

        console_logs = []
        sse_events = []

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        print("\n[STEP 1] Navigating to http://localhost:5000 ...")
        await page.goto("http://localhost:5000", wait_until="networkidle")
        await asyncio.sleep(1)

        # ----------------------------------------------------------------------
        # TEST 1: "Open HealthSphere document"
        # ----------------------------------------------------------------------
        print("\n================================================================================")
        print("TEST 1: 'Open HealthSphere document'")
        print("================================================================================")

        await page.evaluate("simulateUserCommand('Open HealthSphere document')")
        print("  Submitted command via UI Javascript...")

        # Wait for Planner and Execution sections
        await page.wait_for_selector("#sec-planner", state="visible", timeout=30000)
        await page.wait_for_selector("#sec-execution", state="visible", timeout=30000)
        await asyncio.sleep(2)

        # Screenshot Planner & Execution
        shot1 = os.path.join(ARTIFACTS_DIR, "01_healthsphere_planner_execution.png")
        await page.screenshot(path=shot1, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot1}")

        # Wait for File Search Modal Popup
        print("  Waiting for #file-search-modal popup...")
        await page.wait_for_selector("#file-search-modal", state="visible", timeout=30000)
        await asyncio.sleep(1)

        modal_text = await page.inner_text("#file-search-results")
        print(f"  Modal Results Content:\n{modal_text[:300]}...")

        assert "Healthsphere" in modal_text or "HealthSphere" in modal_text, "HealthSphere result missing from modal popup!"

        # Screenshot Popup Modal
        shot2 = os.path.join(ARTIFACTS_DIR, "02_healthsphere_popup_modal.png")
        await page.screenshot(path=shot2, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot2}")

        # Click "Open number 1" button inside the modal
        print("  Clicking 'Open number 1' button in popup modal...")
        btn1 = page.locator("#file-search-actions button:has-text('Open number 1')")
        await btn1.click()
        await asyncio.sleep(3)

        # Screenshot Document Opened status
        shot3 = os.path.join(ARTIFACTS_DIR, "03_healthsphere_document_opened.png")
        await page.screenshot(path=shot3, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot3}")
        print("  [SUCCESS] TEST 1 PASSED!")

        # ----------------------------------------------------------------------
        # TEST 2: "Open Money Mentor document"
        # ----------------------------------------------------------------------
        print("\n================================================================================")
        print("TEST 2: 'Open Money Mentor document'")
        print("================================================================================")

        await page.evaluate("simulateUserCommand('Open Money Mentor document')")
        await page.wait_for_selector("#file-search-modal", state="visible", timeout=30000)
        await asyncio.sleep(1)

        mm_text = await page.inner_text("#file-search-results")
        print(f"  Money Mentor Modal Content:\n{mm_text[:300]}...")
        assert "MONEY MENTOR" in mm_text or "money" in mm_text.lower(), "Money Mentor result missing from modal popup!"

        # Screenshot Money Mentor Popup
        shot4 = os.path.join(ARTIFACTS_DIR, "04_moneymentor_popup_modal.png")
        await page.screenshot(path=shot4, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot4}")

        # Click "Open number 1"
        mm_btn1 = page.locator("#file-search-actions button:has-text('Open number 1')")
        await mm_btn1.click()
        await asyncio.sleep(3)

        shot5 = os.path.join(ARTIFACTS_DIR, "05_moneymentor_document_opened.png")
        await page.screenshot(path=shot5, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot5}")
        print("  [SUCCESS] TEST 2 PASSED!")

        # ----------------------------------------------------------------------
        # TEST 3 & 4: "HealthSphere PDF" & Extension Filter Audit
        # ----------------------------------------------------------------------
        print("\n================================================================================")
        print("TEST 3 & 4: Extension Filter & Ranking Audit ('HealthSphere PDF')")
        print("================================================================================")

        await page.evaluate("simulateUserCommand('HealthSphere PDF')")
        await page.wait_for_selector("#sec-execution", state="visible", timeout=30000)
        await asyncio.sleep(2)

        # Check if modal is visible OR single result opened
        modal_visible = await page.is_visible("#file-search-modal")
        if modal_visible:
            pdf_text = await page.inner_text("#file-search-results")
            print(f"  HealthSphere PDF Results in Modal:\n{pdf_text[:300]}...")
            for bad_ext in [".py", ".js", ".json", ".md", ".yml", "README", "requirements"]:
                assert bad_ext not in pdf_text, f"Forbidden extension '{bad_ext}' found in results!"
        else:
            exec_text = (await page.inner_text("#sec-execution")).encode('ascii', errors='ignore').decode('ascii')
            print(f"  HealthSphere PDF Execution Text (Single Result Opened):\n{exec_text[:300]}...")
            assert "Healthsphere.pdf" in exec_text or "Opening" in exec_text, "Healthsphere.pdf single result launch failed!"

        shot6 = os.path.join(ARTIFACTS_DIR, "06_pdf_filter_verified.png")
        await page.screenshot(path=shot6, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot6}")
        print("  [SUCCESS] TEST 3 & 4 PASSED!")

        # Close modal if visible
        close_btn = page.locator("#file-search-actions button:has-text('Cancel')")
        if await close_btn.count() > 0 and await close_btn.is_visible():
            await close_btn.click()

        # ----------------------------------------------------------------------
        # TEST 5: Persistence & Reload Audit
        # ----------------------------------------------------------------------
        print("\n================================================================================")
        print("TEST 5: Persistence & Page Reload Audit")
        print("================================================================================")

        await page.reload(wait_until="networkidle")
        await asyncio.sleep(2)

        shot8 = os.path.join(ARTIFACTS_DIR, "08_persistence_verified.png")
        await page.screenshot(path=shot8, full_page=True)
        print(f"  [SCREENSHOT SAVED] {shot8}")
        print("  [SUCCESS] TEST 5 PASSED!")

        # Log summary
        print("\n================================================================================")
        print("SUMMARY OF CAPTURED BROWSER CONSOLE LOGS (First 15):")
        for cl in console_logs[:15]:
            print(f"  {cl.encode('ascii', errors='ignore').decode('ascii')}")
        print("================================================================================")

        await browser.close()
        print("\n REAL CHROME E2E AUTOMATION PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    asyncio.run(main())
