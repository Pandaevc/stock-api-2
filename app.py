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
    """计算所有技术指标"""
    closes = [float(k.split(',')[2]) for k in klines]
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    volumes = [float(k.split(',')[5]) for k in klines]
    opens = [float(k.split(',')[1]) for k in klines]
    
    ind = {}
    
    # WR指标 (多周期)
    for n in [6, 10, 14, 20]:
        h, l = max(highs[-n:]), min(lows[-n:])
        ind[f'wr_{n}'] = 100 * (closes[-1] - l) / (h - l) if h != l else 50
    
    # MA均线
    for n in [5, 10, 20, 30, 60, 120]:
        ind[f'ma{n}'] = sum(closes[-n:]) / n
    
    # 均线形态
    ind['ma多头'] = 1 if ind['ma5'] > ind['ma10'] > ind['ma20'] > ind['ma30'] else 0
    ind['ma空头'] = 1 if ind['ma5'] < ind['ma10'] < ind['ma20'] else 0
    ind['ma金叉'] = 1 if ind['ma5'] > ind['ma10'] and ind['ma10'] > ind['ma20'] else 0
    ind['ma死叉'] = 1 if ind['ma5'] < ind['ma10'] and ind['ma10'] < ind['ma20'] else 0
    ind['ma多头金叉'] = 1 if ind['ma多头'] and ind['ma金叉'] else 0
    ind['价格站上ma5'] = 1 if closes[-1] > ind['ma5'] else 0
    ind['价格站上ma20'] = 1 if closes[-1] > ind['ma20'] else 0
    ind['价格跌破ma5'] = 1 if closes[-1] < ind['ma5'] else 0
    ind['价格跌破ma20'] = 1 if closes[-1] < ind['ma20'] else 0
    
    # 资金流向
    v5 = sum(volumes[-5:]) / 5
    v10 = sum(volumes[-10:]) / 10
    v20 = sum(volumes[-20:]) / 20
    change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0
    
    ind['放量'] = volumes[-1] / v5 if v5 > 0 else 1
    ind['缩量'] = 1 if volumes[-1] < v5 * 0.5 else 0
    ind['资金流入'] = 1 if ind['放量'] > 1.3 and change > 0 else 0
    ind['资金大幅流入'] = 1 if ind['放量'] > 1.8 and change > 3 else 0
    ind['资金持续流入'] = 1 if ind['资金流入'] and v5 > v10 else 0
    ind['资金流出'] = 1 if ind['放量'] > 1.5 and change < -2 else 0
    ind['资金大幅流出'] = 1 if ind['放量'] > 2 and change < -5 else 0
    
    # 位置判断
    high20 = max(highs[-20:])
    high60 = max(highs[-60:]) if len(highs) >= 60 else high20
    high120 = max(highs[-120:]) if len(highs) >= 120 else high60
    low20 = min(lows[-20:])
    low60 = min(lows[-60:]) if len(lows) >= 60 else low20
    
    ind['接近新高'] = 1 if closes[-1] >= high20 * 0.95 else 0
    ind['突破新高'] = 1 if closes[-1] > high20 else 0
    ind['年内新高'] = 1 if closes[-1] >= high60 * 0.98 else 0
    ind['历史新高'] = 1 if closes[-1] >= high120 * 0.99 else 0
    ind['接近新低'] = 1 if closes[-1] <= low20 * 1.1 else 0
    ind['跌破新低'] = 1 if closes[-1] < low20 else 0
    
    # 压力位/支撑位
    ind['上方有压力'] = 1 if closes[-1] < high20 * 0.85 else 0
    ind['下方有支撑'] = 1 if closes[-1] > low20 * 1.2 else 0
    
    # 涨跌幅
    ind['change'] = change
    ind['涨幅较大'] = 1 if change > 7 else 0
    ind['跌幅较大'] = 1 if change < -5 else 0
    ind['涨停'] = 1 if change >= 9.9 else 0
    ind['跌停'] = 1 if change <= -9.9 else 0
    
    # 连续性
    ind['连续上涨'] = 1 if len(closes) >= 3 and closes[-1] > closes[-2] > closes[-3] else 0
    ind['连续下跌'] = 1 if len(closes) >= 3 and closes[-1] < closes[-2] < closes[-3] else 0
    ind['上涨中继'] = 1 if ind['连续上涨'] == 0 and ind['资金流入'] and 0 < change < 5 else 0
    
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
    
    # 量价配合
    ind['量价齐升'] = 1 if ind['放量'] > 1.3 and change > 1 else 0
    ind['放量滞涨'] = 1 if ind['放量'] > 1.5 and change < 0 else 0
    ind['缩量企稳'] = 1 if ind['缩量'] and abs(change) < 2 else 0
    ind['放量下跌'] = 1 if ind['放量'] > 1.5 and change < -2 else 0
    
    # 趋势
    ma5_angle = (ind['ma5'] - ind['ma10']) / ind['ma10'] * 100
    ma10_angle = (ind['ma10'] - ind['ma20']) / ind['ma20'] * 100
    ind['上升趋势'] = 1 if ma5_angle > 0.5 and ma10_angle > 0.3 else 0
    ind['下降趋势'] = 1 if ma5_angle < -0.5 and ma10_angle < -0.3 else 0
    
    # K线形态
    if len(klines) >= 2:
        last_c = closes[-1]
        last_o = opens[-1]
        last_h = highs[-1]
        last_l = lows[-1]
        
        # 锤子线
        ind['锤子线'] = 1 if (last_c > last_o) and (last_c - last_o) < (last_h - last_l) * 0.3 and (last_o - last_l) > (last_h - last_l) * 0.6 else 0
        # 上吊线
        ind['上吊线'] = 1 if (last_c < last_o) and (last_o - last_c) < (last_h - last_l) * 0.3 and (last_c - last_l) > (last_h - last_l) * 0.6 else 0
        # 吞没
        ind['看涨吞没'] = 1 if len(closes) >= 2 and closes[-2] < opens[-2] and last_c > opens[-2] and last_o < closes[-2] else 0
        # 射击之星
        ind['射击之星'] = 1 if (last_c < last_o) and (last_o - last_c) < (last_h - last_l) * 0.3 and (last_h - last_o) > (last_h - last_l) * 0.6 else 0
    
    return ind

