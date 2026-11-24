import pandas as pd
from backtest import simulate

if __name__=="__main__":
    panel=pd.read_csv("data/panel.csv")
    for col in ("NewBrdLotQty_option","NewBrdLotQty_future"):
        if panel[col].nunique()!=1: raise ValueError("Lot size changes require explicit handling")
    for policy in ("unhedged","daily","adaptive"):
        out=simulate(panel,policy=policy,option_lot=panel.NewBrdLotQty_option.iloc[0],futures_lot=panel.NewBrdLotQty_future.iloc[0])
        out.to_csv(f"data/{policy}.csv",index=False)
        print(policy,{"pnl":out.pnl.sum(),"cost":out.cost.sum(),"turnover":out.turnover.sum()})
