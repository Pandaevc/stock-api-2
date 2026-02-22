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
        params = {"secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "klt": 101, "fqt": 0, "beg": "20240101", "end": "20260222", "lmt": 120}
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            return data["data"]["klines"][-120:]
    except:
        pass
    return None

def calc_all(klines):
    closes = [float(k.split(',')[2]) for k in klines]
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    volumes = [float(k.split(',')[5]) for k in klines]
    opens = [float(k.split(',')[1]) for k in klines]
    
    ind = {}
    
    # WR
    for n in [6, 10, 14, 20]:
        h, l = max(highs[-n:]), min(lows[-n:])
        ind[f'wr_{n}'] = 100 * (closes[-1] - l) / (h - l) if h != l else 50
    
    # MA
    for n in [5, 10, 20, 30, 60]:
        ind[f'ma{n}'] = sum(closes[-n:]) / n
    
    ind['ma多头'] = 1 if ind['ma5'] > ind['ma10'] > ind['ma20'] > ind['ma30'] else 0
    ind['ma空头'] = 1 if ind['ma5'] < ind['ma10'] < ind['ma20'] else 0
    ind['ma金叉'] = 1 if ind['ma5'] > ind['ma10'] and ind['ma10'] > ind['ma20'] else 0
    ind['ma死叉'] = 1 if ind['ma5'] < ind['ma10'] and ind['ma10'] < ind['ma20'] else 0
    ind['ma多头金叉'] = 1 if ind['ma多头'] and ind['ma金叉'] else 0
    
    # 资金
    v5 = sum(volumes[-5:]) / 5
    v10 = sum(volumes[-10:]) / 10
    change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0
    
    ind['放量'] = volumes[-1] / v5 if v5 > 0 else 1
    ind['资金流入'] = 1 if ind['放量'] > 1.3 and change > 0 else 0
    ind['资金大幅流入'] = 1 if ind['放量'] > 1.8 and change > 3 else 0
    ind['资金持续流入'] = 1 if ind['资金流入'] and v5 > v10 else 0
    ind['资金流出'] = 1 if ind['放量'] > 1.5 and change < -2 else 0
    ind['资金大幅流出'] = 1 if ind['放量'] > 2 and change < -5 else 0
    
    # 位置
    high20 = max(highs[-20:])
    high60 = max(highs[-60:]) if len(highs) >= 60 else high20
    low20 = min(lows[-20:])
    
    ind['接近新高'] = 1 if closes[-1] >= high20 * 0.95 else 0
    ind['突破新高'] = 1 if closes[-1] > high20 else 0
    ind['年内新高'] = 1 if closes[-1] >= high60 * 0.98 else 0
    ind['接近新低'] = 1 if closes[-1] <= low20 * 1.1 else 0
    
    # 涨跌幅
    ind['change'] = change
    ind['涨幅较大'] = 1 if change > 7 else 0
    ind['跌幅较大'] = 1 if change < -5 else 0
    
    # RSI
    if len(closes) >= 14:
        delta = [closes[i] - closes[i-1] for i in range(1, 14)]
        gain = [d if d > 0 else 0 for d in delta]
        loss = [-d if d < 0 else 0 for d in delta]
        avg_gain = sum(gain) / 14
        avg_loss = sum(loss) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        ind['rsi'] = 100 - (100 / (1 + rs))
        ind['rsi超卖'] = 1 if ind['rsi'] < 25 else 0
        ind['rsi超买'] = 1 if ind['rsi'] > 75 else 0
    
    # CCI
    if len(closes) >= 14:
        tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(-14, 0)]
        tp_avg = sum(tp) / 14
        tp_dev = sum(abs(t - tp_avg) for t in tp) / 14
        ind['cci'] = (tp[-1] - tp_avg) / (0.015 * tp_dev) if tp_dev > 0 else 0
        ind['cci超卖'] = 1 if ind['cci'] < -100 else 0
        ind['cci超买'] = 1 if ind['cci'] > 100 else 0
    
    # 量价
    ind['量价齐升'] = 1 if ind['放量'] > 1.3 and change > 1 else 0
    ind['放量滞涨'] = 1 if ind['放量'] > 1.5 and change < 0 else 0
    
    # 趋势
    ma5_angle = (ind['ma5'] - ind['ma10']) / ind['ma10'] * 100
    ma10_angle = (ind['ma10'] - ind['ma20']) / ind['ma20'] * 100
    ind['上升趋势'] = 1 if ma5_angle > 0.5 and ma10_angle > 0.3 else 0
    ind['下降趋势'] = 1 if ma5_angle < -0.5 and ma10_angle < -0.3 else 0
    
    return ind

