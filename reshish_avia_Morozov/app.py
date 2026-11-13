import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'reshis_avia_morozov_secret_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'users.db')
CSV_PATH = os.path.join(BASE_DIR, 'Morozov_Arseniy_Igorevich_my_forecast.csv')

ROUTES_INFO = {
    'MOW-AER': {'destination': 'Сочи', 'name': 'Москва — Сочи', 'base_price': 9000, 'price_sensitivity': 0.141, 'price_min': 5400, 'price_max': 18000},
    'MOW-LED': {'destination': 'Санкт-Петербург', 'name': 'Москва — Санкт-Петербург', 'base_price': 5500, 'price_sensitivity': 0.294, 'price_min': 3300, 'price_max': 11000},
    'MOW-KGD': {'destination': 'Калининград', 'name': 'Москва — Калининград', 'base_price': 7500, 'price_sensitivity': 0.0957, 'price_min': 4500, 'price_max': 15000},
    'MOW-OVB': {'destination': 'Новосибирск', 'name': 'Москва — Новосибирск', 'base_price': 12000, 'price_sensitivity': 0.0312, 'price_min': 7200, 'price_max': 24000},
    'MOW-MRV': {'destination': 'Минеральные Воды', 'name': 'Москва — Минеральные Воды', 'base_price': 8000, 'price_sensitivity': 0.0653, 'price_min': 4800, 'price_max': 16000},
}

df_forecast = pd.read_csv(CSV_PATH)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL)')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html', routes=ROUTES_INFO)

@app.route('/api/auth/status')
def auth_status():
    return jsonify({'authenticated': 'user' in session, 'username': session.get('user')})

@app.route('/api/auth/register', methods=('POST',))
def register():
    data = request.get_json()
    u = data.get('username', '').strip()
    p = data.get('password', '').strip()
    if len(u) < 3 or len(p) < 4:
        return jsonify({'error': 'Логин от 3 символов, пароль от 4'}), 400
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (u, generate_password_hash(p)))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Логин уже занят'}), 400
    conn.close()
    session['user'] = u
    return jsonify({'username': u})

@app.route('/api/auth/login', methods=('POST',))
def login():
    data = request.get_json()
    u = data.get('username', '').strip()
    p = data.get('password', '').strip()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute('SELECT password_hash FROM users WHERE username = ?', (u,)).fetchone()
    conn.close()
    if row and check_password_hash(row.__getitem__(0), p):
        session['user'] = u
        return jsonify({'username': u})
    return jsonify({'error': 'Неверный логин или пароль'}), 401

@app.route('/api/auth/logout', methods=('POST',))
def logout():
    session.pop('user', None)
    return jsonify({'ok': True})

@app.route('/api/predict', methods=('POST',))
def predict():
    if 'user' not in session:
        return jsonify({'error': 'Нужна авторизация'}), 403
    data = request.get_json()
    r_code = data.get('route')
    f_date = data.get('date')
    try:
        price = float(data.get('price'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Некорректная цена'}), 400
    if r_code not in ROUTES_INFO:
        return jsonify({'error': 'Маршрут не найден'}), 404
    sub = df_forecast.query('route == @r_code and date == @f_date')
    if sub.empty:
        return jsonify({'error': 'Рейс на эту дату не найден'}), 404

    row = sub.iloc.__getitem__(0)
    meta = ROUTES_INFO.get(r_code)
    seats = int(row.get('seats'))
    base_p = meta.get('base_price')
    sens = meta.get('price_sensitivity')

    dem_05 = float(row.get('0.5_base_demand')) - sens * (price - base_p)
    sal_05 = min(seats, max(0.0, dem_05))

    q_list = []
    for q in ('0.1', '0.2', '0.3', '0.4', '0.5', '0.6', '0.7', '0.8', '0.9'):
        qd = float(row.get(f'{q}_base_demand')) - sens * (price - base_p)
        qs = min(seats, max(0.0, qd))
        q_list.append({'quantile': q, 'raw_demand': round(qd, 1), 'expected_sales': round(qs, 1)})

    return jsonify({
        'seats': seats,
        'raw_demand': round(dem_05, 1),
        'expected_sales': round(sal_05, 1),
        'is_capped': dem_05 > seats,
        'quantiles': q_list
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
