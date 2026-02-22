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
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            return data["data"]["klines"][-60:]
    except:
        pass
    return None

def calc_all(klines):
    """计算所有技术指标"""
    closes = [float(k.split(',')[2]) for k in klines]
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    volumes = [float(k.split(',')[5]) for k in klines]
    
    ind = {}
    
    # WR指标 (多周期)
    for n in [6, 10, 14]:
        h, l = max(highs[-n:]), min(lows[-n:])
        ind[f'wr_{n}'] = 100 * (closes[-1] - l) / (h - l) if h != l else 50
    
    # MA均线
    ind['ma5'] = sum(closes[-5:]) / 5
    ind['ma10'] = sum(closes[-10:]) / 10
    ind['ma20'] = sum(closes[-20:]) / 20
    ind['ma30'] = sum(closes[-30:]) / 30 if len(closes) >= 30 else ind['ma20']
    ind['ma60'] = sum(closes[-60:]) / 60 if len(closes) >= 60 else ind['ma30']
    
    # 均线形态
    ind['ma多头'] = 1 if ind['ma5'] > ind['ma10'] > ind['ma20'] > ind['ma30'] else 0
    ind['ma空头'] = 1 if ind['ma5'] < ind['ma10'] < ind['ma20'] else 0
    ind['ma金叉'] = 1 if ind['ma5'] > ind['ma10'] and closes[-1] > ind['ma5'] else 0
    ind['ma死叉'] = 1 if ind['ma5'] < ind['ma10'] and closes[-1] < ind['ma5'] else 0
    
    # 资金流向
    v5 = sum(volumes[-5:]) / 5
    v10 = sum(volumes[-10:]) / 10
    change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0
    
    ind['放量'] = volumes[-1] / v5 if v5 > 0 else 1
    ind['缩量'] = 1 if volumes[-1] < v5 * 0.7 else 0
    ind['资金流入'] = 1 if ind['放量'] > 1.3 and change > 0 else 0
    ind['资金大幅流入'] = 1 if ind['放量'] > 1.8 and change > 3 else 0
    ind['资金流出'] = 1 if ind['放量'] > 1.5 and change < -2 else 0
    ind['资金大幅流出'] = 1 if ind['放量'] > 2 and change < -5 else 0
    
    # 位置判断
    high20 = max(highs[-20:])
    high60 = max(highs[-60:]) if len(highs) >= 60 else high20
    low20 = min(lows[-20:])
    
    ind['接近新高'] = 1 if closes[-1] >= high20 * 0.95 else 0
    ind['突破新高'] = 1 if closes[-1] > high20 else 0
    ind['接近新低'] = 1 if closes[-1] <= low20 * 1.1 else 0
    ind['年内新高'] = 1 if closes[-1] >= high60 * 0.98 else 0
    
    # 涨跌幅
    ind['change'] = change
    ind['涨幅较大'] = 1 if change > 7 else 0
    ind['跌幅较大'] = 1 if change < -5 else 0
    ind['涨停'] = 1 if change >= 9.9 else 0
    
    # 连续性
    ind['连续上涨'] = 1 if len(closes) >= 3 and closes[-1] > closes[-2] > closes[-3] else 0
    ind['连续下跌'] = 1 if len(closes) >= 3 and closes[-1] < closes[-2] < closes[-3] else 0
    ind['上涨中继'] = 1 if ind['连续上涨'] == 0 and ind['资金流入'] and change > 0 and change < 5 else 0
    
    # RSI
    if len(closes) >= 14:
        delta = [closes[i] - closes[i-1] for i in range(1, 14)]
        gain = [d if d > 0 else 0 for d in delta]
        loss = [-d if d < 0 else 0 for d in delta]
        avg_gain = sum(gain) / 14
        avg_loss = sum(loss) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        ind['rsi'] = 100 - (100 / (1 + rs))
        ind['rsi超卖'] = 1 if ind['rsi'] < 30 else 0
        ind['rsi超买'] = 1 if ind['rsi'] > 70 else 0
    
    return ind

