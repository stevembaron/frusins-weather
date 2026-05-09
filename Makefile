.PHONY: deals clothing-deals

deals:
	python3 scripts/deal_monitor.py

clothing-deals:
	python3 scripts/deal_monitor.py --config config/clothing_deal_sources.json
