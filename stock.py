import json
import requests

def handler(request):
    path = request.path
    
    if path == "/api/analyze":
        symbol = request.query_params.get("symbol", "600000")
        try:
            secid = "1." + symbol if symbol.startswith("6") else "0." + symbol
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {"secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "klt": 101, "fqt": 0, "beg": "20240101", "end": "20260222", "lmt": 60}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("data") and data["data"].get("klines"):
                klines = data["data"]["klines"]
                closes = [float(k.split(',')[2]) for k in klines[-20:]]
                return {"symbol": symbol, "price": float(klines[-1].split(',')[2]), "ma5": sum(closes[-5:])/5}
        except:
            pass
        return {"error": "failed"}
    
    if path == "/api/limitup-pattern":
        try:
            url = 'https://push2.eastmoney.com/api/qt/clist/get'
            params = {"pn": 1, "pz": 20, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:10]
        except:
            stocks = []
        return {"total": len(stocks), "stocks": [s.get("f14", "") for s in stocks]}
    
    return {"status": "ok", "path": path}
