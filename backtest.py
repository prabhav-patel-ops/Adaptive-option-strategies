"""Single-contract, daily observation model. Signal at close, execute next open."""
import pandas as pd

def simulate(frame, policy="adaptive", band=.15, shock=.01, cost_bps=2, option_lot=1, futures_lot=1):
    if policy not in ("daily","adaptive","unhedged"): raise ValueError("unknown policy")
    f=frame.sort_values("date").reset_index(drop=True)
    if f.empty or f.date.duplicated().any(): raise ValueError("empty or duplicate dates")
    h=0; target=0; rows=[]; previous=None
    for i,x in f.iterrows():
        # Short one option lot. Futures P&L split at execution open.
        change=target-h
        cost=abs(change)*futures_lot*x.future_open*cost_bps/10000
        pnl=0 if previous is None else option_lot*(previous.option_close-x.option_close)+futures_lot*(h*(x.future_open-previous.future_close)+target*(x.future_close-x.future_open))-cost
        h=target
        tolerance=band/(1+abs(x.gamma*x.future_close*shock)/band)
        if policy=="daily" or (policy=="adaptive" and abs(h*futures_lot/option_lot-x.delta)>tolerance):
            target=round(x.delta*option_lot/futures_lot)
        rows.append(dict(date=x.date,pnl=pnl,cost=cost,hedge=h,turnover=abs(change)))
        previous=x
    out=pd.DataFrame(rows)
    out["cumulative_pnl"]=out.pnl.cumsum()
    return out
