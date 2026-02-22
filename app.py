from flask import Flask, jsonify
import requests

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def get_klines(symbol):
    try:
        secid = "1." + symbol if symbol.startswith('6') else "0." + symbol
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {"secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "klt": 101, "fqt": 0, "beg": "20240101", "end": "20260222", "lmt": 60}
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            return data["data"]["klines"]
    except:
        pass
    return None

def calc_indicators(klines):
    import numpy as np
    try:
        closes = [float(k.split(',')[2]) for k in klines]
        highs = [float(k.split(',')[3]) for k in klines]
        lows = [float(k.split(',')[4]) for k in klines]
        volumes = [float(k.split(',')[5]) for k in klines]
        
        ind = {}
        
        # WR
        h14 = max(highs[-14:])
        l14 = min(lows[-14:])
        ind['wr_14'] = 100 * (closes[-1] - l14) / (h14 - l14) if h14 != l14 else 50
        
        # MA
        ind['ma5'] = sum(closes[-5:]) / 5
        ind['ma10'] = sum(closes[-10:]) / 10
        ind['ma20'] = sum(closes[-20:]) / 20
        ind['ma多头'] = 1 if ind['ma5'] > ind['ma10'] > ind['ma20'] else 0
        
        # 资金
        vol_ma5 = sum(volumes[-5:]) / 5
        change = (closes[-1] - closes[-2]) / closes[-2] * 100
        ind['资金流入'] = 1 if volumes[-1] > vol_ma5 * 1.3 and change > 0 else 0
        
        # 位置
        high20 = max(highs[-20:])
        ind['接近新高'] = 1 if closes[-1] >= high20 * 0.95 else 0
        
        return ind, closes, change
    except:
        return None, [], 0

def score_stock(ind, change):
    score = 0
    reasons = []
    
    if ind.get('ma多头'):
        score += 20
        reasons.append("均线多头")
    
    if ind.get('wr_14', 50) <= 20:
        score += 12
        reasons.append("WR超卖")
    
    if ind.get('资金流入'):
        score += 15
        reasons.append("资金流入")
    
    if ind.get('接近新高'):
        score += 10
        reasons.append("接近新高")
    
    if change > 3:
        score += 5
        reasons.append("涨幅较好")
    
    if score >= 30:
        return "强烈买入", score, reasons
    elif score >= 15:
        return "买入", score, reasons
    elif score >= 5:
        return "加仓", score, reasons
    elif score >= 0:
        return "观望", score, reasons
    else:
        return "减仓", score, reasons

@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_klines(symbol)
    if not klines:
        return jsonify({'error': '无法获取数据'})
    
    ind, closes, change = calc_indicators(klines)
    if not ind:
        return jsonify({'error': '计算失败'})
    
    signal, score, reasons = score_stock(ind, change)
    
    return jsonify({
        'symbol': symbol,
        'price': closes[-1] if closes else 0,
        'change': change,
        'signal': signal,
        'score': score,
        'reasons': reasons
    })

@app.route('/api/top-stocks')
def top_stocks():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 30, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f2,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = data.get("data", {}).get("diff", [])[:20]
    except:
        stocks = []
    
    results = []
    for s in stocks:
        try:
            code = s['f12']
            klines = get_klines(code)
            if klines and len(klines) >= 20:
                ind, closes, change = calc_indicators(klines)
                if ind:
                    signal, score, reasons = score_stock(ind, change)
                    results.append({
                        'code': code,
                        'name': s.get('f14', ''),
                        'price': closes[-1] if closes else 0,
                        'change': s.get('f3', 0),
                        'signal': signal,
                        'score': score,
                        'reasons': reasons[:2]
                    })
        except:
            continue
    
    results.sort(key=lambda x: -x['score'])
    return jsonify(results[:10])

@app.route('/api/limitup-pattern')
def limitup():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 50, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:30]
    except:
        stocks = []
    
    stats = {"total": len(stocks), "强烈买入": 0, "买入": 0, "加仓": 0, "观望": 0, "减仓": 0}
    
    for s in stocks:
        try:
            klines = get_klines(s['f12'])
            if klines and len(klines) >= 20:
                ind, closes, change = calc_indicators(klines)
                if ind:
                    signal, score, reasons = score_stock(ind, change)
                    stats[signal] = stats.get(signal, 0) + 1
        except:
            continue
    
    return jsonify(stats)
