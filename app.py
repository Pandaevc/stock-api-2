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
        params = {"secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "klt": 101, "fqt": 0, "beg": "20240101", "end": "20260222", "lmt": 30}
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            return data["data"]["klines"][-30:]
    except:
        pass
    return None

@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_klines(symbol)
    if not klines or len(klines) < 20:
        return jsonify({'error': '无数据'})
    
    try:
        closes = [float(k.split(',')[2]) for k in klines]
        highs = [float(k.split(',')[3]) for k in klines]
        lows = [float(k.split(',')[4]) for k in klines]
        volumes = [float(k.split(',')[5]) for k in klines]
        
        # WR
        h14, l14 = max(highs[-14:]), min(lows[-14:])
        wr = 100 * (closes[-1] - l14) / (h14 - l14) if h14 != l14 else 50
        
        # MA
        ma5, ma10, ma20 = sum(closes[-5:])/5, sum(closes[-10:])/10, sum(closes[-20:])/20
        ma多头 = 1 if ma5 > ma10 > ma20 else 0
        
        # 资金
        v5 = sum(volumes[-5:])/5
        change = (closes[-1] - closes[-2]) / closes[-2] * 100
        zijing = 1 if volumes[-1] > v5 * 1.3 and change > 0 else 0
        
        # 评分
        score = 0
        reasons = []
        if ma多头: score += 20; reasons.append("均线多头")
        if wr < 20: score += 12; reasons.append("WR超卖")
        if zijing: score += 15; reasons.append("资金流入")
        
        signal = "买入" if score >= 20 else "加仓" if score >= 10 else "观望"
        
        return jsonify({'symbol': symbol, 'price': closes[-1], 'change': change, 'signal': signal, 'score': score, 'reasons': reasons})
    except:
        return jsonify({'error': '计算错误'})

@app.route('/api/top-stocks')
def top_stocks():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 30, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f2,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = data.get("data", {}).get("diff", [])[:10]
    except:
        stocks = []
    
    results = []
    for s in stocks:
        try:
            code = s['f12']
            klines = get_klines(code)
            if klines and len(klines) >= 20:
                closes = [float(k.split(',')[2]) for k in klines]
                highs = [float(k.split(',')[3]) for k in klines]
                lows = [float(k.split(',')[4]) for k in klines]
                volumes = [float(k.split(',')[5]) for k in klines]
                
                # WR
                h14, l14 = max(highs[-14:]), min(lows[-14:])
                wr = 100 * (closes[-1] - l14) / (h14 - l14) if h14 != l14 else 50
                
                # MA
                ma5, ma10, ma20 = sum(closes[-5:])/5, sum(closes[-10:])/10, sum(closes[-20:])/20
                ma多头 = 1 if ma5 > ma10 > ma20 else 0
                
                # 资金
                v5 = sum(volumes[-5:])/5
                change = (closes[-1] - closes[-2]) / closes[-2] * 100
                zijing = 1 if volumes[-1] > v5 * 1.3 and change > 0 else 0
                
                # 评分
                score = 0
                reasons = []
                if ma多头: score += 20; reasons.append("均线多头")
                if wr < 20: score += 12; reasons.append("WR超卖")
                if zijing: score += 15; reasons.append("资金流入")
                
                signal = "买入" if score >= 20 else "加仓" if score >= 10 else "观望"
                
                results.append({
                    'code': code,
                    'name': s.get('f14', ''),
                    'price': closes[-1],
                    'change': s.get('f3', 0),
                    'signal': signal,
                    'score': score,
                    'reasons': reasons[:2]
                })
        except:
            continue
    
    results.sort(key=lambda x: -x['score'])
    return jsonify(results[:5])

@app.route('/api/limitup-pattern')
def limitup():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 50, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:10]
    except:
        stocks = []
    
    stats = {"total": len(stocks), "强烈买入": 0, "买入": 0, "加仓": 0, "观望": 0, "减仓": 0}
    
    for s in stocks:
        try:
            klines = get_klines(s['f12'])
            if klines and len(klines) >= 20:
                closes = [float(k.split(',')[2]) for k in klines]
                highs = [float(k.split(',')[3]) for k in klines]
                lows = [float(k.split(',')[4]) for k in klines]
                volumes = [float(k.split(',')[5]) for k in klines]
                
                h14, l14 = max(highs[-14:]), min(lows[-14:])
                wr = 100 * (closes[-1] - l14) / (h14 - l14) if h14 != l14 else 50
                
                ma5, ma10, ma20 = sum(closes[-5:])/5, sum(closes[-10:])/10, sum(closes[-20:])/20
                ma多头 = 1 if ma5 > ma10 > ma20 else 0
                
                v5 = sum(volumes[-5:])/5
                change = (closes[-1] - closes[-2]) / closes[-2] * 100
                zijing = 1 if volumes[-1] > v5 * 1.3 and change > 0 else 0
                
                score = 0
                if ma多头: score += 20
                if wr < 20: score += 12
                if zijing: score += 15
                
                signal = "买入" if score >= 20 else "加仓" if score >= 10 else "观望"
                stats[signal] = stats.get(signal, 0) + 1
        except:
            continue
    
    return jsonify(stats)
