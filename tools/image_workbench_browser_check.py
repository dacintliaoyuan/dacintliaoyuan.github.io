"""Headless browser acceptance for the local image workbench (8765)."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / ".local" / "output" / "image-workbench-browser"
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8765"
IMAGE = Path(sys.argv[1]) if len(sys.argv) > 1 else None
ROOT_LIBRARY = Path(sys.argv[2]) if len(sys.argv) > 2 else None


def state():
    connection = http.client.HTTPConnection("127.0.0.1", 8765, timeout=10)
    connection.request("GET", "/api/state")
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return data


def post(path, payload):
    connection = http.client.HTTPConnection("127.0.0.1", 8765, timeout=30)
    body = json.dumps(payload).encode("utf-8")
    connection.request("POST", path, body=body,
                       headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    data = json.loads(response.read())
    status = response.status
    connection.close()
    return status, data


def item_detail(item_id):
    connection = http.client.HTTPConnection("127.0.0.1", 8765, timeout=10)
    connection.request("GET", f"/api/item/{item_id}")
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return data


def main():
    if IMAGE is None or ROOT_LIBRARY is None:
        raise SystemExit("usage: browser_check.py <image> <temp-root>")
    console = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.on("console", lambda message: console.append(f"{message.type}: {message.text}"))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/", wait_until="networkidle")
        tabs = page.locator("[role=tab]").all_inner_texts()
        print("tabs:", tabs)
        assert len(tabs) == 6, tabs
        page.screenshot(path=str(SHOTS / "01-deliver.png"), full_page=True)

        data = base64.b64encode(IMAGE.read_bytes()).decode("ascii")
        page.evaluate("""([data, name]) => {
          const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
          const transfer = new DataTransfer();
          transfer.items.add(new File([bytes], name, {type: 'image/png'}));
          const drop = document.getElementById('drop');
          drop.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: transfer}));
          drop.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: transfer}));
        }""", [data, IMAGE.name])
        page.wait_for_selector("#delivered-list .card", timeout=20000)
        print("delivered:", page.locator("#delivered-list .card").count())

        page.click('[data-tab="pending"]')
        page.wait_for_selector("#pending-list .card", timeout=20000)
        page.screenshot(path=str(SHOTS / "02-pending.png"), full_page=True)
        page.locator('#pending-list [data-action="start"]').first.click()
        page.click('[data-tab="ai"]')
        page.wait_for_selector("#ai-list .card", state="attached", timeout=30000)
        page.screenshot(path=str(SHOTS / "03-ai-task.png"), full_page=True)

        current = state()
        task = current["tasks"][-1]
        item = next(entry for entry in current["items"] if entry["id"] == task["itemId"])
        task_dir = ROOT_LIBRARY / ".local" / "output" / "homepage-images" / task["jobPath"]
        result = task_dir / "output" / "result.png"
        Image.new("RGB", tuple(item["original"]["size"]), (220, 220, 220)).save(result)
        output_sha = hashlib.sha256(result.read_bytes()).hexdigest()
        receipt = {
            "schemaVersion": 1, "taskId": task["taskId"],
            "inputSha256": task["input"]["sha256"], "outputSha256": output_sha,
            "size": task["input"]["size"], "format": "PNG",
            "summary": "browser acceptance: removed text", "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        (task_dir / "output" / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        # No scan button: the page's normal state poll must discover the pair.
        page.click('[data-tab="processed"]')
        page.wait_for_selector("#processed-list .card", timeout=30000)
        page.screenshot(path=str(SHOTS / "04-processed.png"), full_page=True)
        original_link = page.locator('#processed-list a.tag').first.get_attribute("href")
        print("original link:", original_link)
        assert "/media/originals/" in original_link, original_link

        first_enhanced = page.locator('#processed-list figcaption').nth(1).inner_text()
        first_adopt = page.locator(
            '#processed-list [data-action="adopt"]').nth(1).get_attribute("data-version")
        for round_number, color in ((2, 0.8), (3, 0.4)):
            status, payload = post("/api/start", {
                "itemIds": [item["id"]],
                "settings": {"removeText": "never", "upscale": "auto",
                             "denoise": 0.35, "color": color},
            })
            assert status == 200, payload
            for _ in range(150):
                current_item = item_detail(item["id"])
                if (current_item.get("processingRound", 0) >= round_number
                        and current_item["status"] == "processed"):
                    break
                time.sleep(0.2)
            else:
                raise AssertionError(f"第 {round_number} 轮重新处理未完成")
            page.wait_for_timeout(2500)
        third_enhanced = page.locator('#processed-list figcaption').nth(1).inner_text()
        third_adopt = page.locator(
            '#processed-list [data-action="adopt"]').nth(1).get_attribute("data-version")
        print("reprocess UI:", first_enhanced, "-> 0.8 ->", third_enhanced)
        assert third_enhanced == first_enhanced, (first_enhanced, third_enhanced)
        assert third_adopt == first_adopt, (first_adopt, third_adopt)

        page.locator('#processed-list [data-action="compare-mode"][data-mode="slider"]').first.click()
        slider = page.locator("[data-slider]").first
        slider.fill("30")
        slider.dispatch_event("input")
        page.screenshot(path=str(SHOTS / "05-compare-slider.png"), full_page=True)

        page.locator('#processed-list [data-action="adopt"]').nth(1).click()
        page.wait_for_timeout(800)
        adopted = next(entry for entry in state()["items"] if entry["id"] == item["id"])
        assert adopted["adoptedVersion"] == third_adopt, (adopted, third_adopt)
        page.click("#create-draft")
        page.wait_for_selector("#drafts-list .draft", timeout=30000)
        page.screenshot(path=str(SHOTS / "06-draft.png"), full_page=True)
        iframe = page.locator("#drafts-list iframe").first
        page.wait_for_timeout(1500)
        preview_frame = next((frame for frame in page.frames if "/preview/" in frame.url), None)
        assert preview_frame is not None, [frame.url for frame in page.frames]
        scenes = preview_frame.evaluate("window.HOME_MANIFEST ? window.HOME_MANIFEST.scenes.length : -1")
        print("draft iframe scenes:", scenes)
        assert scenes == 1, scenes

        page.set_viewport_size({"width": 700, "height": 900})
        page.screenshot(path=str(SHOTS / "07-narrow.png"), full_page=True)
        page.click('[data-tab="enabled"]')
        page.screenshot(path=str(SHOTS / "08-enabled.png"), full_page=True)
        print("console:", [line for line in console if line.startswith("error")])
        print("page errors:", errors)
        assert not errors, errors
        browser.close()
    print("browser check OK")


if __name__ == "__main__":
    main()
