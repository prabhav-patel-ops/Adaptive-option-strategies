# Adaptive Option Strategies

Can gamma-aware delta rebalancing reduce transaction costs while containing tail risk relative to daily hedging?

[Open the research dashboard](https://prabhav-patel-ops.github.io/Adaptive-option-strategies/) · [Open the pricing lab](https://prabhav-patel-ops.github.io/Adaptive-option-strategies/model-lab.html) · [View automation runs](https://github.com/prabhav-patel-ops/Adaptive-option-strategies/actions/workflows/research.yml)

The research pipeline validates NSE F&O UDiFF archives, matches NIFTY options and futures by expiry, applies Black-76, and compares unhedged, daily, and adaptive hedges. The dashboard reports the latest workflow status and displays historical results when a source and derived publication are authorized. Its model lab computes an illustrative gamma band from the supplied inputs.

## Run tests

```sh
python -m pip install -r requirements.txt
python -m pytest -q
node --check docs/dashboard.js
```

[The research protocol](RESEARCH.md) describes the experiment, data permissions, source format, and local and scheduled runs.