def score_stock_strict(ind):
    """完整评分系统 - 加分项和减分项"""
    score = 0
    reasons = []
    confidence = 0
    
    # ==================== 加分项 ====================
    
    # 均线系统 (+40分)
    if ind.get('ma多头金叉'):
        score += 40; confidence += 3
        reasons.append("均线多头+金叉")
    elif ind.get('ma多头'):
        score += 25; confidence += 2
        reasons.append("均线多头排列")
    elif ind.get('ma金叉'):
        score += 15; confidence += 1
        reasons.append("均线金叉")
    
    if ind.get('价格站上ma5') and ind.get('价格站上ma20'):
        score += 10; confidence += 1
        reasons.append("价格站稳均线")
    
    # WR指标 (+20分)
    wr_vals = [ind.get(f'wr_{n}', 50) for n in [6, 10, 14, 20]]
    wr_below_20 = sum(1 for w in wr_vals if w <= 20)
    wr_above_80 = sum(1 for w in wr_vals if w >= 80)
    
    if wr_below_20 >= 3:
        score += 20; confidence += 3
        reasons.append("WR多周期超卖")
    elif wr_below_20 >= 2:
        score += 15; confidence += 2
        reasons.append("WR双周期超卖")
    elif wr_below_20 >= 1:
        score += 8; confidence += 1
        reasons.append("WR超卖")
    
    # CCI (+15分)
    if ind.get('cci超卖'):
        score += 15; confidence += 2
        reasons.append("CCI超卖反弹")
    
    # RSI (+10分)
    if ind.get('rsi超卖') and ind.get('资金流入'):
        score += 10; confidence += 2
        reasons.append("RSI超卖+资金流入")
    elif ind.get('rsi超卖'):
        score += 5; confidence += 1
        reasons.append("RSI超卖")
    
    # 资金流向 (+35分) - 核心
    if ind.get('资金持续流入'):
        score += 35; confidence += 3
        reasons.append("资金持续流入")
    elif ind.get('资金大幅流入'):
        score += 30; confidence += 3
        reasons.append("资金大幅流入")
    elif ind.get('资金流入'):
        score += 15; confidence += 1
        reasons.append("资金流入")
    
    # 量价配合 (+15分)
    if ind.get('量价齐升'):
        score += 15; confidence += 2
        reasons.append("量价齐升")
    if ind.get('缩量企稳'):
        score += 10; confidence += 1
        reasons.append("缩量企稳")
    
    # 位置 (+30分)
    if ind.get('历史新高'):
        score += 30; confidence += 3
        reasons.append("创历史新高")
    elif ind.get('年内新高'):
        score += 25; confidence += 3
        reasons.append("年内新高")
    elif ind.get('突破新高') and ind.get('资金流入'):
        score += 25; confidence += 3
        reasons.append("突破新高+资金确认")
    elif ind.get('接近新高') and ind.get('资金流入'):
        score += 15; confidence += 2
        reasons.append("接近新高+资金流入")
    
    if ind.get('接近新低') and ind.get('资金流入'):
        score += 15; confidence += 2
        reasons.append("超跌反弹")
    
    # K线形态 (+15分)
    if ind.get('锤子线') or ind.get('看涨吞没'):
        score += 15; confidence += 2
        reasons.append("看涨K线形态")
    
    # 趋势 (+10分)
    if ind.get('上升趋势'):
        score += 10; confidence += 2
        reasons.append("上升趋势确认")
    
    # 连续性
    if ind.get('连续下跌') and ind.get('资金流入'):
        score += 15; confidence += 2
        reasons.append("连续下跌后资金入场")
    
    # 涨跌幅
    if ind.get('涨停') and ind.get('资金流入'):
        score += 10; reasons.append("涨停封板资金强")
    if ind.get('跌幅较大') and ind.get('资金流入'):
        score += 10; reasons.append("超跌反弹")
    
    # ==================== 减分项 ====================
    
    # 均线
    if ind.get('ma空头'):
        score -= 35; confidence += 3
        reasons.append("均线空头 ⚠️⚠️")
    elif ind.get('ma死叉'):
        score -= 20; confidence += 2
        reasons.append("均线死叉 ⚠️")
    
    if ind.get('价格跌破ma5') and ind.get('价格跌破ma20'):
        score -= 15; confidence += 2
        reasons.append("价格跌破均线 ⚠️")
    
    # WR超买
    if wr_above_80 >= 2:
        score -= 20; confidence += 2
        reasons.append("WR多周期超买 ⚠️")
    elif wr_above_80 >= 1:
        score -= 10; confidence += 1
        reasons.append("WR超买 ⚠️")
    
    # CCI超买
    if ind.get('cci超买'):
        score -= 15; confidence += 2
        reasons.append("CCI超买风险 ⚠️")
    
    # RSI超买
    if ind.get('rsi超买'):
        score -= 10; confidence += 1
        reasons.append("RSI超买 ⚠️")
    
    # 资金流出
    if ind.get('资金大幅流出'):
        score -= 30; confidence += 3
        reasons.append("资金大幅流出 ⚠️⚠️")
    elif ind.get('资金流出'):
        score -= 15; confidence += 2
        reasons.append("资金流出 ⚠️")
    
    # 量价背离
    if ind.get('放量滞涨'):
        score -= 20; confidence += 2
        reasons.append("放量滞涨 ⚠️")
    if ind.get('放量下跌'):
        score -= 15; confidence += 2
        reasons.append("放量下跌 ⚠️")
    
    # 位置风险
    if ind.get('上方有压力'):
        score -= 10; confidence += 1
        reasons.append("上方有压力 ⚠️")
    if ind.get('跌破新低'):
        score -= 20; confidence += 2
        reasons.append("跌破新低 ⚠️")
    
    # 趋势
    if ind.get('下降趋势'):
        score -= 15; confidence += 2
        reasons.append("下降趋势 ⚠️")
    
    # K线形态风险
    if ind.get('上吊线') or ind.get('射击之星'):
        score -= 10; confidence += 1
        reasons.append("反转K线 ⚠️")
    
    # 涨跌幅风险
    if ind.get('涨幅较大') and not ind.get('资金大幅流入'):
        score -= 10; reasons.append("涨幅较大风险 ⚠️")
    if ind.get('跌停') and not ind.get('资金流入'):
        score -= 15; reasons.append("跌停风险 ⚠️")
    
    if ind.get('连续上涨'):
        score -= 8; reasons.append("连续上涨注意回调 ⚠️")
    
    # ==================== 信号判断 ====================
    if score >= 50 and confidence >= 5:
        signal = "强烈买入"
    elif score >= 40 and confidence >= 4:
        signal = "强烈买入"
    elif score >= 25 and confidence >= 3:
        signal = "买入"
    elif score >= 15:
        signal = "加仓"
    elif score >= 0:
        signal = "观望"
    elif score >= -15:
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
