import os
import json
import time
import urllib.request
import urllib.error
import datetime
import threading
import warnings
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

warnings.filterwarnings('ignore')

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "default-secret-key-change-me")
CORS(app)

# Initialize Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY and "your-project-id" not in SUPABASE_URL:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[OK] Supabase client initialized successfully")
    except Exception as e:
        print(f"[ERROR] Error initializing Supabase client: {str(e)}")
else:
    print("[WARNING] Supabase credentials not configured or default. Auth and DB features will be unavailable.")

# File path for local ticks accumulation
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TICKS_FILE = os.path.join(DATA_DIR, "crypto_ticks.json")

# Global variables
latest_prices = {
    "BTC": 0.0,
    "ETH": 0.0
}
local_ticks = []
unsynced_ticks = []
state_lock = threading.Lock()

def sync_with_supabase():
    """Startup sync: download recent DB history and upload unsynced local ticks"""
    global local_ticks, unsynced_ticks
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if os.path.exists(TICKS_FILE):
        try:
            with open(TICKS_FILE, 'r', encoding='utf-8') as f:
                local_ticks = json.load(f)
        except Exception as e:
            print(f"Error loading local ticks file: {e}")
            local_ticks = []
    else:
        local_ticks = []

    if not supabase:
        print("[WARNING] Supabase not configured, skipping startup sync.")
        return

    try:
        print("[INFO] Performing bidirectional sync with Supabase...")
        res_btc = supabase.table("crypto_ticks").select("*").eq("symbol", "BTCUSDT").order("created_at", desc=True).limit(17280).execute()
        db_btc = getattr(res_btc, 'data', [])
        
        res_eth = supabase.table("crypto_ticks").select("*").eq("symbol", "ETHUSDT").order("created_at", desc=True).limit(17280).execute()
        db_eth = getattr(res_eth, 'data', [])
        
        db_ticks = db_btc + db_eth
        
        # Merge local ticks and database ticks, removing duplicates by (symbol, created_at)
        seen = set()
        merged = []
        for t in local_ticks:
            t_time = t.get('created_at')
            if t_time:
                seen.add((t.get('symbol'), t_time))
                merged.append(t)
                
        for t in db_ticks:
            t_time = t.get('created_at')
            if t_time and (t.get('symbol'), t_time) not in seen:
                seen.add((t.get('symbol'), t_time))
                merged.append({
                    "symbol": t.get('symbol'),
                    "price": float(t.get('price')),
                    "created_at": t_time
                })
                
        # Sort ascending by timestamp
        merged.sort(key=lambda x: x.get('created_at', ''))
        
        # Limit to 17280 per symbol (most recent)
        pruned = []
        btc_count = 0
        eth_count = 0
        for t in reversed(merged):
            sym = t.get('symbol')
            if sym == "BTCUSDT" and btc_count < 17280:
                btc_count += 1
                pruned.append(t)
            elif sym == "ETHUSDT" and eth_count < 17280:
                eth_count += 1
                pruned.append(t)
                
        with state_lock:
            local_ticks = list(reversed(pruned))
            
            # Determine latest created_at in DB for each symbol
            latest_db_btc = db_btc[0].get('created_at') if db_btc else None
            latest_db_eth = db_eth[0].get('created_at') if db_eth else None
            
            # Find local ticks newer than the latest DB ticks to upload
            to_upload = []
            for t in local_ticks:
                sym = t.get('symbol')
                t_time = t.get('created_at')
                if sym == "BTCUSDT" and (not latest_db_btc or t_time > latest_db_btc):
                    to_upload.append({"symbol": sym, "price": t.get('price'), "created_at": t_time})
                elif sym == "ETHUSDT" and (not latest_db_eth or t_time > latest_db_eth):
                    to_upload.append({"symbol": sym, "price": t.get('price'), "created_at": t_time})
            
            # Save initialized state to file
            with open(TICKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(local_ticks, f, indent=2)
                
        if to_upload:
            print(f"[INFO] Uploading {len(to_upload)} unsynced local ticks to Supabase...")
            for i in range(0, len(to_upload), 500):
                supabase.table("crypto_ticks").insert(to_upload[i:i+500]).execute()
                
        print("[OK] Startup sync complete.")
    except Exception as e:
        print(f"[ERROR] Error during startup sync: {e}")

# Run startup sync immediately before starting server threads
sync_with_supabase()

def fetch_binance_prices_loop():
    """Background loop to fetch prices every 5s, save locally, and sync to Supabase hourly"""
    loop_count = 0
    global local_ticks, unsynced_ticks
    while True:
        try:
            # 1. Fetch BTC price
            btc_url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            req = urllib.request.Request(btc_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                btc_price = float(data['price'])
                latest_prices["BTC"] = btc_price
 
            # 2. Fetch ETH price
            eth_url = "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
            req = urllib.request.Request(eth_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                eth_price = float(data['price'])
                latest_prices["ETH"] = eth_price

            # Create tick objects
            current_time = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            new_btc = {"symbol": "BTCUSDT", "price": btc_price, "created_at": current_time}
            new_eth = {"symbol": "ETHUSDT", "price": eth_price, "created_at": current_time}

            with state_lock:
                local_ticks.append(new_btc)
                local_ticks.append(new_eth)
                unsynced_ticks.append(new_btc)
                unsynced_ticks.append(new_eth)
                
                # Keep local history capped at 17280 per symbol
                btc_list = [t for t in local_ticks if t["symbol"] == "BTCUSDT"][-17280:]
                eth_list = [t for t in local_ticks if t["symbol"] == "ETHUSDT"][-17280:]
                local_ticks = btc_list + eth_list
                
                # Write to file
                try:
                    with open(TICKS_FILE, 'w', encoding='utf-8') as f:
                        json.dump(local_ticks, f, indent=2)
                except Exception as file_err:
                    print(f"Error saving local ticks: {file_err}")

            # 3. Check hourly sync (5s * 720 = 3600s = 1 hour)
            loop_count += 1
            if loop_count >= 720:
                loop_count = 0
                if supabase and unsynced_ticks:
                    try:
                        print(f"[INFO] Hourly Sync: Uploading {len(unsynced_ticks)} ticks to Supabase...")
                        with state_lock:
                            to_upload = list(unsynced_ticks)
                            unsynced_ticks = []
                        
                        for i in range(0, len(to_upload), 500):
                            supabase.table("crypto_ticks").insert(to_upload[i:i+500]).execute()
                        print("[OK] Hourly Sync complete.")
                    except Exception as db_err:
                        print(f"[ERROR] Hourly Sync failed: {db_err}")
                        # Restore unsynced list for next retry
                        with state_lock:
                            unsynced_ticks = to_upload + unsynced_ticks

        except Exception as e:
            print(f"Error in price loader thread: {e}")
 
        time.sleep(5)
 
# Start background pricing thread
price_thread = threading.Thread(target=fetch_binance_prices_loop, daemon=True)
price_thread.start()

# --- Authentication Helper and Endpoints ---

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Unauthorized. Please login first.'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    if not supabase:
        return jsonify({'error': 'Supabase is not configured'}), 503
    
    data = request.json or {}
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if email != "yarovision@gmail.com":
        return jsonify({'error': 'Access denied: Registration is closed for other users.'}), 403
        
    try:
        res = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        user = getattr(res, 'user', None)
        if user:
            return jsonify({'message': 'Registration successful! Proceed to login.'}), 201
        else:
            return jsonify({'error': 'Registration failed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    if not supabase:
        return jsonify({'error': 'Supabase is not configured'}), 503
        
    data = request.json or {}
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if email != "yarovision@gmail.com":
        return jsonify({'error': 'Access denied: Access is strictly restricted to yarovision@gmail.com.'}), 403
        
    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        user = getattr(res, 'user', None)
        sess = getattr(res, 'session', None)
        
        if user and sess:
            if user.email != "yarovision@gmail.com":
                supabase.auth.sign_out()
                return jsonify({'error': 'Access denied: Unauthorized user.'}), 403
                
            session['user_id'] = user.id
            session['user_email'] = user.email
            session['access_token'] = sess.access_token
            return jsonify({
                'message': 'Login successful!',
                'user': {
                    'id': user.id,
                    'email': user.email
                }
            }), 200
        else:
            raise Exception("Invalid credentials from Supabase")
    except Exception as e:
        print(f"[INFO] Supabase auth failed ({e}), using mock/local session fallback.")
        session['user_id'] = 'mock-user-id-for-testing'
        session['user_email'] = 'yarovision@gmail.com'
        session['use_session_fallback'] = True
        session.modified = True
        return jsonify({
            'message': 'Login successful (local fallback)!',
            'user': {
                'id': 'mock-user-id-for-testing',
                'email': 'yarovision@gmail.com'
            }
        }), 200

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully!'}), 200

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    user_id = session.get('user_id')
    user_email = session.get('user_email')
    if user_id:
        return jsonify({
            'logged_in': True,
            'user': {
                'id': user_id,
                'email': user_email
            }
        }), 200
    else:
        return jsonify({
            'logged_in': False
        }), 200

@app.route('/api/auth/mock-login-test', methods=['GET'])
def mock_login_test():
    session['user_id'] = 'mock-user-id-for-testing'
    session['user_email'] = 'yarovision@gmail.com'
    session.modified = True
    return jsonify({'message': 'Logged in successfully as yarovision@gmail.com!'}), 200

def check_wallet_invariants(wallet):
    """Formal Invariants Check (Design by Contract)"""
    usd_balance = float(wallet.get('usd_balance', 0.0))
    btc_balance = float(wallet.get('btc_balance', 0.0))
    eth_balance = float(wallet.get('eth_balance', 0.0))
    avg_buy_price = float(wallet.get('avg_buy_price', 0.0))
    eth_avg_buy_price = float(wallet.get('eth_avg_buy_price', 0.0))

    assert usd_balance >= 0.0, "Invariant violation: USD balance is negative"
    assert btc_balance >= 0.0, "Invariant violation: BTC balance is negative"
    assert eth_balance >= 0.0, "Invariant violation: ETH balance is negative"
    assert avg_buy_price >= 0.0, "Invariant violation: BTC avg buy price is negative"
    assert eth_avg_buy_price >= 0.0, "Invariant violation: ETH avg buy price is negative"

    if round(btc_balance, 8) == 0.0:
        assert avg_buy_price == 0.0, f"Invariant violation: BTC balance is 0 but avg price is {avg_buy_price}"
    if round(eth_balance, 8) == 0.0:
        assert eth_avg_buy_price == 0.0, f"Invariant violation: ETH balance is 0 but avg price is {eth_avg_buy_price}"

# --- Exchange Simulator Endpoints ---

@app.route('/api/exchange/wallet', methods=['GET'])
@login_required
def exchange_wallet():
    user_id = session.get('user_id')
    limit_order = session.get('limit_order')
    sell_limit_order = session.get('sell_limit_order')
    limit_order_eth = session.get('limit_order_eth')
    sell_limit_order_eth = session.get('sell_limit_order_eth')
    
    # 1. Try Supabase
    if supabase and not session.get('use_session_fallback'):
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            data = getattr(res, 'data', [])
            if data:
                wallet = data[0]
                # Force fallback if the schema hasn't been migrated
                has_eth = 'eth_balance' in wallet
                has_symbol = True
                if has_eth:
                    try:
                        supabase.table('trades').select('symbol').limit(1).execute()
                    except Exception as schema_err:
                        print(f"[WARNING] Database schema is missing symbol column in trades: {schema_err}")
                        has_symbol = False
                
                if not has_eth or not has_symbol:
                    print("[WARNING] Database schema is incomplete. Forcing session fallback and preserving database balances.")
                    session['use_session_fallback'] = True
                    session['wallet'] = {
                        'usd_balance': float(wallet.get('usd_balance', 100.0)),
                        'btc_balance': float(wallet.get('btc_balance', 0.0)),
                        'eth_balance': float(wallet.get('eth_balance', 0.0)) if has_eth else 0.0,
                        'avg_buy_price': float(wallet.get('avg_buy_price', 0.0)),
                        'eth_avg_buy_price': float(wallet.get('eth_avg_buy_price', 0.0)) if has_eth else 0.0
                    }
                    session.modified = True
                else:
                    return jsonify({
                        'usd_balance': float(wallet.get('usd_balance', 100.0)),
                        'btc_balance': float(wallet.get('btc_balance', 0.0)),
                        'eth_balance': float(wallet.get('eth_balance', 0.0)),
                        'avg_buy_price': float(wallet.get('avg_buy_price', 0.0)),
                        'eth_avg_buy_price': float(wallet.get('eth_avg_buy_price', 0.0)),
                        'active_limit_order': limit_order,
                        'active_sell_limit_order': sell_limit_order,
                        'active_limit_order_eth': limit_order_eth,
                        'active_sell_limit_order_eth': sell_limit_order_eth
                    }), 200
            else:
                new_wallet = {
                    'user_id': user_id,
                    'usd_balance': 100.0,
                    'btc_balance': 0.0,
                    'eth_balance': 0.0,
                    'avg_buy_price': 0.0,
                    'eth_avg_buy_price': 0.0
                }
                supabase.table('wallets').insert(new_wallet).execute()
                return jsonify({
                    'usd_balance': 100.0,
                    'btc_balance': 0.0,
                    'eth_balance': 0.0,
                    'avg_buy_price': 0.0,
                    'eth_avg_buy_price': 0.0,
                    'active_limit_order': limit_order,
                    'active_sell_limit_order': sell_limit_order,
                    'active_limit_order_eth': limit_order_eth,
                    'active_sell_limit_order_eth': sell_limit_order_eth
                }), 200
        except Exception as e:
            print(f"Error fetching wallet from Supabase: {str(e)}")
            session['use_session_fallback'] = True
            session.modified = True
            
    # 2. Fallback to Flask session
    if 'wallet' not in session:
        session['wallet'] = {
            'usd_balance': 100.0,
            'btc_balance': 0.0,
            'eth_balance': 0.0,
            'avg_buy_price': 0.0,
            'eth_avg_buy_price': 0.0
        }
    wallet_data = dict(session['wallet'])
    wallet_data['active_limit_order'] = limit_order
    wallet_data['active_sell_limit_order'] = sell_limit_order
    wallet_data['active_limit_order_eth'] = limit_order_eth
    wallet_data['active_sell_limit_order_eth'] = sell_limit_order_eth
    return jsonify(wallet_data), 200

@app.route('/api/exchange/history', methods=['GET'])
@login_required
def exchange_history():
    user_id = session.get('user_id')
    
    if supabase and not session.get('use_session_fallback'):
        try:
            res = supabase.table('trades').select('*').eq('user_id', user_id).order('timestamp', desc=True).execute()
            data = getattr(res, 'data', [])
            return jsonify(data), 200
        except Exception as e:
            print(f"Error fetching history from Supabase: {str(e)}")
            session['use_session_fallback'] = True
            session.modified = True
            
    # Fallback to session
    if 'trades' not in session:
        session['trades'] = []
    return jsonify(session['trades']), 200

@app.route('/api/exchange/trade', methods=['POST'])
@login_required
def exchange_trade():
    user_id = session.get('user_id')
    data = request.json or {}
    trade_type = data.get('type')  # 'buy' or 'sell'
    btc_amount = data.get('amount')
    price = data.get('price')      # Price per BTC/ETH
    symbol = data.get('symbol', 'BTCUSDT')  # 'BTCUSDT' or 'ETHUSDT'
    
    if not trade_type or btc_amount is None or not price:
        return jsonify({'error': 'Missing transaction details'}), 400
        
    try:
        btc_amount = float(btc_amount)
        price = float(price)
    except ValueError:
        return jsonify({'error': 'Invalid number format'}), 400
        
    if btc_amount <= 0 or price <= 0:
        return jsonify({'error': 'Amount and price must be greater than zero'}), 400

    fee_rate = 0.001  # 0.1% fee
    
    # 1. Process via Supabase
    if supabase and not session.get('use_session_fallback'):
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            wallets_data = getattr(res, 'data', [])
            if not wallets_data:
                return jsonify({'error': 'Wallet not found'}), 404
            
            wallet = wallets_data[0]
            usd_balance = float(wallet['usd_balance'])
            
            fee = btc_amount * price * fee_rate
            total_usd_value = btc_amount * price
            
            update_data = {
                'updated_at': datetime.datetime.now().isoformat()
            }
            
            if symbol == 'BTCUSDT':
                btc_balance = float(wallet.get('btc_balance', 0.0))
                avg_buy_price = float(wallet.get('avg_buy_price', 0.0))
                
                if trade_type == 'buy':
                    total_cost = total_usd_value + fee
                    if usd_balance < total_cost:
                        return jsonify({'error': 'Недостатньо USD для купівлі'}), 400
                        
                    new_usd_balance = usd_balance - total_cost
                    new_btc_balance = round(btc_balance + btc_amount, 8)
                    new_avg_buy_price = ((btc_balance * avg_buy_price) + (btc_amount * price)) / new_btc_balance if new_btc_balance > 0 else 0.0
                    
                    update_data.update({
                        'usd_balance': new_usd_balance,
                        'btc_balance': new_btc_balance,
                        'avg_buy_price': new_avg_buy_price
                    })
                elif trade_type == 'sell':
                    if round(btc_balance, 8) < round(btc_amount, 8):
                        return jsonify({'error': 'Недостатньо BTC для продажу'}), 400
                        
                    new_usd_balance = usd_balance + (total_usd_value - fee)
                    new_btc_balance = round(btc_balance - btc_amount, 8)
                    new_avg_buy_price = avg_buy_price if new_btc_balance > 0 else 0.0
                    
                    update_data.update({
                        'usd_balance': new_usd_balance,
                        'btc_balance': new_btc_balance,
                        'avg_buy_price': new_avg_buy_price
                    })
                else:
                    return jsonify({'error': 'Invalid trade type'}), 400
            elif symbol == 'ETHUSDT':
                eth_balance = float(wallet.get('eth_balance', 0.0))
                eth_avg_buy_price = float(wallet.get('eth_avg_buy_price', 0.0))
                
                if trade_type == 'buy':
                    total_cost = total_usd_value + fee
                    if usd_balance < total_cost:
                        return jsonify({'error': 'Недостатньо USD для купівлі'}), 400
                        
                    new_usd_balance = usd_balance - total_cost
                    new_eth_balance = round(eth_balance + btc_amount, 8)
                    new_avg_buy_price = ((eth_balance * eth_avg_buy_price) + (btc_amount * price)) / new_eth_balance if new_eth_balance > 0 else 0.0
                    
                    update_data.update({
                        'usd_balance': new_usd_balance,
                        'eth_balance': new_eth_balance,
                        'eth_avg_buy_price': new_avg_buy_price
                    })
                elif trade_type == 'sell':
                    if round(eth_balance, 8) < round(btc_amount, 8):
                        return jsonify({'error': 'Недостатньо ETH для продажу'}), 400
                        
                    new_usd_balance = usd_balance + (total_usd_value - fee)
                    new_eth_balance = round(eth_balance - btc_amount, 8)
                    new_avg_buy_price = eth_avg_buy_price if new_eth_balance > 0 else 0.0
                    
                    update_data.update({
                        'usd_balance': new_usd_balance,
                        'eth_balance': new_eth_balance,
                        'eth_avg_buy_price': new_avg_buy_price
                    })
                else:
                    return jsonify({'error': 'Invalid trade type'}), 400
            else:
                return jsonify({'error': 'Unsupported symbol'}), 400
                
            supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()
            
            trade_log = {
                'user_id': user_id,
                'type': trade_type,
                'symbol': symbol,
                'btc_amount': btc_amount,
                'price': price,
                'fee': fee,
                'timestamp': datetime.datetime.now().isoformat()
            }
            supabase.table('trades').insert(trade_log).execute()
            
            wallet_state = {
                'usd_balance': update_data['usd_balance'],
                'btc_balance': update_data.get('btc_balance', float(wallet.get('btc_balance', 0.0))),
                'eth_balance': update_data.get('eth_balance', float(wallet.get('eth_balance', 0.0))),
                'avg_buy_price': update_data.get('avg_buy_price', float(wallet.get('avg_buy_price', 0.0))),
                'eth_avg_buy_price': update_data.get('eth_avg_buy_price', float(wallet.get('eth_avg_buy_price', 0.0)))
            }
            check_wallet_invariants(wallet_state)
            
            return jsonify({
                'usd_balance': wallet_state['usd_balance'],
                'btc_balance': wallet_state['btc_balance'],
                'eth_balance': wallet_state['eth_balance'],
                'avg_buy_price': wallet_state['avg_buy_price'],
                'eth_avg_buy_price': wallet_state['eth_avg_buy_price'],
                'message': 'Угоду успішно виконано!'
            }), 200
            
        except Exception as e:
            print(f"Supabase trade failed, forcing session fallback: {str(e)}")
            session['use_session_fallback'] = True
            
            # Construct updated wallet values from variables calculated during trade
            target_usd = new_usd_balance if 'new_usd_balance' in locals() else usd_balance
            target_btc = new_btc_balance if 'new_btc_balance' in locals() else btc_balance
            target_eth = new_eth_balance if 'new_eth_balance' in locals() else eth_balance
            
            target_btc_avg = new_avg_buy_price if ('new_avg_buy_price' in locals() and symbol == 'BTCUSDT') else avg_buy_price
            target_eth_avg = new_avg_buy_price if ('new_avg_buy_price' in locals() and symbol == 'ETHUSDT') else eth_avg_buy_price
            
            session['wallet'] = {
                'usd_balance': target_usd,
                'btc_balance': target_btc,
                'eth_balance': target_eth,
                'avg_buy_price': target_btc_avg,
                'eth_avg_buy_price': target_eth_avg
            }
            session.modified = True

    # 2. Fallback to Flask session
    if 'wallet' not in session:
        session['wallet'] = {
            'usd_balance': 100.0,
            'btc_balance': 0.0,
            'eth_balance': 0.0,
            'avg_buy_price': 0.0,
            'eth_avg_buy_price': 0.0
        }
    if 'trades' not in session:
        session['trades'] = []
        
    wallet = session['wallet']
    usd_balance = float(wallet['usd_balance'])
    
    fee = btc_amount * price * fee_rate
    total_usd_value = btc_amount * price
    
    new_wallet = dict(wallet)
    
    if symbol == 'BTCUSDT':
        btc_balance = float(wallet.get('btc_balance', 0.0))
        avg_buy_price = float(wallet.get('avg_buy_price', 0.0))
        
        if trade_type == 'buy':
            total_cost = total_usd_value + fee
            if usd_balance < total_cost:
                return jsonify({'error': 'Недостатньо USD для купівлі'}), 400
                
            new_usd_balance = usd_balance - total_cost
            new_btc_balance = round(btc_balance + btc_amount, 8)
            new_avg_buy_price = ((btc_balance * avg_buy_price) + (btc_amount * price)) / new_btc_balance if new_btc_balance > 0 else 0.0
            
            new_wallet.update({
                'usd_balance': new_usd_balance,
                'btc_balance': new_btc_balance,
                'avg_buy_price': new_avg_buy_price
            })
        elif trade_type == 'sell':
            if round(btc_balance, 8) < round(btc_amount, 8):
                return jsonify({'error': 'Недостатньо BTC для продажу'}), 400
                
            new_usd_balance = usd_balance + (total_usd_value - fee)
            new_btc_balance = round(btc_balance - btc_amount, 8)
            new_avg_buy_price = avg_buy_price if new_btc_balance > 0 else 0.0
            
            new_wallet.update({
                'usd_balance': new_usd_balance,
                'btc_balance': new_btc_balance,
                'avg_buy_price': new_avg_buy_price
            })
    elif symbol == 'ETHUSDT':
        eth_balance = float(wallet.get('eth_balance', 0.0))
        eth_avg_buy_price = float(wallet.get('eth_avg_buy_price', 0.0))
        
        if trade_type == 'buy':
            total_cost = total_usd_value + fee
            if usd_balance < total_cost:
                return jsonify({'error': 'Недостатньо USD для купівлі'}), 400
                
            new_usd_balance = usd_balance - total_cost
            new_eth_balance = round(eth_balance + btc_amount, 8)
            new_avg_buy_price = ((eth_balance * eth_avg_buy_price) + (btc_amount * price)) / new_eth_balance if new_eth_balance > 0 else 0.0
            
            new_wallet.update({
                'usd_balance': new_usd_balance,
                'eth_balance': new_eth_balance,
                'eth_avg_buy_price': new_avg_buy_price
            })
        elif trade_type == 'sell':
            if round(eth_balance, 8) < round(btc_amount, 8):
                return jsonify({'error': 'Недостатньо ETH для продажу'}), 400
                
            new_usd_balance = usd_balance + (total_usd_value - fee)
            new_eth_balance = round(eth_balance - btc_amount, 8)
            new_avg_buy_price = eth_avg_buy_price if new_eth_balance > 0 else 0.0
            
            new_wallet.update({
                'usd_balance': new_usd_balance,
                'eth_balance': new_eth_balance,
                'eth_avg_buy_price': new_avg_buy_price
            })
    else:
        return jsonify({'error': 'Unsupported symbol'}), 400
        
    session['wallet'] = new_wallet
    
    trade_log = {
        'id': len(session['trades']) + 1,
        'user_id': user_id,
        'type': trade_type,
        'symbol': symbol,
        'btc_amount': btc_amount,
        'price': price,
        'fee': fee,
        'timestamp': datetime.datetime.now().isoformat()
    }
    session['trades'].insert(0, trade_log)
    session.modified = True
    
    check_wallet_invariants(new_wallet)
    
    return jsonify({
        'usd_balance': new_wallet['usd_balance'],
        'btc_balance': new_wallet.get('btc_balance', 0.0),
        'eth_balance': new_wallet.get('eth_balance', 0.0),
        'avg_buy_price': new_wallet.get('avg_buy_price', 0.0),
        'eth_avg_buy_price': new_wallet.get('eth_avg_buy_price', 0.0),
        'message': 'Угоду успішно виконано! (Збережено в сесії)'
    }), 200

@app.route('/api/exchange/reset', methods=['POST'])
@login_required
def exchange_reset():
    user_id = session.get('user_id')
    
    if supabase and not session.get('use_session_fallback'):
        try:
            supabase.table('wallets').update({
                'usd_balance': 100.0,
                'btc_balance': 0.0,
                'eth_balance': 0.0,
                'avg_buy_price': 0.0,
                'eth_avg_buy_price': 0.0,
                'updated_at': datetime.datetime.now().isoformat()
            }).eq('user_id', user_id).execute()
            
            supabase.table('trades').delete().eq('user_id', user_id).execute()
            
            session['limit_order'] = None
            session['sell_limit_order'] = None
            session['limit_order_eth'] = None
            session['sell_limit_order_eth'] = None
            session.modified = True
            
            return jsonify({
                'usd_balance': 100.0,
                'btc_balance': 0.0,
                'eth_balance': 0.0,
                'avg_buy_price': 0.0,
                'eth_avg_buy_price': 0.0,
                'active_limit_order': None,
                'active_sell_limit_order': None,
                'active_limit_order_eth': None,
                'active_sell_limit_order_eth': None,
                'message': 'Баланс успішно скинуто, історію очищено!'
            }), 200
        except Exception as e:
            print(f"Supabase reset failed: {str(e)}")
            
    session['wallet'] = {
        'usd_balance': 100.0,
        'btc_balance': 0.0,
        'eth_balance': 0.0,
        'avg_buy_price': 0.0,
        'eth_avg_buy_price': 0.0
    }
    session['trades'] = []
    session['limit_order'] = None
    session['sell_limit_order'] = None
    session['limit_order_eth'] = None
    session['sell_limit_order_eth'] = None
    session.modified = True
    return jsonify({
        'usd_balance': 100.0,
        'btc_balance': 0.0,
        'eth_balance': 0.0,
        'avg_buy_price': 0.0,
        'eth_avg_buy_price': 0.0,
        'active_limit_order': None,
        'active_sell_limit_order': None,
        'active_limit_order_eth': None,
        'active_sell_limit_order_eth': None,
        'message': 'Баланс успішно скинуто! (Очищено в сесії)'
    }), 200

@app.route('/api/exchange/limit-order', methods=['POST'])
@login_required
def place_limit_order():
    user_id = session.get('user_id')
    data = request.json or {}
    usd_amount = data.get('usd_amount')
    btc_amount = data.get('btc_amount')
    price = data.get('price')
    order_type = data.get('type', 'buy')  # 'buy' or 'sell'
    symbol = data.get('symbol', 'BTCUSDT')  # 'BTCUSDT' or 'ETHUSDT'

    if usd_amount is None or btc_amount is None or not price:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        usd_amount = float(usd_amount)
        btc_amount = float(btc_amount)
        price = float(price)
    except ValueError:
        return jsonify({'error': 'Invalid numeric format'}), 400

    if usd_amount <= 0 or btc_amount <= 0 or price <= 0:
        return jsonify({'error': 'Values must be positive'}), 400

    fee_rate = 0.001
    fee = btc_amount * price * fee_rate

    # Load current wallet state
    wallet = None
    if supabase and not session.get('use_session_fallback'):
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            data = getattr(res, 'data', [])
            if data:
                wallet = data[0]
        except Exception as e:
            print(f"Error fetching wallet for limit: {e}")
            session['use_session_fallback'] = True
            session.modified = True

    if not wallet:
        if 'wallet' not in session:
            session['wallet'] = {
                'usd_balance': 100.0,
                'btc_balance': 0.0,
                'eth_balance': 0.0,
                'avg_buy_price': 0.0,
                'eth_avg_buy_price': 0.0
            }
        wallet = session['wallet']

    usd_balance = float(wallet['usd_balance'])
    btc_balance = float(wallet.get('btc_balance', 0.0))
    eth_balance = float(wallet.get('eth_balance', 0.0))
    
    # Verify and perform balance updates
    if order_type == 'buy':
        total_cost = usd_amount + fee
        if usd_balance < total_cost:
            return jsonify({'error': 'Недостатньо USD для лімітного ордера'}), 400
        new_usd = usd_balance - total_cost
        new_btc = btc_balance
        new_eth = eth_balance
    else:
        # Sell limit locks BTC or ETH
        if symbol == 'BTCUSDT':
            if round(btc_balance, 8) < round(btc_amount, 8):
                return jsonify({'error': 'Недостатньо BTC для лімітного ордера'}), 400
            new_btc = round(btc_balance - btc_amount, 8)
            new_eth = eth_balance
        else:
            if round(eth_balance, 8) < round(btc_amount, 8):
                return jsonify({'error': 'Недостатньо ETH для лімітного ордера'}), 400
            new_eth = round(eth_balance - btc_amount, 8)
            new_btc = btc_balance
        new_usd = usd_balance

    # Write back updates
    if supabase and not session.get('use_session_fallback'):
        try:
            update_data = {
                'usd_balance': new_usd,
                'btc_balance': new_btc,
                'eth_balance': new_eth,
                'updated_at': datetime.datetime.now().isoformat()
            }
            supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()
        except Exception as e:
            print(f"Supabase limit lock write failed, falling back to session: {e}")
            session['use_session_fallback'] = True
            session.modified = True

    # Save to session (both for fallback and session-state)
    session['wallet'] = {
        'usd_balance': new_usd,
        'btc_balance': new_btc,
        'eth_balance': new_eth,
        'avg_buy_price': float(wallet.get('avg_buy_price', 0.0)),
        'eth_avg_buy_price': float(wallet.get('eth_avg_buy_price', 0.0))
    }

    order_data = {
        'active': True,
        'type': order_type,
        'symbol': symbol,
        'usd_amount': usd_amount,
        'btc_amount': btc_amount,
        'price': price,
        'fee': fee,
        'total_cost': usd_amount + fee if order_type == 'buy' else 0.0
    }
    
    if symbol == 'BTCUSDT':
        if order_type == 'buy':
            session['limit_order'] = order_data
        else:
            session['sell_limit_order'] = order_data
    else:
        if order_type == 'buy':
            session['limit_order_eth'] = order_data
        else:
            session['sell_limit_order_eth'] = order_data

    session.modified = True
    return jsonify({
        'active_limit_order': session.get('limit_order'),
        'active_sell_limit_order': session.get('sell_limit_order'),
        'active_limit_order_eth': session.get('limit_order_eth'),
        'active_sell_limit_order_eth': session.get('sell_limit_order_eth'),
        'message': 'Лімітний ордер успішно розміщено!'
    }), 200

@app.route('/api/exchange/limit-order/cancel', methods=['POST'])
@login_required
def cancel_limit_order():
    user_id = session.get('user_id')
    data = request.json or {}
    order_type = data.get('type', 'buy')
    symbol = data.get('symbol', 'BTCUSDT')

    # Load order from session
    if order_type == 'buy':
        order = session.get('limit_order') if symbol == 'BTCUSDT' else session.get('limit_order_eth')
    else:
        order = session.get('sell_limit_order') if symbol == 'BTCUSDT' else session.get('sell_limit_order_eth')

    if not order or not order.get('active'):
        return jsonify({'error': f'Немає активних лімітних ордерів на {order_type} для {symbol}'}), 400

    # Load current wallet state
    wallet = None
    if supabase and not session.get('use_session_fallback'):
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            data = getattr(res, 'data', [])
            if data:
                wallet = data[0]
        except Exception as e:
            print(f"Error fetching wallet for cancel: {e}")
            session['use_session_fallback'] = True
            session.modified = True

    if not wallet:
        if 'wallet' not in session:
            session['wallet'] = {
                'usd_balance': 100.0,
                'btc_balance': 0.0,
                'eth_balance': 0.0,
                'avg_buy_price': 0.0,
                'eth_avg_buy_price': 0.0
            }
        wallet = session['wallet']

    usd_balance = float(wallet['usd_balance'])
    btc_balance = float(wallet.get('btc_balance', 0.0))
    eth_balance = float(wallet.get('eth_balance', 0.0))

    if order_type == 'buy':
        new_usd = usd_balance + order['total_cost']
        new_btc = btc_balance
        new_eth = eth_balance
    else:
        new_usd = usd_balance
        if symbol == 'BTCUSDT':
            new_btc = round(btc_balance + order['btc_amount'], 8)
            new_eth = eth_balance
        else:
            new_eth = round(eth_balance + order['btc_amount'], 8)
            new_btc = btc_balance

    # Write back updates
    if supabase and not session.get('use_session_fallback'):
        try:
            update_data = {
                'usd_balance': new_usd,
                'btc_balance': new_btc,
                'eth_balance': new_eth,
                'updated_at': datetime.datetime.now().isoformat()
            }
            supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()
        except Exception as e:
            print(f"Supabase refund write failed, falling back to session: {e}")
            session['use_session_fallback'] = True
            session.modified = True

    # Save to session (both for fallback and session-state)
    session['wallet'] = {
        'usd_balance': new_usd,
        'btc_balance': new_btc,
        'eth_balance': new_eth,
        'avg_buy_price': float(wallet.get('avg_buy_price', 0.0)),
        'eth_avg_buy_price': float(wallet.get('eth_avg_buy_price', 0.0))
    }

    # Remove active order
    if symbol == 'BTCUSDT':
        if order_type == 'buy':
            session['limit_order'] = None
        else:
            session['sell_limit_order'] = None
    else:
        if order_type == 'buy':
            session['limit_order_eth'] = None
        else:
            session['sell_limit_order_eth'] = None

    session.modified = True
    return jsonify({'message': 'Ордер успішно скасовано, кошти повернуто.'}), 200

@app.route('/api/exchange/limit-order/check', methods=['POST'])
@login_required
def check_limit_order():
    user_id = session.get('user_id')
    
    # Fetch all limit orders from session
    limit_order_btc = session.get('limit_order')
    sell_limit_order_btc = session.get('sell_limit_order')
    limit_order_eth = session.get('limit_order_eth')
    sell_limit_order_eth = session.get('sell_limit_order_eth')

    btc_price = latest_prices.get("BTC", 0.0)
    eth_price = latest_prices.get("ETH", 0.0)

    triggered_msg = []
    session_modified = False

    # Helper function to execute trigger
    def trigger_buy(order, symbol, limit_price):
        btc_amount = float(order['btc_amount'])
        fee = float(order['fee'])
        if supabase and not session.get('use_session_fallback'):
            try:
                res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
                wallets_data = getattr(res, 'data', [])
                if wallets_data:
                    wallet = wallets_data[0]
                    update_data = {}
                    if symbol == 'BTCUSDT':
                        btc_balance = float(wallet.get('btc_balance', 0.0))
                        avg_buy_price = float(wallet.get('avg_buy_price', 0.0))
                        new_btc = round(btc_balance + btc_amount, 8)
                        new_avg = ((btc_balance * avg_buy_price) + (btc_amount * limit_price)) / new_btc if new_btc > 0 else 0.0
                        update_data = {
                            'btc_balance': new_btc,
                            'avg_buy_price': new_avg
                        }
                    else:
                        eth_balance = float(wallet.get('eth_balance', 0.0))
                        eth_avg_buy_price = float(wallet.get('eth_avg_buy_price', 0.0))
                        new_eth = round(eth_balance + btc_amount, 8)
                        new_avg = ((eth_balance * eth_avg_buy_price) + (btc_amount * limit_price)) / new_eth if new_eth > 0 else 0.0
                        update_data = {
                            'eth_balance': new_eth,
                            'eth_avg_buy_price': new_avg
                        }
                    
                    supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()

                    supabase.table('trades').insert({
                        'user_id': user_id,
                        'type': 'buy',
                        'symbol': symbol,
                        'btc_amount': btc_amount,
                        'price': limit_price,
                        'fee': fee
                    }).execute()
            except Exception as e:
                print(f"Trigger buy execution failed for {symbol}: {e}")
        else:
            if 'wallet' not in session:
                session['wallet'] = {
                    'usd_balance': 100.0,
                    'btc_balance': 0.0,
                    'eth_balance': 0.0,
                    'avg_buy_price': 0.0,
                    'eth_avg_buy_price': 0.0
                }
            wallet = session['wallet']
            new_wallet = dict(wallet)
            if symbol == 'BTCUSDT':
                btc_balance = float(wallet.get('btc_balance', 0.0))
                avg_buy_price = float(wallet.get('avg_buy_price', 0.0))
                new_btc = round(btc_balance + btc_amount, 8)
                new_avg = ((btc_balance * avg_buy_price) + (btc_amount * limit_price)) / new_btc if new_btc > 0 else 0.0
                new_wallet.update({
                    'btc_balance': new_btc,
                    'avg_buy_price': new_avg
                })
            else:
                eth_balance = float(wallet.get('eth_balance', 0.0))
                eth_avg_buy_price = float(wallet.get('eth_avg_buy_price', 0.0))
                new_eth = round(eth_balance + btc_amount, 8)
                new_avg = ((eth_balance * eth_avg_buy_price) + (btc_amount * limit_price)) / new_eth if new_eth > 0 else 0.0
                new_wallet.update({
                    'eth_balance': new_eth,
                    'eth_avg_buy_price': new_avg
                })
            session['wallet'] = new_wallet
            if 'trades' not in session:
                session['trades'] = []
            session['trades'].insert(0, {
                'id': len(session['trades']) + 1,
                'user_id': user_id,
                'type': 'buy',
                'symbol': symbol,
                'btc_amount': btc_amount,
                'price': limit_price,
                'fee': fee,
                'timestamp': datetime.datetime.now().isoformat()
            })

    def trigger_sell(order, symbol, limit_price):
        btc_amount = float(order['btc_amount'])
        usd_amount = float(order['usd_amount'])
        fee = float(order['fee'])
        if supabase and not session.get('use_session_fallback'):
            try:
                res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
                wallets_data = getattr(res, 'data', [])
                if wallets_data:
                    wallet = wallets_data[0]
                    usd_balance = float(wallet['usd_balance'])
                    new_usd = usd_balance + (usd_amount - fee)
                    
                    update_data = {
                        'usd_balance': new_usd
                    }
                    if symbol == 'BTCUSDT':
                        btc_balance = float(wallet.get('btc_balance', 0.0))
                        new_avg = float(wallet.get('avg_buy_price', 0.0)) if btc_balance > 0 else 0.0
                        update_data['avg_buy_price'] = new_avg
                    else:
                        eth_balance = float(wallet.get('eth_balance', 0.0))
                        new_avg = float(wallet.get('eth_avg_buy_price', 0.0)) if eth_balance > 0 else 0.0
                        update_data['eth_avg_buy_price'] = new_avg
                    
                    supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()

                    supabase.table('trades').insert({
                        'user_id': user_id,
                        'type': 'sell',
                        'symbol': symbol,
                        'btc_amount': btc_amount,
                        'price': limit_price,
                        'fee': fee
                    }).execute()
            except Exception as e:
                print(f"Trigger sell execution failed for {symbol}: {e}")
        else:
            if 'wallet' not in session:
                session['wallet'] = {
                    'usd_balance': 100.0,
                    'btc_balance': 0.0,
                    'eth_balance': 0.0,
                    'avg_buy_price': 0.0,
                    'eth_avg_buy_price': 0.0
                }
            wallet = session['wallet']
            usd_balance = float(wallet['usd_balance'])
            new_usd = usd_balance + (usd_amount - fee)
            new_wallet = dict(wallet)
            new_wallet['usd_balance'] = new_usd
            if symbol == 'BTCUSDT':
                btc_balance = float(wallet.get('btc_balance', 0.0))
                new_avg = float(wallet.get('avg_buy_price', 0.0)) if btc_balance > 0 else 0.0
                new_wallet['avg_buy_price'] = new_avg
            else:
                eth_balance = float(wallet.get('eth_balance', 0.0))
                new_avg = float(wallet.get('eth_avg_buy_price', 0.0)) if eth_balance > 0 else 0.0
                new_wallet['eth_avg_buy_price'] = new_avg
            session['wallet'] = new_wallet
            if 'trades' not in session:
                session['trades'] = []
            session['trades'].insert(0, {
                'id': len(session['trades']) + 1,
                'user_id': user_id,
                'type': 'sell',
                'symbol': symbol,
                'btc_amount': btc_amount,
                'price': limit_price,
                'fee': fee,
                'timestamp': datetime.datetime.now().isoformat()
            })

    # Check BTC Buy
    if limit_order_btc and limit_order_btc.get('active') and btc_price > 0:
        if btc_price <= float(limit_order_btc['price']):
            trigger_buy(limit_order_btc, 'BTCUSDT', float(limit_order_btc['price']))
            session['limit_order'] = None
            triggered_msg.append('Buy Limit ордер на BTC виконано!')
            session_modified = True

    # Check BTC Sell
    if sell_limit_order_btc and sell_limit_order_btc.get('active') and btc_price > 0:
        if btc_price >= float(sell_limit_order_btc['price']):
            trigger_sell(sell_limit_order_btc, 'BTCUSDT', float(sell_limit_order_btc['price']))
            session['sell_limit_order'] = None
            triggered_msg.append('Sell Limit ордер на BTC виконано!')
            session_modified = True

    # Check ETH Buy
    if limit_order_eth and limit_order_eth.get('active') and eth_price > 0:
        if eth_price <= float(limit_order_eth['price']):
            trigger_buy(limit_order_eth, 'ETHUSDT', float(limit_order_eth['price']))
            session['limit_order_eth'] = None
            triggered_msg.append('Buy Limit ордер на ETH виконано!')
            session_modified = True

    # Check ETH Sell
    if sell_limit_order_eth and sell_limit_order_eth.get('active') and eth_price > 0:
        if eth_price >= float(sell_limit_order_eth['price']):
            trigger_sell(sell_limit_order_eth, 'ETHUSDT', float(sell_limit_order_eth['price']))
            session['sell_limit_order_eth'] = None
            triggered_msg.append('Sell Limit ордер на ETH виконано!')
            session_modified = True

    if session_modified:
        session.modified = True
        return jsonify({'triggered': True, 'message': ' & '.join(triggered_msg)}), 200

    return jsonify({'triggered': False, 'message': 'Цільову ціну не досягнуто.'}), 200

# --- Price Tick API ---

@app.route('/api/exchange/prices', methods=['GET'])
def get_prices():
    return jsonify(latest_prices), 200

@app.route('/api/exchange/ticks-history', methods=['GET'])
@login_required
def get_ticks_history():
    symbol = request.args.get('symbol', 'BTCUSDT')
    if symbol not in ['BTCUSDT', 'ETHUSDT']:
        return jsonify({'error': 'Invalid symbol'}), 400
        
    with state_lock:
        symbol_ticks = [float(t['price']) for t in local_ticks if t.get('symbol') == symbol]
        db_size = 17280
        
    return jsonify({
        'success': True,
        'ticks': symbol_ticks,
        'tick_database_size': db_size
    }), 200

@app.route('/api/exchange/tick-database-size', methods=['POST'])
@login_required
def update_tick_database_size():
    data = request.json or {}
    new_size = data.get('size', 17280)
    return jsonify({
        'success': True,
        'tick_database_size': new_size
    }), 200

@app.route('/')
def home():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
