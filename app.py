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

def calc_all(klines):
    """计算所有技术指标"""
    closes = [float(k.split(',')[2]) for k in klines]
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    volumes = [float(k.split(',')[5]) for k in klines]
    
    ind = {}
    
    # WR指标 (短期14天)
    h14, l14 = max(highs[-14:]), min(lows[-14:])
    ind['wr_14'] = 100 * (closes[-1] - l14) / (h14 - l14) if h14 != l14 else 50
    
    # MA均线
    ind['ma5'] = sum(closes[-5:]) / 5
    ind['ma10'] = sum(closes[-10:]) / 10
    ind['ma20'] = sum(closes[-20:]) / 20
    ind['ma30'] = sum(closes[-30:]) / 30 if len(closes) >= 30 else ind['ma20']
    
    # 均线形态
    ind['ma多头'] = 1 if ind['ma5'] > ind['ma10'] > ind['ma20'] else 0
    ind['ma空头'] = 1 if ind['ma5'] < ind['ma10'] < ind['ma20'] else 0
    ind['ma死叉'] = 1 if ind['ma5'] < ind['ma10'] and closes[-1] < ind['ma5'] else 0
    
    # 资金流向
    v5 = sum(volumes[-5:]) / 5
    change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0
    ind['放量'] = volumes[-1] / v5 if v5 > 0 else 1
    ind['资金流入'] = 1 if ind['放量'] > 1.3 and change > 0 else 0
    ind['资金流出'] = 1 if ind['放量'] > 1.5 and change < -2 else 0
    
    # 位置判断
    high20 = max(highs[-20:])
    low20 = min(lows[-20:])
    ind['接近新高'] = 1 if closes[-1] >= high20 * 0.95 else 0
    ind['接近新低'] = 1 if closes[-1] <= low20 * 1.05 else 0
    
    # 涨跌幅
    ind['change'] = change
    ind['涨幅较大'] = 1 if change > 7 else 0
    ind['跌幅较大'] = 1 if change < -5 else 0
    
    # 连续上涨/下跌
    ind['连续上涨'] = 1 if len(closes) >= 3 and closes[-1] > closes[-2] > closes[-3] else 0
    ind['连续下跌'] = 1 if len(closes) >= 3 and closes[-1] < closes[-2] < closes[-3] else 0
    
    return ind

def score_stock(ind):
    """综合评分 - 返回(信号, 分数, 原因)"""
    score = 0
    reasons = []
    
    # 均线系统 (+25分)
    if ind.get('ma多头'):
        score += 25
        reasons.append("均线多头排列")
    if ind.get('ma空头'):
        score -= 20
        reasons.append("均线空头排列 ⚠️")
    if ind.get('ma死叉'):
        score -= 15
        reasons.append("均线死叉 ⚠️")
    
    # WR指标 (+15分)
    if ind.get('wr_14', 50) <= 20:  # 超卖
        score += 15
        reasons.append("WR超卖反弹")
    elif ind.get('wr_14', 50) >= 80:  # 超买
        score -= 10
        reasons.append("WR超买风险")
    
    # 资金流向 (+20分)
    if ind.get('资金流入'):
        score += 20
        reasons.append("资金流入")
    if ind.get('资金流出'):
        score -= 15
        reasons.append("资金流出 ⚠️")
    
    # 位置 (+15分)
    if ind.get('接近新高'):
        score += 15
        reasons.append("接近新高")
    if ind.get('接近新低'):
        score += 10
        reasons.append("超跌反弹")
    
    # 涨跌幅 (+10分)
    if ind.get('涨幅较大'):
        score -= 5
        reasons.append("涨幅较大注意风险")
    if ind.get('跌幅较大') and ind.get('资金流入'):
        score += 10
        reasons.append("超跌反弹")
    
    # 连续性 (+5分)
    if ind.get('连续下跌') and ind.get('资金流入'):
        score += 10
        reasons.append("连续下跌后资金流入")
    if ind.get('连续上涨'):
        score -= 5
        reasons.append("连续上涨注意回调")
    
    # 信号判断
    if score >= 35:
        signal = "强烈买入"
    elif score >= 20:
        signal = "买入"
    elif score >= 10:
        signal = "加仓"
    elif score >= 0:
        signal = "观望"
    elif score >= -10:
        signal = "减仓"
    else:
        signal = "清仓"
    
    return signal, score, reasons

@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_klines(symbol)
    if not klines or len(klines) < 20:
        return jsonify({'error': '无数据'})
    
    try:
        ind = calc_all(klines)
        signal, score, reasons = score_stock(ind)
        
        return jsonify({
            'symbol': symbol,
            'price': float(klines[-1].split(',')[2]),
            'change': ind['change'],
            'signal': signal,
            'score': score,
            'reasons': reasons,
            'wr': ind.get('wr_14', 0),
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
            if klines and len(klines) >= 20:
                ind = calc_all(klines)
                signal, score, reasons = score_stock(ind)
                results.append({
                    'code': code,
                    'name': s.get('f14', ''),
                    'price': float(klines[-1].split(',')[2]),
                    'change': s.get('f3', 0),
                    'signal': signal,
                    'score': score,
                    'reasons': reasons[:8]
                })
        except:
            continue
    
    results.sort(key=lambda x: -x['score'])
    return jsonify(results[:8])

@app.route('/api/limitup-pattern')
def limitup():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 10, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:8]
    except:
        stocks = []
    
    stats = {"total": len(stocks), "强烈买入": 0, "买入": 0, "加仓": 0, "观望": 0, "减仓": 0, "清仓": 0}
    
    for s in stocks:
        try:
            klines = get_klines(s['f12'])
            if klines and len(klines) >= 20:
                ind = calc_all(klines)
                signal, score, reasons = score_stock(ind)
                stats[signal] = stats.get(signal, 0) + 1
        except:
            continue
    
    return jsonify(stats)

@app.route('/api/scan-all')
def scan_all():
    """扫描所有A股，返回各信号统计"""
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
            if klines and len(klines) >= 20:
                ind = calc_all(klines)
                signal, score, reasons = score_stock(ind)
                results[signal].append({
                    'code': code,
                    'name': s.get('f14', ''),
                    'price': float(klines[-1].split(',')[2]),
                    'change': s.get('f3', 0),
                    'score': score
                })
        except:
            continue
    
    return jsonify(results)
