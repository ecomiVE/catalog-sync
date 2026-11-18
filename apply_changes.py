#!/usr/bin/env python3
"""
Apply the changes from stock_changes.csv (made by compare_stock.py) to PrestaShop
through the PrestaShop Webservice API.

- ACTIVATE rows   -> product set active = 1
- DEACTIVATE rows -> product set active = 0, ONLY if it was matched at the
                     supplier (products not in the supplier file are skipped.

Usage:
    export PS_API_KEY=xxxxxxxx
    python3 apply_changes.py --url https://yourshop.com            # dry run, shows what would change
    python3 apply_changes.py --url https://yourshop.com --execute  # actually update
"""
import argparse
import base64
import csv
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# Fields the API returns but rejects on PUT
READ_ONLY_FIELDS = ("manufacturer_name", "quantity", "position_in_category")


def load_changes(path):
    activate, deactivate, skipped = [], [], 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            pid = int(r["id_product"])
            if r["action"] == "ACTIVATE":
                activate.append(pid)
            elif r["action"] == "DEACTIVATE":
                if r["matched_by"] == "not_found":
                    skipped += 1
                else:
                    deactivate.append(pid)
    return activate, deactivate, skipped


class PrestaShopAPI:
    def __init__(self, base_url, key, timeout=30):
        self.base = base_url.rstrip("/") + "/api"
        token = base64.b64encode(f"{key}:".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}
        self.timeout = timeout

    def _request(self, method, path, body=None):
        headers = dict(self.headers)
        if body is not None:
            headers["Content-Type"] = "application/xml"
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def set_active(self, product_id, active):
        """Returns True if changed, False if it already had that value."""
        root = ET.fromstring(self._request("GET", f"/products/{product_id}"))
        product = root.find("product")
        el = product.find("active")
        new = "1" if active else "0"
        if (el.text or "").strip() == new:
            return False
        el.text = new
        for name in READ_ONLY_FIELDS:
            node = product.find(name)
            if node is not None:
                product.remove(node)
        self._request("PUT", f"/products/{product_id}", ET.tostring(root, encoding="utf-8"))
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("changes_csv", nargs="?", default="stock_changes.csv")
    ap.add_argument("--url", required=True, help="shop base URL, e.g. https://yourshop.com")
    ap.add_argument("--key", default=os.environ.get("PS_API_KEY"), help="API key (or env PS_API_KEY)")
    ap.add_argument("--execute", action="store_true", help="really update (otherwise dry run)")
    ap.add_argument("--delay", type=float, default=0.1, help="seconds between requests")
    ap.add_argument("--log", default="apply_log.csv")
    args = ap.parse_args()

    activate, deactivate, skipped = load_changes(args.changes_csv)
    print(f"To activate:   {len(activate)}")
    print(f"To deactivate: {len(deactivate)}  (skipped {skipped} not found at supplier)")

    if not args.execute:
        print("Dry run: nothing changed. Add --execute to apply.")
        return
    if not args.key:
        sys.exit("No API key: use --key or set PS_API_KEY")

    api = PrestaShopAPI(args.url, args.key)
    jobs = [(pid, True) for pid in activate] + [(pid, False) for pid in deactivate]
    counts = {"updated": 0, "unchanged": 0, "error": 0}

    with open(args.log, "w", newline="", encoding="utf-8") as logf:
        log = csv.writer(logf, delimiter=";")
        log.writerow(["id_product", "action", "result", "error"])
        for i, (pid, active) in enumerate(jobs, 1):
            action = "ACTIVATE" if active else "DEACTIVATE"
            try:
                result = "updated" if api.set_active(pid, active) else "unchanged"
                err = ""
            except urllib.error.HTTPError as e:
                result, err = "error", f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"
            except Exception as e:
                result, err = "error", str(e)
            counts[result] += 1
            log.writerow([pid, action, result, err])
            if result == "error":
                print(f"  ! {pid} {action}: {err}", file=sys.stderr)
            if i % 100 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}  {counts}")
            time.sleep(args.delay)

    print(f"Done: {counts}. Details in {args.log}")


if __name__ == "__main__":
    main()
