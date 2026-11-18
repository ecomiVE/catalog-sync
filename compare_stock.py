#!/usr/bin/env python3
"""
Find PrestaShop products that are inactive but in stock at the supplier.

Usage:
    python3 compare_stock.py SUPPLIER.csv PRESTASHOP.csv [-o output.csv] [--min-qty 10]

Matching: PrestaShop `reference` = supplier "Codice Articolo"; if no match,
falls back to PrestaShop `ean13` against any of the supplier's EAN columns.
"""
import argparse
import csv
import sys

# Supplier file columns (by position, because the EAN headers are malformed)
COL_CODE = 0
COL_EANS = range(1, 11)
COL_DESC = 11
COL_QTY = 25
COL_PRICE = 27


def to_int(value):
    try:
        return int(float(value.strip().replace(".", "").replace(",", ".") or 0))
    except ValueError:
        return 0


def load_supplier(path):
    by_code, by_ean = {}, {}
    with open(path, newline="", encoding="latin-1") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # header
        for row in reader:
            if len(row) <= COL_PRICE:
                continue
            item = {
                "code": row[COL_CODE].strip(),
                "desc": row[COL_DESC].strip(),
                "qty": to_int(row[COL_QTY]),
                "price": row[COL_PRICE].strip(),
            }
            by_code[item["code"]] = item
            for i in COL_EANS:
                ean = row[i].strip()
                if ean:
                    by_ean[ean] = item
    return by_code, by_ean


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("supplier_csv")
    ap.add_argument("prestashop_csv")
    ap.add_argument("-o", "--output", default="stock_changes.csv")
    ap.add_argument("--min-qty", type=int, default=10)
    args = ap.parse_args()

    by_code, by_ean = load_supplier(args.supplier_csv)

    results = []
    with open(args.prestashop_csv, newline="", encoding="utf-8-sig") as f:
        for p in csv.DictReader(f, delimiter=";"):
            active = p["active"].strip() == "1"
            ref, ean = p["reference"].strip(), p["ean13"].strip()
            item, matched_by = by_code.get(ref), "reference"
            if item is None and ean:
                item, matched_by = by_ean.get(ean), "ean13"
            if item is None:
                matched_by = "not_found"
            qty = item["qty"] if item else 0
            in_stock = qty >= args.min_qty

            if not active and in_stock:
                action = "ACTIVATE"
            elif active and not in_stock:
                action = "DEACTIVATE"
            else:
                continue  # already in the right state

            results.append({
                "action": action,
                "id_product": p["id_product"],
                "reference": ref,
                "ean13": ean,
                "name": p["name"],
                "currently_active": "1" if active else "0",
                "supplier_qty": qty,
                "supplier_code": item["code"] if item else "",
                "supplier_description": item["desc"] if item else "",
                "supplier_price": item["price"] if item else "",
                "matched_by": matched_by,
            })

    results.sort(key=lambda r: (r["action"], -r["supplier_qty"]))
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else ["id_product"], delimiter=";")
        w.writeheader()
        w.writerows(results)

    to_activate = [r for r in results if r["action"] == "ACTIVATE"]
    to_deactivate = [r for r in results if r["action"] == "DEACTIVATE"]
    not_found = sum(1 for r in to_deactivate if r["matched_by"] == "not_found")
    print(f"Threshold: supplier stock >= {args.min_qty}")
    print(f"Can ACTIVATE:   {len(to_activate)}")
    print(f"Can DEACTIVATE: {len(to_deactivate)}  (of which {not_found} not found at supplier)")
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
