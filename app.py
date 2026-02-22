from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/limitup-pattern')
def limitup():
    return jsonify({'total': 20, 'volume_up': 5, 'ma_golden': 17})

@app.route('/api/analyze/<symbol>')
def analyze(symbol):
    return jsonify({'symbol': symbol, 'price': 10.5})

@app.route('/')
def home():
    return jsonify({'status': 'ok'})
