#!/bin/zsh
set -e

cd "$(dirname "$0")"

python3 scripts/deal_monitor.py --config config/clothing_deal_sources.json

echo
echo "Opening data/clothing_deals.html..."
open data/clothing_deals.html

echo
echo "Done. Press any key to close this window."
read -k 1
