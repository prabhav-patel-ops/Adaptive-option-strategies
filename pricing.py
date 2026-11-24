from math import log, sqrt, exp
from scipy.stats import norm
from scipy.optimize import brentq

def price(F,K,T,r,sigma,kind="CE"):
    if min(F,K,T,sigma)<=0: raise ValueError("positive inputs required")
    if kind not in ("CE","PE"): raise ValueError("invalid option type")
    d1=(log(F/K)+sigma*sigma*T/2)/(sigma*sqrt(T))
    d2=d1-sigma*sqrt(T)
    s=1 if kind=="CE" else -1
    return exp(-r*T)*s*(F*norm.cdf(s*d1)-K*norm.cdf(s*d2))

def iv(p,F,K,T,r,kind="CE"):
    if kind not in ("CE","PE") or min(F,K,T)<=0: raise ValueError("invalid inputs")
    s=1 if kind=="CE" else -1
    if not exp(-r*T)*max(s*(F-K),0)<p<exp(-r*T)*(F if s==1 else K): raise ValueError("outside IV bounds")
    return brentq(lambda v:price(F,K,T,r,v,kind)-p,1e-8,10)

def greeks(F,K,T,r,sigma,kind="CE"):
    d1=(log(F/K)+sigma*sigma*T/2)/(sigma*sqrt(T))
    D=exp(-r*T)
    return D*(norm.cdf(d1)-(kind=="PE")), D*norm.pdf(d1)/(F*sigma*sqrt(T)), D*F*norm.pdf(d1)*sqrt(T)
