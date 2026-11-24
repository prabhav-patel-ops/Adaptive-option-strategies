"""Build a single-contract research panel from locally downloaded UDiFF archives."""
import argparse
from pathlib import Path
import pandas as pd
from pricing import iv,greeks

def prepare(strike,expiry,kind,future_expiry,rate):
    frames=[pd.read_csv(p,compression="zip",low_memory=False) for p in sorted(Path("data/raw").glob("*.zip"))]
    if not frames: raise ValueError("No archives downloaded")
    d=pd.concat(frames,ignore_index=True)
    d=d[d.TckrSymb.eq("NIFTY")].copy()
    d["date"]=pd.to_datetime(d.TradDt)
    d["expiry"]=pd.to_datetime(d.XpryDt)
    o=d[(d.StrkPric.eq(strike)) & d.OptnTp.eq(kind) & d.expiry.eq(pd.Timestamp(expiry))]
    f=d[d.FinInstrmTp.eq("IDF") & d.expiry.eq(pd.Timestamp(future_expiry))]
    panel=o[["date","ClsPric","NewBrdLotQty"]].merge(f[["date","OpnPric","ClsPric","NewBrdLotQty"]],on="date",validate="one_to_one",suffixes=("_option","_future"))
    panel=panel.rename(columns={"ClsPric_option":"option_close","ClsPric_future":"future_close","OpnPric":"future_open"})
    rows=[]
    for x in panel.sort_values("date").to_dict("records"):
        T=(pd.Timestamp(expiry)-x["date"]).days/365
        if T<=0: continue
        try:
            sigma=iv(x["option_close"],x["future_close"],strike,T,rate,kind)
            x["iv"]=sigma
            x["delta"],x["gamma"],x["vega"]=greeks(x["future_close"],strike,T,rate,sigma,kind)
            rows.append(x)
        except ValueError:
            continue
    if not rows: raise ValueError("No valid matched quotes; inspect schema and contract selection")
    return pd.DataFrame(rows)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--strike",type=float,required=True); p.add_argument("--expiry",required=True)
    p.add_argument("--kind",choices=["CE","PE"],default="CE"); p.add_argument("--future-expiry",required=True)
    p.add_argument("--rate",type=float,default=.06)
    a=p.parse_args()
    prepare(a.strike,a.expiry,a.kind,a.future_expiry,a.rate).to_csv("data/panel.csv",index=False)
