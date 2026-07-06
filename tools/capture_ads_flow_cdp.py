import argparse
import json
import time
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright


KEEP_TYPES = {"XHR", "Fetch", "Document"}


def write_jsonl(path, obj):
    obj.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def attach_page(context_id, page, out_path):
    if getattr(page, "_ads_cdp_capture_attached", False):
        return
    page._ads_cdp_capture_attached = True
    session = page.context.new_cdp_session(page)
    session.send("Network.enable")

    def on_request(params):
        if params.get("type") not in KEEP_TYPES:
            return
        request = params.get("request", {})
        write_jsonl(
            out_path,
            {
                "event": "request",
                "context_id": context_id,
                "page_url": page.url,
                "request_id": params.get("requestId"),
                "resource_type": params.get("type"),
                "method": request.get("method"),
                "url": request.get("url"),
                "headers": request.get("headers", {}),
                "post_data": request.get("postData"),
                "has_post_data": request.get("hasPostData"),
                "initiator": params.get("initiator", {}),
            },
        )

    def on_response(params):
        if params.get("type") not in KEEP_TYPES:
            return
        response = params.get("response", {})
        write_jsonl(
            out_path,
            {
                "event": "response",
                "context_id": context_id,
                "page_url": page.url,
                "request_id": params.get("requestId"),
                "resource_type": params.get("type"),
                "url": response.get("url"),
                "status": response.get("status"),
                "status_text": response.get("statusText"),
                "headers": response.get("headers", {}),
                "mime_type": response.get("mimeType"),
            },
        )

    def on_failed(params):
        if params.get("type") not in KEEP_TYPES:
            return
        write_jsonl(
            out_path,
            {
                "event": "loading_failed",
                "context_id": context_id,
                "page_url": page.url,
                "request_id": params.get("requestId"),
                "resource_type": params.get("type"),
                "error_text": params.get("errorText"),
                "canceled": params.get("canceled"),
            },
        )

    session.on("Network.requestWillBeSent", on_request)
    session.on("Network.responseReceived", on_response)
    session.on("Network.loadingFailed", on_failed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, {"event": "capture_start", "cdp": args.cdp})

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(args.cdp)
            for context_id, context in enumerate(browser.contexts):
                for page in context.pages:
                    attach_page(context_id, page, out_path)
                context.on("page", lambda page, cid=context_id: attach_page(cid, page, out_path))
            write_jsonl(
                out_path,
                {
                    "event": "attached",
                    "contexts": len(browser.contexts),
                    "pages": sum(len(context.pages) for context in browser.contexts),
                },
            )
            while True:
                time.sleep(1)
    except Exception:
        write_jsonl(out_path, {"event": "fatal_error", "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