def score_stock_strict(ind):
    """超级严格评分系统 - 只给多重确认的强烈信号"""
    score = 0
    reasons = []
    confidence = 0
    
    # ==================== 强烈买入条件（必须全部满足）================
    strong_buy_count = 0  # 强烈信号计数
    
    # 1. 均线多头+金叉 (必须)
    if ind.get('ma多头金叉'):
        strong_buy_count += 1
        score += 30
        reasons.append("均线多头+金叉 ✅")
    
    # 2. 资金持续流入 (必须)
    if ind.get('资金持续流入') or ind.get('资金大幅流入'):
        strong_buy_count += 1
        score += 25
        reasons.append("资金大幅流入 ✅")
    
    # 3. WR超卖 (必须)
    wr_vals = [ind.get(f'wr_{n}', 50) for n in [6, 10, 14, 20]]
    wr_below = sum(1 for w in wr_vals if w <= 20)
    if wr_below >= 2:
        strong_buy_count += 1
        score += 15
        reasons.append("WR多周期超卖 ✅")
    
    # 4. 位置有利 (必须)
    if ind.get('突破新高') or ind.get('年内新高'):
        strong_buy_count += 1
        score += 20
        reasons.append("突破/年内新高 ✅")
    
    # ==================== 加分项 ====================
    
    # CCI超卖反弹
    if ind.get('cci超卖'):
        score += 10
        confidence += 1
        reasons.append("CCI超卖")
    
    # RSI超卖+资金
    if ind.get('rsi超卖') and ind.get('资金流入'):
        score += 10
        confidence += 1
        reasons.append("RSI超卖+资金")
    
    # 量价齐升
    if ind.get('量价齐升'):
        score += 10
        confidence += 1
        reasons.append("量价齐升")
    
    # 上升趋势
    if ind.get('上升趋势'):
        score += 5
        reasons.append("上升趋势")
    
    # ==================== 减分项 ====================
    
    # 均线问题
    if ind.get('ma空头'):
        score -= 30; confidence += 3
        reasons.append("均线空头 ⚠️")
    elif ind.get('ma死叉'):
        score -= 15; confidence += 2
        reasons.append("均线死叉 ⚠️")
    
    # 资金问题
    if ind.get('资金大幅流出'):
        score -= 25; confidence += 3
        reasons.append("资金大幅流出 ⚠️")
    elif ind.get('资金流出'):
        score -= 15; confidence += 2
        reasons.append("资金流出 ⚠️")
    
    # WR超买
    wr_above = sum(1 for w in wr_vals if w >= 80)
    if wr_above >= 2:
        score -= 15; confidence += 2
        reasons.append("WR超买 ⚠️")
    
    # CCI超买
    if ind.get('cci超买'):
        score -= 10; confidence += 1
        reasons.append("CCI超买 ⚠️")
    
    # RSI超买
    if ind.get('rsi超买'):
        score -= 10; confidence += 1
        reasons.append("RSI超买 ⚠️")
    
    # 量价背离
    if ind.get('放量滞涨'):
        score -= 15; confidence += 2
        reasons.append("放量滞涨 ⚠️")
    
    # 下降趋势
    if ind.get('下降趋势'):
        score -= 10; confidence += 2
        reasons.append("下降趋势 ⚠️")
    
    # ==================== 信号判断 ====================
    # 强烈买入：必须满足4个必须条件
    if strong_buy_count >= 4:
        signal = "强烈买入"
    elif strong_buy_count >= 3 and score >= 30:
        signal = "强烈买入"
    elif strong_buy_count >= 2 and score >= 25:
        signal = "买入"
    elif score >= 15 and ind.get('资金流入'):
        signal = "加仓"
    elif score >= 5:
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
            'reasons': reasons[:5],
            'wr': round(ind.get('wr_14', 0), 1),
            'rsi': round(ind.get('rsi', 0), 1),
            'cci': round(ind.get('cci', 0), 1),
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
