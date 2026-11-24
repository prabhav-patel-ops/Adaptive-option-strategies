# Research protocol

1. Install dependencies: pip install -r requirements.txt
2. Confirm exchange terms permit the intended automated access and storage.
3. Download locally: python fetch_nse.py YYYY-MM-DD YYYY-MM-DD
4. Inspect data/raw/missing.csv and archive schemas; holidays and failed requests must be distinguished.
5. Select a liquid option and a matching expiry futures contract. For different maturities, forward basis adjustment is required before interpreting IV.
6. Run python prepare.py --strike STRIKE --expiry YYYY-MM-DD --future-expiry YYYY-MM-DD --kind CE
7. Run python run_research.py

This is a prototype single-position experiment, not a validated trading system. The sample excludes expiry and does not liquidate the final futures position; report results as marked-to-market over the observation window. Missing observations, execution assumptions, lot rounding, funding, spreads and expiry settlement need further validation. No raw exchange data should be published. Dashboard is illustrative until real data are validated. For Pages, choose main /docs in repository Settings > Pages.
