from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import sqlite3, os, secrets
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('DB_PATH', os.path.join(BASE, 'koenigswette.db'))
os.makedirs(os.path.dirname(DB), exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(24))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
ADMIN_PIN = os.environ.get('ADMIN_PIN', '2026')


def db():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def init_db():
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS settings (
      id INTEGER PRIMARY KEY CHECK (id=1),
      event_name TEXT NOT NULL DEFAULT 'KÖNIGSWETTE 2026',
      is_open INTEGER NOT NULL DEFAULT 1,
      winner_candidate_id INTEGER
    );
    INSERT OR IGNORE INTO settings (id) VALUES (1);

    CREATE TABLE IF NOT EXISTS candidates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL COLLATE NOCASE UNIQUE,
      created_by TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS bets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      bettor_name TEXT NOT NULL,
      candidate_id INTEGER NOT NULL,
      amount REAL NOT NULL CHECK(amount > 0),
      paid INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY(candidate_id) REFERENCES candidates(id)
    );
    ''')
    con.commit(); con.close()


def get_state():
    con = db()
    settings = con.execute('SELECT * FROM settings WHERE id=1').fetchone()
    rows = con.execute('''
      SELECT c.id, c.name, c.created_by,
             COALESCE(SUM(b.amount),0) AS pool,
             COUNT(b.id) AS bet_count
      FROM candidates c
      LEFT JOIN bets b ON b.candidate_id=c.id
      GROUP BY c.id
      ORDER BY pool DESC, c.name ASC
    ''').fetchall()
    total = sum(r['pool'] for r in rows)
    result = []
    for r in rows:
        pool = float(r['pool'])
        factor = round(total/pool, 2) if pool > 0 else None
        result.append({**dict(r), 'pool': pool, 'factor': factor,
                       'share': round((pool/total*100),1) if total else 0})
    con.close()
    return settings, result, total


@app.route('/')
def index():
    settings, candidates, total = get_state()
    return render_template('index.html', settings=settings, candidates=candidates, total=total)


@app.route('/health')
def health():
    return {'ok': True}, 200


@app.post('/candidate')
def add_candidate():
    settings, _, _ = get_state()
    if not settings['is_open']:
        flash('Die Wette ist geschlossen.'); return redirect(url_for('index'))
    name = ' '.join(request.form.get('name','').strip().split())
    created_by = ' '.join(request.form.get('created_by','').strip().split())
    if len(name) < 2 or len(name) > 80:
        flash('Bitte einen gültigen Namen eingeben.'); return redirect(url_for('index'))
    con = db()
    try:
        con.execute('INSERT INTO candidates(name, created_by, created_at) VALUES(?,?,?)',
                    (name, created_by, datetime.now().isoformat(timespec='seconds')))
        con.commit(); flash(f'{name} wurde ins Rennen geschickt.')
    except sqlite3.IntegrityError:
        flash(f'{name} ist bereits dabei.')
    finally:
        con.close()
    return redirect(url_for('index'))


@app.post('/bet')
def place_bet():
    settings, _, _ = get_state()
    if not settings['is_open']:
        flash('Die Wette ist geschlossen.'); return redirect(url_for('index'))
    bettor = ' '.join(request.form.get('bettor_name','').strip().split())
    try:
        cid = int(request.form.get('candidate_id','0'))
        amount = round(float(request.form.get('amount','0').replace(',','.')),2)
    except Exception:
        flash('Ungültige Eingabe.'); return redirect(url_for('index'))
    if len(bettor) < 2 or len(bettor) > 80 or amount < 1 or amount > 500:
        flash('Name eingeben; Einsatz zwischen 1 € und 500 €.'); return redirect(url_for('index'))
    con = db()
    candidate = con.execute('SELECT id FROM candidates WHERE id=?',(cid,)).fetchone()
    if not candidate:
        con.close(); flash('Kandidat nicht gefunden.'); return redirect(url_for('index'))
    con.execute('INSERT INTO bets(bettor_name,candidate_id,amount,created_at) VALUES(?,?,?,?)',
                (bettor,cid,amount,datetime.now().isoformat(timespec='seconds')))
    con.commit(); con.close()
    flash(f'Wette gespeichert: {bettor} – {amount:.2f} €')
    return redirect(url_for('index'))


@app.route('/api/state')
def api_state():
    settings, candidates, total = get_state()
    return jsonify({'event_name':settings['event_name'], 'is_open':bool(settings['is_open']),
                    'winner_candidate_id':settings['winner_candidate_id'], 'total':total,
                    'candidates':candidates})


@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method == 'POST' and not session.get('admin'):
        if request.form.get('pin') == ADMIN_PIN:
            session['admin']=True
        else:
            flash('Falsche PIN.')
        return redirect(url_for('admin'))
    if not session.get('admin'):
        return render_template('login.html')
    con = db()
    settings = con.execute('SELECT * FROM settings WHERE id=1').fetchone()
    bets = con.execute('''SELECT b.*, c.name candidate_name FROM bets b JOIN candidates c ON c.id=b.candidate_id ORDER BY b.id DESC''').fetchall()
    candidates = con.execute('SELECT * FROM candidates ORDER BY name').fetchall()
    con.close()
    _, _, total = get_state()
    return render_template('admin.html', settings=settings, bets=bets, candidates=candidates, total=total)


@app.post('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin'))


@app.post('/admin/toggle')
def admin_toggle():
    if not session.get('admin'): return redirect(url_for('admin'))
    con=db(); s=con.execute('SELECT is_open FROM settings WHERE id=1').fetchone()
    con.execute('UPDATE settings SET is_open=? WHERE id=1',(0 if s['is_open'] else 1,)); con.commit(); con.close()
    return redirect(url_for('admin'))


@app.post('/admin/paid/<int:bet_id>')
def admin_paid(bet_id):
    if not session.get('admin'): return redirect(url_for('admin'))
    con=db(); b=con.execute('SELECT paid FROM bets WHERE id=?',(bet_id,)).fetchone()
    if b: con.execute('UPDATE bets SET paid=? WHERE id=?',(0 if b['paid'] else 1,bet_id)); con.commit()
    con.close(); return redirect(url_for('admin'))


@app.post('/admin/winner')
def admin_winner():
    if not session.get('admin'): return redirect(url_for('admin'))
    try:
        cid = int(request.form.get('candidate_id','0'))
    except ValueError:
        flash('Ungültiger Kandidat.'); return redirect(url_for('admin'))
    con=db()
    candidate = con.execute('SELECT id FROM candidates WHERE id=?',(cid,)).fetchone()
    if not candidate:
        con.close(); flash('Kandidat nicht gefunden.'); return redirect(url_for('admin'))
    con.execute('UPDATE settings SET winner_candidate_id=?, is_open=0 WHERE id=1',(cid,)); con.commit(); con.close()
    return redirect(url_for('admin'))


@app.route('/result')
def result():
    settings, candidates, total = get_state()
    winner_id=settings['winner_candidate_id']
    winner=next((c for c in candidates if c['id']==winner_id),None)
    payouts=[]
    if winner and winner['pool']>0:
        con=db(); bets=con.execute('SELECT * FROM bets WHERE candidate_id=? ORDER BY amount DESC',(winner_id,)).fetchall(); con.close()
        factor=total/winner['pool']
        payouts=[{'name':b['bettor_name'],'amount':b['amount'],'result':round(b['amount']*factor,2),'paid':b['paid']} for b in bets]
    return render_template('result.html', winner=winner, payouts=payouts, total=total, settings=settings)


# Important for Gunicorn/production imports.
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)
