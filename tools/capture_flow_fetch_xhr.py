import argparse
import json
import time
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright


def write_jsonl(path, obj):
    obj.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


HOOK_SCRIPT = r"""
(() => {
  window.__flowCaptureInstalled = true;

  const emit = (payload) => {
    try {
      window.__flowCaptureEmit(JSON.stringify({
        ts: new Date().toISOString(),
        pageUrl: location.href,
        ...payload,
      }));
    } catch (error) {
      console.warn("flow capture emit failed", error);
    }
  };

  const normalizeHeaders = (headers) => {
    try {
      if (!headers) return {};
      if (headers instanceof Headers) return Object.fromEntries(headers.entries());
      if (Array.isArray(headers)) return Object.fromEntries(headers);
      if (typeof headers === "object") return {...headers};
    } catch (error) {
      return {__capture_error: String(error)};
    }
    return {};
  };

  const normalizeBody = (body) => {
    if (body == null) return null;
    if (typeof body === "string") return body;
    if (body instanceof URLSearchParams) return body.toString();
    if (body instanceof FormData) {
      const items = [];
      for (const [key, value] of body.entries()) {
        if (value instanceof File) {
          items.push([key, {fileName: value.name, type: value.type, size: value.size}]);
        } else {
          items.push([key, String(value)]);
        }
      }
      return {formData: items};
    }
    try {
      return JSON.stringify(body);
    } catch {
      return String(body);
    }
  };

  const originalFetch = window.__flowCaptureOriginalFetch || window.fetch;
  window.__flowCaptureOriginalFetch = originalFetch;
  window.fetch = async function(input, init = {}) {
    const url = typeof input === "string" ? input : input?.url;
    const method = init?.method || input?.method || "GET";
    const headers = {...normalizeHeaders(input?.headers), ...normalizeHeaders(init?.headers)};
    const body = normalizeBody(init?.body);
    const startedAt = Date.now();
    try {
      const response = await originalFetch.apply(this, arguments);
      emit({
        event: "fetch",
        method,
        url,
        headers,
        body,
        status: response.status,
        ok: response.ok,
        durationMs: Date.now() - startedAt,
      });
      return response;
    } catch (error) {
      emit({
        event: "fetch_error",
        method,
        url,
        headers,
        body,
        error: String(error),
        durationMs: Date.now() - startedAt,
      });
      throw error;
    }
  };

  const originalOpen = window.__flowCaptureOriginalXhrOpen || XMLHttpRequest.prototype.open;
  const originalSetHeader = window.__flowCaptureOriginalXhrSetHeader || XMLHttpRequest.prototype.setRequestHeader;
  const originalSend = window.__flowCaptureOriginalXhrSend || XMLHttpRequest.prototype.send;
  window.__flowCaptureOriginalXhrOpen = originalOpen;
  window.__flowCaptureOriginalXhrSetHeader = originalSetHeader;
  window.__flowCaptureOriginalXhrSend = originalSend;

  XMLHttpRequest.prototype.open = function(method, url) {
    this.__flowCapture = {method, url, headers: {}, startedAt: 0};
    return originalOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
    if (this.__flowCapture) this.__flowCapture.headers[name] = value;
    return originalSetHeader.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function(body) {
    const meta = this.__flowCapture || {method: "GET", url: ""};
    meta.startedAt = Date.now();
    meta.body = normalizeBody(body);
    this.addEventListener("loadend", () => {
      emit({
        event: "xhr",
        method: meta.method,
        url: meta.url,
        headers: meta.headers || {},
        body: meta.body,
        status: this.status,
        durationMs: Date.now() - meta.startedAt,
      });
    });
    return originalSend.apply(this, arguments);
  };

  emit({event: "hook_installed"});
  return "installed";
})();
"""


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

            def emit(payload):
                try:
                    write_jsonl(out_path, json.loads(payload))
                except Exception as error:
                    write_jsonl(out_path, {"event": "emit_error", "error": repr(error), "payload": payload})

            attached = 0
            for context in browser.contexts:
                for page in context.pages:
                    if "labs.google/fx/tools/flow" not in page.url:
                        continue
                    page.expose_function("__flowCaptureEmit", emit)
                    page.add_init_script(HOOK_SCRIPT)
                    result = page.evaluate(HOOK_SCRIPT)
                    write_jsonl(out_path, {"event": "attached", "page_url": page.url, "result": result})
                    page.reload(wait_until="domcontentloaded")
                    write_jsonl(out_path, {"event": "reloaded", "page_url": page.url})
                    attached += 1

            write_jsonl(out_path, {"event": "ready", "attached_pages": attached})
            while True:
                time.sleep(1)
    except Exception:
        write_jsonl(out_path, {"event": "fatal_error", "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
