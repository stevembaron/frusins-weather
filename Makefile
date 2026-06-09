.PHONY: deals clothing-deals brief test

deals:
	python3 scripts/deal_monitor.py

clothing-deals:
	python3 scripts/deal_monitor.py --config config/clothing_deal_sources.json

brief:
	python3 scripts/deal_analyst.py

test:
	python3 -m unittest discover tests
