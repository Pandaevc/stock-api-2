from flask import Flask, jsonify
import requests

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def get_klines(symbol, days=120):
    try:
        secid = "1." + symbol if symbol.startswith('6') else "0." + symbol
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {"secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "klt": 101, "fqt": 0, "beg": "20240101", "end": "20260222", "lmt": days}
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            return data["data"]["klines"]
    except:
        pass
    return None

def calculate_all(klines):
    """计算所有指标"""
    import numpy as np
    closes = [float(k.split(',')[2]) for k in klines]
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    opens = [float(k.split(',')[1]) for k in klines]
    volumes = [float(k.split(',')[5]) for k in klines]
    
    ind = {}
    
    # WR
    for n in [14, 10]:
        h = max(highs[-n:])
        l = min(lows[-n:])
        ind[f'wr_{n}'] = 100 * (closes[-1] - l) / (h - l) if h != l else 50
    
    # CCI
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(-14, 0)]
    tp_avg = sum(tp) / 14
    tp_dev = sum(abs(t - tp_avg) for t in tp) / 14
    ind['cci'] = (tp[-1] - tp_avg) / (0.015 * tp_dev) if tp_dev > 0 else 0
    
    # 均线
    ind['ma5'] = sum(closes[-5:]) / 5
    ind['ma10'] = sum(closes[-10:]) / 10
    ind['ma20'] = sum(closes[-20:]) / 20
    ind['ma多头'] = 1 if ind['ma5'] > ind['ma10'] > ind['ma20'] else 0
    ind['ma空头'] = 1 if ind['ma5'] < ind['ma10'] < ind['ma20'] else 0
    
    # RSI
    if len(closes) >= 14:
        delta = [closes[i] - closes[i-1] for i in range(1, 14)]
        gain = [d if d > 0 else 0 for d in delta]
        loss = [-d if d < 0 else 0 for d in delta]
        avg_gain = sum(gain) / 14
        avg_loss = sum(loss) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        ind['rsi'] = 100 - (100 / (1 + rs))
    
    # 资金
    vol_ma5 = sum(volumes[-5:]) / 5
    price_change = (closes[-1] - closes[-2]) / closes[-2] * 100
    ind['放量上涨'] = 1 if volumes[-1] > vol_ma5 * 1.3 and price_change > 0 else 0
    ind['资金流入'] = 1 if volumes[-1] > vol_ma5 * 1.3 and price_change > 0 else 0
    ind['资金强势流入'] = 1 if volumes[-1] > vol_ma5 * 1.5 and price_change > 2 else 0
    
    # 位置
    high20 = max(highs[-20:])
    ind['接近新高'] = 1 if closes[-1] >= high20 * 0.95 else 0
    ind['突破'] = 1 if closes[-1] > max(highs[-5:-1]) else 0
    
    return ind

def comprehensive_score(ind):
    """综合评分"""
    score = 0
    reasons = []
    
    # 均线
    if ind.get('ma多头'):
        score += 20
        reasons.append("均线多头排列")
    if ind.get('ma空头'):
        score -= 15
        reasons.append("均线空头排列")
    
    # WR
    if ind.get('wr_14', 50) <= 20:
        score += 12
        reasons.append("WR超卖")
    elif ind.get('wr_14', 50) >= 80:
        score -= 8
        reasons.append("WR超买")
    
    # CCI
    if ind.get('cci', 0) < -100:
        score += 10
        reasons.append("CCI超卖反弹")
    elif ind.get('cci', 0) > 100:
        score -= 6
        reasons.append("CCI超买")
    
    # RSI
    if ind.get('rsi', 50) < 30:
        score += 8
        reasons.append("RSI超卖")
    elif ind.get('rsi', 50) > 70:
        score -= 5
        reasons.append("RSI超买")
    
    # 资金
    if ind.get('资金强势流入'):
        score += 15
        reasons.append("资金强势流入")
    elif ind.get('资金流入'):
        score += 8
        reasons.append("资金流入")
    
    # 量价
    if ind.get('放量上涨'):
        score += 10
        reasons.append("放量上涨")
    
    # 位置
    if ind.get('突破'):
        score += 15
        reasons.append("放量突破")
    elif ind.get('接近新高'):
        score += 10
        reasons.append("接近新高")
    
    # 评级
    if score >= 35:
        return "强烈买入", score, reasons
    elif score >= 20:
        return "买入", score, reasons
    elif score >= 8:
        return "加仓", score, reasons
    elif score >= -2:
        return "观望", score, reasons
    else:
        return "减仓", score, reasons

# === 分析单只股票 ===
@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_klines(symbol, 60)
    if not klines:
        return jsonify({'error': '无法获取数据'})
    
    ind = calculate_all(klines)
    signal, score, reasons = comprehensive_score(ind)
    closes = [float(k.split(',')[2]) for k in klines]
    
    return jsonify({
        'symbol': symbol,
        'price': closes[-1],
        'signal': signal,
        'score': score,
        'reasons': reasons,
        'indicators': ind
    })

# === TOP股票推荐 ===
@app.route('/api/top-stocks')
def top_stocks():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 50, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f2,f3,f4,f5,f6"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = data.get("data", {}).get("diff", [])[:30]
    except:
        stocks = []
    
    candidates = []
    
    for stock in stocks:
        try:
            code = stock['f12']
            klines = get_klines(code, 60)
            if not klines or len(klines) < 30:
                continue
            
            ind = calculate_all(klines)
            signal, score, reasons = comprehensive_score(ind)
            closes = [float(k.split(',')[2]) for k in klines]
            
            candidates.append({
                'code': code,
                'name': stock.get('f14', ''),
                'price': closes[-1],
                'change': stock.get('f3', 0),
                'signal': signal,
                'score': score,
                'reasons': reasons[:3]
            })
        except:
            continue
    
    candidates.sort(key=lambda x: -x['score'])
    return jsonify(candidates[:15])

# === 涨停模式分析 ===
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
    
    for stock in stocks:
        try:
            code = stock['f12']
            klines = get_klines(code, 60)
            if klines and len(klines) >= 30:
                ind = calculate_all(klines)
                signal, score, reasons = comprehensive_score(ind)
                stats[signal] = stats.get(signal, 0) + 1
        except:
            pass
    
    return jsonify(stats)
