from flask import Flask, jsonify, request
import requests
import json
import os

app = Flask(__name__)

# 简单的内存存储（Vercel会重置，需要持久化）
# 使用GitHub Gist作为简单数据库
GIST_ID = None  # 需要创建一个GitHub Gist来存储数据

# 内存存储（临时）
db = {
    "portfolio": [],
    "picks": [],
    "settings": {}
}

def save_db():
    """保存到GitHub Gist"""
    global db
    if GIST_ID:
        try:
            url = f"https://api.github.com/gists/{GIST_ID}"
            data = {"description": "Stock DB", "public": False, "files": {"stock_db.json": {"content": json.dumps(db)}}}
            requests.patch(url, json=data, headers={"Authorization": f"token {os.environ.get('GITHUB_TOKEN', '')}"})
        except:
            pass

def load_db():
    """从GitHub Gist加载"""
    global db
    if GIST_ID:
        try:
            url = f"https://api.github.com/gists/{GIST_ID}"
            resp = requests.get(url)
            if resp.status_code == 200:
                db = json.loads(resp.json()["files"]["stock_db.json"]["content"])
        except:
            pass

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

# === 持仓管理 ===
@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    return jsonify(db.get("portfolio", []))

@app.route('/api/portfolio', methods=['POST'])
def add_portfolio():
    data = request.json
    db.setdefault("portfolio", []).append(data)
    save_db()
    return jsonify({"success": True})

@app.route('/api/portfolio/<code>', methods=['DELETE'])
def delete_portfolio(code):
    db["portfolio"] = [p for p in db.get("portfolio", []) if p.get("code") != code]
    save_db()
    return jsonify({"success": True})

# === 股票精选 ===
@app.route('/api/picks', methods=['GET'])
def get_picks():
    return jsonify(db.get("picks", []))

@app.route('/api/picks', methods=['POST'])
def add_pick():
    data = request.json
    db.setdefault("picks", []).append(data)
    save_db()
    return jsonify({"success": True})

# === 股票分析 ===
def get_kline(symbol):
    try:
        secid = "1." + symbol if symbol.startswith('6') else "0." + symbol
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {"secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "klt": 101, "fqt": 0, "beg": "20240101", "end": "20260222", "lmt": 60}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            return data["data"]["klines"]
    except:
        pass
    return None

@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    klines = get_kline(symbol)
    if not klines:
        return jsonify({'error': '无法获取数据'})
    
    closes = [float(k.split(',')[2]) for k in klines[-20:]]
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    
    return jsonify({
        'symbol': symbol, 
        'price': float(klines[-1].split(',')[2]), 
        'ma5': ma5, 
        'ma10': ma10, 
        'ma20': ma20
    })

# === 涨停模式分析 ===
@app.route('/api/limitup-pattern')
def limitup():
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {"pn": 1, "pz": 50, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f13,f14,f3"}
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        stocks = [d for d in data.get("data", {}).get("diff", []) if d.get("f3", 0) >= 9.5][:20]
    except:
        stocks = []
    
    volume_up = ma_golden = total = 0
    
    for stock in stocks:
        try:
            code = stock['f12']
            market = "1" if stock.get('f13') == 1 else "0"
            kline_url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={market}.{code}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=0&beg=20250201&end=20260222&lmt=15"
            kr = requests.get(kline_url, timeout=3)
            kd = kr.json()
            if kd.get("data") and kd["data"].get("klines"):
                klines = kd["data"]["klines"][-15:]
                if len(klines) >= 10:
                    closes = [float(k.split(',')[2]) for k in klines]
                    ma5 = sum(closes[-5:]) / 5
                    ma10 = sum(closes[-10:]) / 10
                    yes_vol = float(klines[-2].split(',')[5])
                    vol_5avg = sum([float(k.split(',')[5]) for k in klines[-6:-1]]) / 5
                    if yes_vol > vol_5avg * 1.2:
                        volume_up += 1
                    if ma5 > ma10:
                        ma_golden += 1
                    total += 1
        except:
            pass
    
    return jsonify({
        'total': total, 
        'volume_up': volume_up, 
        'volume_up_pct': round(volume_up/total*100, 1) if total > 0 else 0, 
        'ma_golden': ma_golden, 
        'ma_golden_pct': round(ma_golden/total*100, 1) if total > 0 else 0
    })
