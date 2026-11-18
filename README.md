To get the csv file:

python3 compare_stock.py SUPPLIER.csv PRESTASHOP.csv [-o output.csv] [--min-qty 10]

To apply changes to prestashop:

export PS_API_KEY=xxxxxxxx
python3 apply_changes.py --url https://yourshop.com            # dry run, shows what would change
python3 apply_changes.py --url https://yourshop.com --execute  # actually update