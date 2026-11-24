"""Download permitted daily archives locally; never publish raw exchange data."""
import argparse, io, zipfile
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def fetch(start,end):
    root=Path("data/raw"); root.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    session.mount("https://",HTTPAdapter(max_retries=Retry(total=3,backoff_factor=2,status_forcelist=[429,500,502,503,504],respect_retry_after_header=True)))
    failures=[]
    for day in pd.bdate_range(start,end):
        date=day.strftime("%Y%m%d"); path=root/f"{date}.zip"
        if path.exists() and zipfile.is_zipfile(path): continue
        url=f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date}_F_0000.csv.zip"
        try:
            response=session.get(url,timeout=30)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                if z.testzip() or not any(n.endswith(".csv") for n in z.namelist()): raise ValueError("invalid archive")
            path.write_bytes(response.content)
        except (requests.RequestException,ValueError,zipfile.BadZipFile) as exc:
            failures.append((date,str(exc)))
    pd.DataFrame(failures,columns=["date","error"]).to_csv(root/"missing.csv",index=False)
    return failures

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("start"); p.add_argument("end"); a=p.parse_args()
    print(fetch(a.start,a.end))
