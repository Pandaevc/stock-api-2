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

def calculate_wr(klines):
    """计算威廉指标 - 机构算法 (0-100范围)"""
    if len(klines) < 30:
        return None
    
    closes = [float(k.split(',')[2]) for k in klines]
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    
    n1, n2 = 14, 28
    
    # 短期WR (0-100范围)
    highest_high = max(highs[-n1:])
    lowest_low = min(lows[-n1:])
    wr_short = 100 * (closes[-1] - lowest_low) / (highest_high - lowest_low) if highest_high != lowest_low else 50
    
    # 中期WR (10日)
    highest_high_mid = max(highs[-10:])
    lowest_low_mid = min(lows[-10:])
    wr_mid = 100 * (closes[-1] - lowest_low_mid) / (highest_high_mid - lowest_low_mid) if highest_high_mid != lowest_low_mid else 50
    
    # 中长期WR (20日)
    highest_high_long = max(highs[-20:])
    lowest_low_long = min(lows[-20:])
    wr_long_mid = 100 * (closes[-1] - lowest_low_long) / (highest_high_long - lowest_low_long) if highest_high_long != lowest_low_long else 50
    
    # 长期WR (28日)
    highest_high_extra = max(highs[-n2:])
    lowest_low_extra = min(lows[-n2:])
    wr_long = 100 * (closes[-1] - lowest_low_extra) / (highest_high_extra - lowest_low_extra) if highest_high_extra != lowest_low_extra else 50
    
    return {
        'wr_short': wr_short,
        'wr_mid': wr_mid,
        'wr_long_mid': wr_long_mid,
        'wr_long': wr_long
    }

def calculate_ma(klines):
    """计算均线"""
    if len(klines) < 20:
        return None
    closes = [float(k.split(',')[2]) for k in klines]
    return {
        'ma5': sum(closes[-5:]) / 5,
        'ma10': sum(closes[-10:]) / 10,
        'ma20': sum(closes[-20:]) / 20
    }

def calculate_cci(klines):
    """计算CCI"""
    if len(klines) < 14:
        return None
    highs = [float(k.split(',')[3]) for k in klines]
    lows = [float(k.split(',')[4]) for k in klines]
    closes = [float(k.split(',')[2]) for k in klines]
    
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(-14, 0)]
    tp_avg = sum(tp) / 14
    tp_dev = sum(abs(t - tp_avg) for t in tp) / 14
    cci = (tp[-1] - tp_avg) / (0.015 * tp_dev) if tp_dev > 0 else 0
    return cci

def get_buy_signals(klines):
    """根据机构算法获取买入信号"""
    wr = calculate_wr(klines)
    ma = calculate_ma(klines)
    cci = calculate_cci(klines)
    
    if not wr:
        return {"signals": [], "score": 0, "recommend": "观望"}
    
    signals = []
    score = 0
    
    # 四线归零买 (WR all <= 6)
    if wr['wr_short'] <= 6 and wr['wr_mid'] <= 6 and wr['wr_long_mid'] <= 6 and wr['wr_long'] <= 6:
        signals.append("四线归零买")
        score += 10
    
    # 白线下20买 (WR短<=20 AND WR长>=60)
    if wr['wr_short'] <= 20 and wr['wr_long'] >= 60:
        signals.append("白线下20买")
        score += 8
    
    # 白穿红线买 (短期上穿长期且长期<20)
    if wr['wr_short'] > wr['wr_long'] and wr['wr_long'] < 20 and wr['wr_short'] <= 80:
        signals.append("白穿红线买")
        score += 7
    
    # 白穿黄线买 (短期上穿中期且中期<30)
    if wr['wr_short'] > wr['wr_mid'] and wr['wr_mid'] < 30 and wr['wr_short'] <= 80:
        signals.append("白穿黄线买")
        score += 5
    
    # CCI超卖反弹
    if cci and cci < -100:
        signals.append("CCI超卖反弹")
        score += 3
    
    # 均线多头排列
    if ma and ma['ma5'] > ma['ma10'] > ma['ma20']:
        signals.append("均线多头")
        score += 3
    
    # 推荐
    if score >= 8:
        recommend = "买入"
    elif score >= 4:
        recommend = "加仓"
    else:
        recommend = "观望"
    
    return {
        "signals": signals,
        "score": score,
        "recommend": recommend,
        "wr": wr,
        "cci": cci
    }

# === 威廉指标分析 ===
@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_klines(symbol, 60)
    if not klines:
        return jsonify({'error': '无法获取数据'})
    
    signals = get_buy_signals(klines)
    return jsonify({
        'symbol': symbol,
        'price': float(klines[-1].split(',')[2]),
        'signals': signals
    })

# === 涨停股模式分析 - 大规模测试 ===
@app.route('/api/limitup-pattern')
def limitup():
    try:
        # 获取更多涨停股
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 200, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:30]  # 增加到100只
    except:
        stocks = []
    
    # 统计各指标
    stats = {
        'four_line_zero': 0,  # 四线归零
        'white_under_20': 0,   # 白线下20
        'white_cross_red': 0, # 白穿红线
        'white_cross_yellow': 0, # 白穿黄线
        'cci_oversold': 0,    # CCI超卖
        'ma_golden': 0,       # 均线多头
        'total': 0
    }
    
    for stock in stocks:
        try:
            code = stock['f12']
            market = "1" if stock.get('f13') == 1 else "0"
            klines = get_klines(code, 60)
            
            if klines and len(klines) >= 30:
                signals = get_buy_signals(klines)
                sig_list = signals.get('signals', [])
                
                if "四线归零买" in sig_list: stats['four_line_zero'] += 1
                if "白线下20买" in sig_list: stats['white_under_20'] += 1
                if "白穿红线买" in sig_list: stats['white_cross_red'] += 1
                if "白穿黄线买" in sig_list: stats['white_cross_yellow'] += 1
                if "CCI超卖反弹" in sig_list: stats['cci_oversold'] += 1
                if "均线多头" in sig_list: stats['ma_golden'] += 1
                
                stats['total'] += 1
        except:
            pass
    
    # 计算百分比
    t = stats['total']
    result = {
        'total': t,
        'four_line_zero': stats['four_line_zero'],
        'four_line_zero_pct': round(stats['four_line_zero']/t*100, 1) if t else 0,
        'white_under_20': stats['white_under_20'],
        'white_under_20_pct': round(stats['white_under_20']/t*100, 1) if t else 0,
        'white_cross_red': stats['white_cross_red'],
        'white_cross_red_pct': round(stats['white_cross_red']/t*100, 1) if t else 0,
        'white_cross_yellow': stats['white_cross_yellow'],
        'white_cross_yellow_pct': round(stats['white_cross_yellow']/t*100, 1) if t else 0,
        'cci_oversold': stats['cci_oversold'],
        'cci_oversold_pct': round(stats['cci_oversold']/t*100, 1) if t else 0,
        'ma_golden': stats['ma_golden'],
        'ma_golden_pct': round(stats['ma_golden']/t*100, 1) if t else 0
    }
    
    return jsonify(result)
