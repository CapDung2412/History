"""Optional real Chrome/UI smoke; no service mocks, no production index writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from src.config import PROJECT_ROOT


def check_layout(page, width: int, height: int) -> dict:
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_timeout(150)
    sizes = page.evaluate("""() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
    })""")
    assert sizes["document"] <= width + 1 and sizes["body"] <= width + 1, sizes
    return {"width": width, "height": height, "horizontal_overflow": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--image", type=Path, help="Enable real upload/recognition/content flow")
    parser.add_argument("--channel", default="chrome", help="Installed browser channel: chrome or msedge")
    args = parser.parse_args()
    report_dir = PROJECT_ROOT / "reports" / "browser"
    report_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        expect(page.locator("html")).to_have_attribute("lang", "vi")
        expect(page.get_by_role("heading", name="Chụp một chứng tích, mở một câu chuyện")).to_be_visible()
        for width, height in ((320, 800), (390, 844), (768, 1024), (1440, 1000)):
            checks.append(check_layout(page, width, height))
            page.screenshot(path=report_dir / f"home-{width}.png", full_page=True)
        page.get_by_role("button", name="Tăng cỡ chữ").click()
        page.get_by_role("button", name="Tương phản").click()
        checks.append(check_layout(page, 320, 800))
        page.reload(wait_until="networkidle")
        expect(page.locator("html")).to_have_attribute("data-contrast", "high")
        page.get_by_role("button", name="Tương phản").click()
        page.get_by_role("button", name="Giảm cỡ chữ").click()
        if args.image:
            image = args.image.resolve()
            assert image.is_file(), "Image does not exist"
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('input[type="file"]').first.set_input_files(image)
            expect(page.get_by_alt_text("Ảnh hiện vật chuẩn bị nhận diện")).to_be_visible()
            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/recognitions") and response.request.method == "POST",
                timeout=190_000,
            ) as recognition_response:
                page.get_by_role("button", name="Phân tích ảnh").click()
            response = recognition_response.value
            assert response.ok, f"Recognition HTTP {response.status}"
            result = response.json()
            status = result["recognition_status"]
            assert status != "rejected", f"Known smoke image rejected: {result['quality']['issues']}"
            if status == "needs_confirmation":
                page.get_by_role("button", name="Chọn hiện vật này").first.click()
            expect(page.get_by_role("tab", name="Nhìn nhanh")).to_be_visible(timeout=30_000)
            page.get_by_role("tab", name="Khám phá sâu").click()
            expect(page.get_by_role("tabpanel")).to_be_visible()
            for width, height in ((320, 800), (390, 844), (768, 1024), (1440, 1000)):
                checks.append(check_layout(page, width, height))
                page.screenshot(path=report_dir / f"story-{width}.png", full_page=True)
            checks.append({"real_recognition": status, "candidate_ids": [c["item_id"] for c in result["candidates"]]})
        assert not errors, f"Browser errors: {errors}"
        browser.close()
    report = {"checks": checks, "browser_errors": errors}
    (report_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