def score_stock_strict(ind):
    """严格评分系统 - 只有多重确认才给出强烈信号"""
    score = 0
    reasons = []
    confidence = 0  # 置信度
    
    # === 均线系统 (+30分) ===
    if ind.get('ma多头') and ind.get('ma金叉'):
        score += 30
        confidence += 2
        reasons.append("均线多头+金叉")
    elif ind.get('ma多头'):
        score += 20
        confidence += 1
        reasons.append("均线多头排列")
    
    if ind.get('ma空头'):
        score -= 25
        confidence += 2
        reasons.append("均线空头 ⚠️")
    if ind.get('ma死叉'):
        score -= 15
        confidence += 1
        reasons.append("均线死叉 ⚠️")
    
    # === WR指标 (+15分) ===
    wr_14 = ind.get('wr_14', 50)
    wr_10 = ind.get('wr_10', 50)
    wr_6 = ind.get('wr_6', 50)
    
    if wr_14 <= 15 and wr_10 <= 20:  # 多周期超卖
        score += 15
        confidence += 2
        reasons.append("WR多周期超卖")
    elif wr_14 <= 20:
        score += 10
        confidence += 1
        reasons.append("WR超卖")
    
    if wr_14 >= 85:
        score -= 10
        confidence += 1
        reasons.append("WR超买 ⚠️")
    
    # === 资金流向 (+25分) ===
    if ind.get('资金大幅流入'):
        score += 25
        confidence += 3
        reasons.append("资金大幅流入")
    elif ind.get('资金流入'):
        score += 15
        confidence += 1
        reasons.append("资金流入")
    
    if ind.get('资金大幅流出'):
        score -= 20
        confidence += 2
        reasons.append("资金大幅流出 ⚠️")
    elif ind.get('资金流出'):
        score -= 10
        confidence += 1
        reasons.append("资金流出 ⚠️")
    
    # === 位置 (+20分) ===
    if ind.get('突破新高') and ind.get('资金流入'):
        score += 20
        confidence += 3
        reasons.append("突破新高+资金确认")
    elif ind.get('年内新高'):
        score += 15
        confidence += 2
        reasons.append("接近年内新高")
    elif ind.get('接近新高') and ind.get('资金流入'):
        score += 15
        confidence += 2
        reasons.append("接近新高+资金流入")
    
    if ind.get('接近新低') and ind.get('资金流入'):
        score += 15
        confidence += 2
        reasons.append("超跌反弹")
    
    # === RSI (+10分) ===
    if ind.get('rsi超卖'):
        score += 10
        confidence += 1
        reasons.append("RSI超卖")
    elif ind.get('rsi超买'):
        score -= 5
        reasons.append("RSI超买")
    
    # === 涨跌幅调整 ===
    if ind.get('涨幅较大') and not ind.get('资金大幅流入'):
        score -= 10
        reasons.append("放量不涨注意风险")
    
    if ind.get('连续下跌') and ind.get('资金流入'):
        score += 10
        reasons.append("连续下跌后资金入场")
    
    # === 严格信号判断 ===
    # 只有置信度>=3且分数>=25才是强烈买入
    if score >= 35 and confidence >= 3:
        signal = "强烈买入"
    elif score >= 25 and confidence >= 2:
        signal = "买入"
    elif score >= 15:
        signal = "加仓"
    elif score >= 0:
        signal = "观望"
    elif score >= -10:
        signal = "减仓"
    else:
        signal = "清仓"
    
    return signal, score, reasons, confidence

@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_klines(symbol)
    if not klines or len(klines) < 30:
        return jsonify({'error': '无数据'})
    
    try:
        ind = calc_all(klines)
        signal, score, reasons, confidence = score_stock_strict(ind)
        
        return jsonify({
            'symbol': symbol,
            'price': float(klines[-1].split(',')[2]),
            'change': ind['change'],
            'signal': signal,
            'score': score,
            'confidence': confidence,
            'reasons': reasons,
            'wr': ind.get('wr_14', 0),
            'rsi': ind.get('rsi', 0),
            'ma': '多头' if ind.get('ma多头') else '空头' if ind.get('ma空头') else '震荡'
        })
    except:
        return jsonify({'error': '计算错误'})

@app.route('/api/top-stocks')
def top_stocks():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 10, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f2,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = data.get("data", {}).get("diff", [])[:8]
    except:
        stocks = []
    
    results = []
    for s in stocks:
        try:
            code = s['f12']
            klines = get_klines(code)
            if klines and len(klines) >= 30:
                ind = calc_all(klines)
                signal, score, reasons, confidence = score_stock_strict(ind)
                results.append({
                    'code': code,
                    'name': s.get('f14', ''),
                    'price': float(klines[-1].split(',')[2]),
                    'change': s.get('f3', 0),
                    'signal': signal,
                    'score': score,
                    'confidence': confidence,
                    'reasons': reasons[:3]
                })
        except:
            continue
    
    results.sort(key=lambda x: (-x['score'], -x['confidence']))
    return jsonify(results[:6])

@app.route('/api/limitup-pattern')
def limitup():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 10, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:10]
    except:
        stocks = []
    
    stats = {"total": len(stocks), "强烈买入": 0, "买入": 0, "加仓": 0, "观望": 0, "减仓": 0, "清仓": 0}
    
    for s in stocks:
        try:
            klines = get_klines(s['f12'])
            if klines and len(klines) >= 30:
                ind = calc_all(klines)
                signal, score, reasons, confidence = score_stock_strict(ind)
                stats[signal] = stats.get(signal, 0) + 1
        except:
            continue
    
    return jsonify(stats)

@app.route('/api/scan-all')
def scan_all():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 10, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f2,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = data.get("data", {}).get("diff", [])[:8]
    except:
        stocks = []
    
    results = {"强烈买入": [], "买入": [], "加仓": [], "观望": [], "减仓": [], "清仓": []}
    
    for s in stocks:
        try:
            code = s['f12']
            klines = get_klines(code)
            if klines and len(klines) >= 30:
                ind = calc_all(klines)
                signal, score, reasons, confidence = score_stock_strict(ind)
                results[signal].append({
                    'code': code,
                    'name': s.get('f14', ''),
                    'price': float(klines[-1].split(',')[2]),
                    'change': s.get('f3', 0),
                    'score': score,
                    'confidence': confidence
                })
        except:
            continue
    
    return jsonify(results)
