import os
import json
import time
import urllib.request
import urllib.error
import datetime
import threading
import warnings
import math
from collections import deque
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

# Sync configuration
TICK_SYNC_WRITE_ENABLED = os.environ.get("TICK_SYNC_WRITE_ENABLED", "false").lower() == "true"
print(f"[INFO] TICK_SYNC_WRITE_ENABLED = {TICK_SYNC_WRITE_ENABLED}")

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

# Moving windows for regression analysis (last 50 ticks)
btc_regression_window = deque(maxlen=50)
eth_regression_window = deque(maxlen=50)

latest_regression = {
    "BTCUSDT": {"angle": 0.0, "signal": "НЕЙТРАЛЬНИЙ"},
    "ETHUSDT": {"angle": 0.0, "signal": "НЕЙТРАЛЬНИЙ"}
}

def calculate_regression_angle(prices, tick_size=0.1):
    """
    Обчислює кут нахилу лінії тренду на основі лінійної регресії (МНК)
    для останніх 50 тіків.
    """
    N = len(prices)
    if N < 2:
        return 0.0
    
    # Якщо довжина рівна 50, використовуємо оптимізовану формулу МНК з константним знаменником
    if N == 50:
        sum_y = sum(prices)
        sum_xy = sum(i * p for i, p in enumerate(prices))
        # slope = (2 * sum_xy - 49 * sum_y) / (20825.0 * tick_size)
        slope = (2 * sum_xy - 49.0 * sum_y) / (20825.0 * tick_size)
    else:
        # Загальний випадок МНК для будь-якої іншої довжини N
        sum_x = sum(range(N))
        sum_x2 = sum(i ** 2 for i in range(N))
        sum_y = sum(prices) / tick_size
        sum_xy = sum(i * (p / tick_size) for i, p in enumerate(prices))
        
        denom = N * sum_x2 - sum_x ** 2
        if denom == 0:
            return 0.0
        slope = (N * sum_xy - sum_x * sum_y) / denom

    # arctan(slope) повертає кут в радіанах від -pi/2 до +pi/2, переводимо в градуси (-90 до +90)
    angle_radians = math.atan(slope)
    angle_degrees = math.degrees(angle_radians)
    
    return angle_degrees

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
            if TICK_SYNC_WRITE_ENABLED:
                print(f"[INFO] Uploading {len(to_upload)} unsynced local ticks to Supabase...")
                for i in range(0, len(to_upload), 500):
                    supabase.table("crypto_ticks").insert(to_upload[i:i+500]).execute()
            else:
                print(f"[INFO] TICK_SYNC_WRITE_ENABLED is false. Skipping upload of {len(to_upload)} unsynced ticks to Supabase.")
                
        print("[OK] Startup sync complete.")
    except Exception as e:
        print(f"[ERROR] Error during startup sync: {e}")

# Run startup sync immediately before starting server threads
sync_with_supabase()

# Initialize regression windows from loaded history
for t in local_ticks:
    try:
        p = float(t.get("price", 0.0))
        if p > 0:
            if t.get("symbol") == "BTCUSDT":
                btc_regression_window.append(p)
            elif t.get("symbol") == "ETHUSDT":
                eth_regression_window.append(p)
    except (ValueError, TypeError):
        pass

LIMIT_ORDERS_FILE = os.path.join(DATA_DIR, "limit_orders.json")
BOT_STATE_FILE = os.path.join(DATA_DIR, "bot_state.json")
LOCAL_WALLET_FILE = os.path.join(DATA_DIR, "local_wallet.json")
BOT_WINDOW_SIZES_FILE = os.path.join(DATA_DIR, "bot_window_sizes.json")

def load_local_wallet(user_id):
    if os.path.exists(LOCAL_WALLET_FILE):
        try:
            with open(LOCAL_WALLET_FILE, 'r', encoding='utf-8') as f:
                wallets = json.load(f)
                if user_id in wallets:
                    return wallets[user_id]
        except Exception as e:
            print(f"Error reading local_wallet.json: {e}")
    return {
        'usd_balance': 100.0,
        'btc_balance': 0.0,
        'eth_balance': 0.0,
        'avg_buy_price': 0.0,
        'eth_avg_buy_price': 0.0
    }

def save_local_wallet(user_id, wallet_data):
    wallets = {}
    if os.path.exists(LOCAL_WALLET_FILE):
        try:
            with open(LOCAL_WALLET_FILE, 'r', encoding='utf-8') as f:
                wallets = json.load(f)
        except Exception:
            pass
    clean_wallet = {
        'usd_balance': float(wallet_data.get('usd_balance', 100.0)),
        'btc_balance': float(wallet_data.get('btc_balance', 0.0)),
        'eth_balance': float(wallet_data.get('eth_balance', 0.0)),
        'avg_buy_price': float(wallet_data.get('avg_buy_price', 0.0)),
        'eth_avg_buy_price': float(wallet_data.get('eth_avg_buy_price', 0.0))
    }
    wallets[user_id] = clean_wallet
    try:
        with open(LOCAL_WALLET_FILE, 'w', encoding='utf-8') as f:
            json.dump(wallets, f, indent=2)
    except Exception as e:
        print(f"Error writing local_wallet.json: {e}")

def is_fallback_mode():
    if TICK_SYNC_WRITE_ENABLED:
        return False
    return session.get('use_session_fallback', False)

def get_user_wallet(user_id):
    if supabase and not is_fallback_mode():
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            data = getattr(res, 'data', [])
            if data:
                return data[0]
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
                return new_wallet
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Supabase wallet fetch failed: {str(e)}")
            print(f"Supabase wallet fetch failed, using local fallback: {e}")
            session['use_session_fallback'] = True
            session.modified = True
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    return load_local_wallet(user_id)

def save_user_wallet(user_id, wallet_data):
    if supabase and not is_fallback_mode():
        try:
            update_data = {
                'usd_balance': float(wallet_data['usd_balance']),
                'btc_balance': float(wallet_data['btc_balance']),
                'eth_balance': float(wallet_data['eth_balance']),
                'avg_buy_price': float(wallet_data['avg_buy_price']),
                'eth_avg_buy_price': float(wallet_data['eth_avg_buy_price']),
                'updated_at': datetime.datetime.now().isoformat()
            }
            supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Supabase wallet update failed: {str(e)}")
            print(f"Supabase wallet update failed, using local fallback: {e}")
            session['use_session_fallback'] = True
            session.modified = True
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    save_local_wallet(user_id, wallet_data)
    return True

def bg_get_user_wallet(user_id):
    if supabase:
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            data = getattr(res, 'data', [])
            if data:
                return data[0]
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Background wallet fetch from Supabase failed: {str(e)}")
            print(f"Background wallet fetch from Supabase failed: {e}")
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    return load_local_wallet(user_id)

def bg_save_user_wallet(user_id, wallet_data):
    if supabase:
        try:
            update_data = {
                'usd_balance': float(wallet_data['usd_balance']),
                'btc_balance': float(wallet_data['btc_balance']),
                'eth_balance': float(wallet_data['eth_balance']),
                'avg_buy_price': float(wallet_data['avg_buy_price']),
                'eth_avg_buy_price': float(wallet_data['eth_avg_buy_price']),
                'updated_at': datetime.datetime.now().isoformat()
            }
            supabase.table('wallets').update(update_data).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Background wallet update to Supabase failed: {str(e)}")
            print(f"Background wallet update to Supabase failed: {e}")
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    save_local_wallet(user_id, wallet_data)
    return True

def get_active_limit_orders_for_user(user_id):
    if supabase and not is_fallback_mode():
        try:
            res = supabase.table('limit_orders').select('*').eq('user_id', user_id).eq('active', True).execute()
            return getattr(res, 'data', [])
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Error fetching active limit orders from Supabase: {str(e)}")
            print(f"Error fetching active limit orders from Supabase: {e}")
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    orders = []
    if os.path.exists(LIMIT_ORDERS_FILE):
        try:
            with open(LIMIT_ORDERS_FILE, 'r', encoding='utf-8') as f:
                orders = json.load(f)
        except Exception as e:
            print(f"Error reading limit_orders.json: {e}")
    return [o for o in orders if o.get('user_id') == user_id and o.get('active', True)]

def map_orders_to_keys(orders_list):
    res = {
        'active_limit_order': None,
        'active_sell_limit_order': None,
        'active_limit_order_eth': None,
        'active_sell_limit_order_eth': None
    }
    for o in orders_list:
        symbol = o.get('symbol')
        type_ = o.get('type')
        if symbol == 'BTCUSDT':
            if type_ == 'buy':
                res['active_limit_order'] = o
            elif type_ == 'sell':
                res['active_sell_limit_order'] = o
        elif symbol == 'ETHUSDT':
            if type_ == 'buy':
                res['active_limit_order_eth'] = o
            elif type_ == 'sell':
                res['active_sell_limit_order_eth'] = o
    return res

def add_limit_order_to_db(order_data):
    if supabase and not is_fallback_mode():
        try:
            supabase.table('limit_orders').insert(order_data).execute()
            return True
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Error saving limit order to Supabase: {str(e)}")
            print(f"Error saving limit order to Supabase: {e}")
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    orders = []
    if os.path.exists(LIMIT_ORDERS_FILE):
        try:
            with open(LIMIT_ORDERS_FILE, 'r', encoding='utf-8') as f:
                orders = json.load(f)
        except Exception:
            pass
    orders.append(order_data)
    try:
        with open(LIMIT_ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2)
    except Exception as e:
        print(f"Error writing limit_orders.json: {e}")
    return True

def cancel_limit_order_in_db(user_id, symbol, type_):
    if supabase and not is_fallback_mode():
        try:
            supabase.table('limit_orders').update({'active': False}).eq('user_id', user_id).eq('symbol', symbol).eq('type', type_).eq('active', True).execute()
            return True
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                raise Exception(f"Error canceling limit order in Supabase: {str(e)}")
            print(f"Error canceling limit order in Supabase: {e}")
    if TICK_SYNC_WRITE_ENABLED:
        raise Exception("Supabase is not initialized or database connection failed (TICK_SYNC_WRITE_ENABLED is active)")
    orders = []
    if os.path.exists(LIMIT_ORDERS_FILE):
        try:
            with open(LIMIT_ORDERS_FILE, 'r', encoding='utf-8') as f:
                orders = json.load(f)
        except Exception:
            pass
    for o in orders:
        if o.get('user_id') == user_id and o.get('symbol') == symbol and o.get('type') == type_ and o.get('active', True):
            o['active'] = False
    try:
        with open(LIMIT_ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2)
    except Exception as e:
        print(f"Error writing limit_orders.json: {e}")
    return True

def load_local_trades(user_id):
    LOCAL_TRADES_FILE = os.path.join(DATA_DIR, "local_trades.json")
    if os.path.exists(LOCAL_TRADES_FILE):
        try:
            with open(LOCAL_TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
                return [t for t in trades if t.get('user_id') == user_id]
        except Exception as e:
            print(f"Error reading local_trades.json: {e}")
    return []

def bg_insert_trade(user_id, trade_log):
    if supabase:
        try:
            supabase.table('trades').insert(trade_log).execute()
            return True
        except Exception as e:
            print(f"Background trade log insert to Supabase failed: {e}")
    LOCAL_TRADES_FILE = os.path.join(DATA_DIR, "local_trades.json")
    trades = []
    if os.path.exists(LOCAL_TRADES_FILE):
        try:
            with open(LOCAL_TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
        except Exception:
            pass
    trade_log['id'] = len(trades) + 1
    trades.insert(0, trade_log)
    try:
        with open(LOCAL_TRADES_FILE, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2)
    except Exception as e:
        print(f"Error saving local trades file: {e}")
    return True

def bg_check_limit_orders(user_id, btc_price, eth_price):
    active_orders = []
    if supabase:
        try:
            res = supabase.table('limit_orders').select('*').eq('user_id', user_id).eq('active', True).execute()
            active_orders = getattr(res, 'data', [])
        except Exception as e:
            print(f"Error fetching active limit orders from Supabase in background: {e}")
    else:
        if os.path.exists(LIMIT_ORDERS_FILE):
            try:
                with open(LIMIT_ORDERS_FILE, 'r', encoding='utf-8') as f:
                    all_orders = json.load(f)
                    active_orders = [o for o in all_orders if o.get('user_id') == user_id and o.get('active', True)]
            except Exception:
                pass
    if not active_orders:
        return False
    triggered_any = False
    for order in active_orders:
        symbol = order.get('symbol')
        price_limit = float(order.get('price'))
        btc_amount = float(order.get('btc_amount'))
        fee = float(order.get('fee'))
        usd_amount = float(order.get('usd_amount'))
        order_type = order.get('type')
        order_id = order.get('id')
        current_price = btc_price if symbol == 'BTCUSDT' else eth_price
        if current_price <= 0:
            continue
        triggered = False
        if order_type == 'buy' and current_price <= price_limit:
            triggered = True
        elif order_type == 'sell' and current_price >= price_limit:
            triggered = True
        if triggered:
            wallet = bg_get_user_wallet(user_id)
            usd_balance = float(wallet['usd_balance'])
            btc_balance = float(wallet.get('btc_balance', 0.0))
            eth_balance = float(wallet.get('eth_balance', 0.0))
            avg_buy_price = float(wallet.get('avg_buy_price', 0.0))
            eth_avg_buy_price = float(wallet.get('eth_avg_buy_price', 0.0))
            new_usd = usd_balance
            new_btc = btc_balance
            new_eth = eth_balance
            new_btc_avg = avg_buy_price
            new_eth_avg = eth_avg_buy_price
            if order_type == 'buy':
                if symbol == 'BTCUSDT':
                    new_btc = round(btc_balance + btc_amount, 8)
                    new_btc_avg = ((btc_balance * avg_buy_price) + (btc_amount * price_limit)) / new_btc if new_btc > 0 else 0.0
                else:
                    new_eth = round(eth_balance + btc_amount, 8)
                    new_eth_avg = ((eth_balance * eth_avg_buy_price) + (btc_amount * price_limit)) / new_eth if new_eth > 0 else 0.0
            else:
                new_usd = usd_balance + (usd_amount - fee)
                if symbol == 'BTCUSDT':
                    new_btc_avg = avg_buy_price if new_btc > 0 else 0.0
                else:
                    new_eth_avg = eth_avg_buy_price if new_eth > 0 else 0.0
            updated_wallet = {
                'usd_balance': new_usd,
                'btc_balance': new_btc,
                'eth_balance': new_eth,
                'avg_buy_price': new_btc_avg,
                'eth_avg_buy_price': new_eth_avg
            }
            bg_save_user_wallet(user_id, updated_wallet)
            if supabase:
                try:
                    supabase.table('limit_orders').update({'active': False}).eq('id', order_id).execute()
                except Exception as e:
                    print(f"Error marking order as executed in Supabase: {e}")
            else:
                if os.path.exists(LIMIT_ORDERS_FILE):
                    try:
                        with open(LIMIT_ORDERS_FILE, 'r', encoding='utf-8') as f:
                            all_orders = json.load(f)
                        for o in all_orders:
                            if o.get('id') == order_id:
                                o['active'] = False
                        with open(LIMIT_ORDERS_FILE, 'w', encoding='utf-8') as f:
                            json.dump(all_orders, f, indent=2)
                    except Exception:
                        pass
            trade_log = {
                'user_id': user_id,
                'type': order_type,
                'symbol': symbol,
                'btc_amount': btc_amount,
                'price': price_limit,
                'fee': fee,
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            }
            bg_insert_trade(user_id, trade_log)
            triggered_any = True
    return triggered_any

def get_bot_window_size(user_id, symbol):
    if os.path.exists(BOT_WINDOW_SIZES_FILE):
        try:
            with open(BOT_WINDOW_SIZES_FILE, 'r', encoding='utf-8') as f:
                sizes = json.load(f)
                key = f"{user_id}_{symbol}"
                return sizes.get(key, 1500)
        except Exception:
            pass
    return 1500

def save_bot_window_size(user_id, symbol, size):
    sizes = {}
    if os.path.exists(BOT_WINDOW_SIZES_FILE):
        try:
            with open(BOT_WINDOW_SIZES_FILE, 'r', encoding='utf-8') as f:
                sizes = json.load(f)
        except Exception:
            pass
    key = f"{user_id}_{symbol}"
    sizes[key] = int(size)
    try:
        with open(BOT_WINDOW_SIZES_FILE, 'w', encoding='utf-8') as f:
            json.dump(sizes, f, indent=2)
    except Exception as e:
        print(f"Error saving bot window size: {e}")

def bg_get_bot_state(user_id, symbol):
    if supabase:
        try:
            res = supabase.table('bot_states').select('*').eq('user_id', user_id).eq('symbol', symbol).execute()
            data = getattr(res, 'data', [])
            if data:
                return data[0]
            else:
                initial_state = {
                    'user_id': user_id,
                    'symbol': symbol,
                    'usd_balance': 100.0,
                    'asset_balance': 0.0,
                    'trade_state': 'idle',
                    'trade_sub_state': 'waiting_below_13',
                    'buy_price': 0.0
                }
                supabase.table('bot_states').insert(initial_state).execute()
                return initial_state
        except Exception as e:
            print(f"Error fetching bot state from Supabase: {e}")
    if os.path.exists(BOT_STATE_FILE):
        try:
            with open(BOT_STATE_FILE, 'r', encoding='utf-8') as f:
                bot_states = json.load(f)
                key = f"{user_id}_{symbol}"
                if key in bot_states:
                    return bot_states[key]
        except Exception as e:
            print(f"Error reading bot_state.json: {e}")
    return {
        'user_id': user_id,
        'symbol': symbol,
        'usd_balance': 100.0,
        'asset_balance': 0.0,
        'trade_state': 'idle',
        'trade_sub_state': 'waiting_below_13',
        'buy_price': 0.0
    }

def bg_save_bot_state(user_id, symbol, state_data):
    if supabase:
        try:
            update_data = {
                'usd_balance': float(state_data['usd_balance']),
                'asset_balance': float(state_data['asset_balance']),
                'trade_state': state_data['trade_state'],
                'trade_sub_state': state_data['trade_sub_state'],
                'buy_price': float(state_data['buy_price']),
                'updated_at': datetime.datetime.now().isoformat()
            }
            supabase.table('bot_states').upsert({
                'user_id': user_id,
                'symbol': symbol,
                **update_data
            }, on_conflict='user_id,symbol').execute()
            return True
        except Exception as e:
            print(f"Error saving bot state to Supabase: {e}")
    bot_states = {}
    if os.path.exists(BOT_STATE_FILE):
        try:
            with open(BOT_STATE_FILE, 'r', encoding='utf-8') as f:
                bot_states = json.load(f)
        except Exception:
            pass
    key = f"{user_id}_{symbol}"
    bot_states[key] = {
        'user_id': user_id,
        'symbol': symbol,
        'usd_balance': float(state_data['usd_balance']),
        'asset_balance': float(state_data['asset_balance']),
        'trade_state': state_data['trade_state'],
        'trade_sub_state': state_data['trade_sub_state'],
        'buy_price': float(state_data['buy_price'])
    }
    try:
        with open(BOT_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(bot_states, f, indent=2)
    except Exception as e:
        print(f"Error writing bot_state.json: {e}")
    return True

def bg_get_bot_trades(user_id, symbol):
    if supabase:
        try:
            res = supabase.table('bot_trades').select('*').eq('user_id', user_id).eq('symbol', symbol).order('timestamp', desc=True).execute()
            return getattr(res, 'data', [])
        except Exception as e:
            print(f"Error fetching bot trades from Supabase: {e}")
    BOT_TRADES_FILE = os.path.join(DATA_DIR, "bot_trades.json")
    if os.path.exists(BOT_TRADES_FILE):
        try:
            with open(BOT_TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
                return [t for t in trades if t.get('user_id') == user_id and t.get('symbol') == symbol]
        except Exception as e:
            print(f"Error reading bot_trades.json: {e}")
    return []

def bg_insert_bot_trade(user_id, symbol, trade_log):
    if supabase:
        try:
            supabase.table('bot_trades').insert({
                'user_id': user_id,
                'symbol': symbol,
                'type': trade_log['type'],
                'amount': float(trade_log['amount']),
                'price': float(trade_log['price']),
                'fee': float(trade_log['fee']),
                'total': float(trade_log['total']),
                'timestamp': trade_log.get('timestamp', datetime.datetime.now().isoformat())
            }).execute()
            return True
        except Exception as e:
            print(f"Error inserting bot trade to Supabase: {e}")
    BOT_TRADES_FILE = os.path.join(DATA_DIR, "bot_trades.json")
    trades = []
    if os.path.exists(BOT_TRADES_FILE):
        try:
            with open(BOT_TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
        except Exception:
            pass
    trade_log['id'] = len(trades) + 1
    trade_log['user_id'] = user_id
    trade_log['symbol'] = symbol
    trades.insert(0, trade_log)
    try:
        with open(BOT_TRADES_FILE, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2)
    except Exception as e:
        print(f"Error writing bot_trades.json: {e}")
    return True

def bg_clear_bot_trades(user_id, symbol):
    if supabase:
        try:
            supabase.table('bot_trades').delete().eq('user_id', user_id).eq('symbol', symbol).execute()
            return True
        except Exception as e:
            print(f"Error clearing bot trades in Supabase: {e}")
    BOT_TRADES_FILE = os.path.join(DATA_DIR, "bot_trades.json")
    if os.path.exists(BOT_TRADES_FILE):
        try:
            with open(BOT_TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            filtered = [t for t in trades if not (t.get('user_id') == user_id and t.get('symbol') == symbol)]
            with open(BOT_TRADES_FILE, 'w', encoding='utf-8') as f:
                json.dump(filtered, f, indent=2)
        except Exception as e:
            print(f"Error clearing local bot trades: {e}")
    return True

def get_all_active_users():
    if supabase:
        try:
            res = supabase.table('wallets').select('user_id').execute()
            data = getattr(res, 'data', [])
            return list(set(d['user_id'] for d in data if 'user_id' in d))
        except Exception as e:
            print(f"Error fetching active users from Supabase: {e}")
    users = []
    if os.path.exists(LOCAL_WALLET_FILE):
        try:
            with open(LOCAL_WALLET_FILE, 'r', encoding='utf-8') as f:
                wallets = json.load(f)
                users = list(wallets.keys())
        except Exception:
            pass
    if not users:
        users = ['2bea02ac-19b7-4614-adb6-0d1cf8403277']
    return users

def run_bot_trading_strategy_on_server(user_id, symbol, current_price, ticks_list, window_size=1500):
    if len(ticks_list) < 2 or len(ticks_list) < window_size:
        return
    window_ticks = ticks_list[-window_size:]
    max_price = max(window_ticks)
    min_price = min(window_ticks)
    if max_price <= min_price:
        return
    diff = max_price - min_price
    val87 = min_price + 0.87 * diff
    val75 = min_price + 0.75 * diff
    val25 = min_price + 0.25 * diff
    val13 = min_price + 0.13 * diff
    
    # Calculate 24h average for BTC buy/sell zone check
    avg24h = None
    if len(ticks_list) > 0:
        max24h = max(ticks_list)
        min24h = min(ticks_list)
        avg24h = (max24h + min24h) / 2.0

    s = bg_get_bot_state(user_id, symbol)
    fee_rate = 0.001
    usd = float(s['usd_balance'])
    asset = float(s['asset_balance'])
    trade_state = s['trade_state']
    trade_sub_state = s['trade_sub_state']
    buy_price = float(s['buy_price'])
    state_changed = False
    if trade_state == 'idle':
        if trade_sub_state == 'deactivated_waiting_above_25':
            if current_price >= val25:
                trade_sub_state = 'waiting_below_13'
                state_changed = True
        elif trade_sub_state != 'triggered_below_13':
            if current_price <= val13:
                trade_sub_state = 'triggered_below_13'
                state_changed = True
        else:
            if current_price <= min_price:
                trade_sub_state = 'deactivated_waiting_above_25'
                state_changed = True
            elif current_price >= val25:
                # BTC buy check: must be in buy zone (green: current_price < avg24h)
                is_btc = (symbol == 'BTCUSDT')
                in_buy_zone = True
                if is_btc and avg24h is not None:
                    in_buy_zone = (current_price < avg24h)

                if in_buy_zone:
                    if usd > 0:
                        total_cost = usd
                        asset = total_cost / (current_price * (1.0 + fee_rate))
                        fee = asset * current_price * fee_rate
                        usd = 0.0
                        trade_state = 'holding'
                        trade_sub_state = 'waiting_75_rising'
                        buy_price = current_price
                        state_changed = True
                        trade_log = {
                            'type': 'buy',
                            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
                            'amount': asset,
                            'price': current_price,
                            'fee': fee,
                            'total': total_cost
                        }
                        bg_insert_bot_trade(user_id, symbol, trade_log)
                    else:
                        trade_sub_state = 'waiting_below_13'
                        state_changed = True
    elif trade_state == 'holding':
        if trade_sub_state in ('waiting_75', 'waiting_75_rising'):
            if current_price >= val75:
                if asset > 0:
                    estimated_revenue = asset * current_price * (1.0 - fee_rate)
                    cost_of_purchase = asset * buy_price * (1.0 + fee_rate)
                    if estimated_revenue > cost_of_purchase:
                        trade_sub_state = 'waiting_75_falling'
                        state_changed = True
                    else:
                        trade_sub_state = 'waiting_breakeven'
                        state_changed = True
        elif trade_sub_state == 'waiting_75_falling':
            if current_price < val75:
                # BTC sell check: must be in sell zone (red: current_price >= avg24h)
                is_btc = (symbol == 'BTCUSDT')
                in_sell_zone = True
                if is_btc and avg24h is not None:
                    in_sell_zone = (current_price >= avg24h)

                if in_sell_zone and asset > 0:
                    estimated_revenue = asset * current_price * (1.0 - fee_rate)
                    usd = estimated_revenue
                    fee = asset * current_price * fee_rate
                    trade_log = {
                        'type': 'sell',
                        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
                        'amount': asset,
                        'price': current_price,
                        'fee': fee,
                        'total': estimated_revenue
                    }
                    bg_insert_bot_trade(user_id, symbol, trade_log)
                    asset = 0.0
                    trade_state = 'idle'
                    trade_sub_state = 'waiting_below_13'
                    buy_price = 0.0
                    state_changed = True
            elif current_price >= val87:
                if asset > 0:
                    estimated_revenue = asset * current_price * (1.0 - fee_rate)
                    cost_of_purchase = asset * buy_price * (1.0 + fee_rate)
                    if estimated_revenue > cost_of_purchase:
                        trade_sub_state = 'waiting_87_falling'
                        state_changed = True
                    else:
                        trade_sub_state = 'waiting_breakeven'
                        state_changed = True
        elif trade_sub_state == 'waiting_87_falling':
            if current_price < val87:
                # BTC sell check: must be in sell zone (red: current_price >= avg24h)
                is_btc = (symbol == 'BTCUSDT')
                in_sell_zone = True
                if is_btc and avg24h is not None:
                    in_sell_zone = (current_price >= avg24h)

                if in_sell_zone and asset > 0:
                    estimated_revenue = asset * current_price * (1.0 - fee_rate)
                    usd = estimated_revenue
                    fee = asset * current_price * fee_rate
                    trade_log = {
                        'type': 'sell',
                        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
                        'amount': asset,
                        'price': current_price,
                        'fee': fee,
                        'total': estimated_revenue
                    }
                    bg_insert_bot_trade(user_id, symbol, trade_log)
                    asset = 0.0
                    trade_state = 'idle'
                    trade_sub_state = 'waiting_below_13'
                    buy_price = 0.0
                    state_changed = True
        elif trade_sub_state == 'waiting_breakeven':
            if current_price >= buy_price * 1.003:
                # BTC sell check: must be in sell zone (red: current_price >= avg24h)
                is_btc = (symbol == 'BTCUSDT')
                in_sell_zone = True
                if is_btc and avg24h is not None:
                    in_sell_zone = (current_price >= avg24h)

                if in_sell_zone and asset > 0:
                    estimated_revenue = asset * current_price * (1.0 - fee_rate)
                    usd = estimated_revenue
                    fee = asset * current_price * fee_rate
                    trade_log = {
                        'type': 'sell',
                        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
                        'amount': asset,
                        'price': current_price,
                        'fee': fee,
                        'total': estimated_revenue
                    }
                    bg_insert_bot_trade(user_id, symbol, trade_log)
                    asset = 0.0
                    trade_state = 'idle'
                    trade_sub_state = 'waiting_below_13'
                    buy_price = 0.0
                    state_changed = True
    if state_changed:
        s['usd_balance'] = usd
        s['asset_balance'] = asset
        s['trade_state'] = trade_state
        s['trade_sub_state'] = trade_sub_state
        s['buy_price'] = buy_price
        bg_save_bot_state(user_id, symbol, s)

def fetch_binance_prices_loop():
    """Background loop to fetch prices every 5s, save locally, run bot strategy & check limit orders, and sync to Supabase hourly"""
    loop_count = 0
    global local_ticks, unsynced_ticks, latest_regression
    while True:
        try:
            # 1. Fetch BTC price
            btc_url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            req = urllib.request.Request(btc_url, headers={'User-Agent': 'Mozilla/5.0'})
            btc_price = 0.0
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                btc_price = float(data['price'])
                latest_prices["BTC"] = btc_price
 
            # 2. Fetch ETH price
            eth_url = "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
            req = urllib.request.Request(eth_url, headers={'User-Agent': 'Mozilla/5.0'})
            eth_price = 0.0
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
                
                # Append to regression windows
                btc_regression_window.append(btc_price)
                eth_regression_window.append(eth_price)
                
                if TICK_SYNC_WRITE_ENABLED:
                    unsynced_ticks.append(new_btc)
                    unsynced_ticks.append(new_eth)
                
                # Keep local history capped at 17280 per symbol
                btc_list = [t for t in local_ticks if t["symbol"] == "BTCUSDT"][-17280:]
                eth_list = [t for t in local_ticks if t["symbol"] == "ETHUSDT"][-17280:]
                local_ticks = btc_list + eth_list
                
                try:
                    with open(TICKS_FILE, 'w', encoding='utf-8') as f:
                        json.dump(local_ticks, f, indent=2)
                except Exception as file_err:
                    print(f"Error saving local ticks: {file_err}")

            # 2.2 Calculate regression angles and signals
            with state_lock:
                btc_window_list = list(btc_regression_window)
                eth_window_list = list(eth_regression_window)

            if len(btc_window_list) == 50:
                btc_angle = calculate_regression_angle(btc_window_list, tick_size=0.1)
                btc_sig = "НЕЙТРАЛЬНИЙ"
                if btc_angle > 45:
                    btc_sig = "ЛОНГ (LONG)"
                    print(f"[{current_time}] [SIGNAL] BTCUSDT regression angle: {btc_angle:.2f}° -> ЛОНГ (LONG)")
                elif btc_angle < -45:
                    btc_sig = "ШОРТ (SHORT)"
                    print(f"[{current_time}] [SIGNAL] BTCUSDT regression angle: {btc_angle:.2f}° -> ШОРТ (SHORT)")
                latest_regression["BTCUSDT"] = {"angle": btc_angle, "signal": btc_sig}
            
            if len(eth_window_list) == 50:
                eth_angle = calculate_regression_angle(eth_window_list, tick_size=0.1)
                eth_sig = "НЕЙТРАЛЬНИЙ"
                if eth_angle > 45:
                    eth_sig = "ЛОНГ (LONG)"
                    print(f"[{current_time}] [SIGNAL] ETHUSDT regression angle: {eth_angle:.2f}° -> ЛОНГ (LONG)")
                elif eth_angle < -45:
                    eth_sig = "ШОРТ (SHORT)"
                    print(f"[{current_time}] [SIGNAL] ETHUSDT regression angle: {eth_angle:.2f}° -> ШОРТ (SHORT)")
                latest_regression["ETHUSDT"] = {"angle": eth_angle, "signal": eth_sig}

            # 2.5 Run Background checks for Limit Orders & Bot Trading Strategies for all active users
            if btc_price > 0 and eth_price > 0:
                active_users = get_all_active_users()
                with state_lock:
                    btc_history = [float(t['price']) for t in local_ticks if t["symbol"] == "BTCUSDT"]
                    eth_history = [float(t['price']) for t in local_ticks if t["symbol"] == "ETHUSDT"]
                
                for user_id in active_users:
                    # A. Check and execute limit orders
                    try:
                        bg_check_limit_orders(user_id, btc_price, eth_price)
                    except Exception as limit_err:
                        print(f"[ERROR] Background limit order execution failed for {user_id}: {limit_err}")
                        
                    # B. Evaluate bot autotrading strategy
                    try:
                        btc_window = get_bot_window_size(user_id, 'BTCUSDT')
                        run_bot_trading_strategy_on_server(user_id, 'BTCUSDT', btc_price, btc_history, btc_window)
                    except Exception as bot_err:
                        print(f"[ERROR] Background BTC bot strategy failed for {user_id}: {bot_err}")
                        
                    try:
                        eth_window = get_bot_window_size(user_id, 'ETHUSDT')
                        run_bot_trading_strategy_on_server(user_id, 'ETHUSDT', eth_price, eth_history, eth_window)
                    except Exception as bot_err:
                        print(f"[ERROR] Background ETH bot strategy failed for {user_id}: {bot_err}")

            # 3. Check hourly sync (5s * 720 = 3600s = 1 hour)
            loop_count += 1
            if loop_count >= 720:
                loop_count = 0
                if supabase and unsynced_ticks and TICK_SYNC_WRITE_ENABLED:
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
            session['use_session_fallback'] = False
            session.modified = True
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
        print(f"[INFO] Supabase auth failed ({e})")
        return jsonify({'error': 'Неправильний пароль або помилка авторизації'}), 401

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
    session['user_id'] = '2bea02ac-19b7-4614-adb6-0d1cf8403277'
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
    active_orders = get_active_limit_orders_for_user(user_id)
    mapped_orders = map_orders_to_keys(active_orders)
    
    # 1. Try Supabase
    if supabase and not is_fallback_mode():
        try:
            res = supabase.table('wallets').select('*').eq('user_id', user_id).execute()
            data = getattr(res, 'data', [])
            if data:
                wallet = data[0]
                has_eth = 'eth_balance' in wallet
                has_symbol = True
                if has_eth:
                    try:
                        supabase.table('trades').select('symbol').limit(1).execute()
                    except Exception as schema_err:
                        print(f"[WARNING] Database schema is missing symbol column in trades: {schema_err}")
                        has_symbol = False
                
                if not has_eth or not has_symbol:
                    if TICK_SYNC_WRITE_ENABLED:
                        return jsonify({'error': 'Database schema is incomplete (missing eth_balance or trades.symbol)'}), 500
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
                        **mapped_orders
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
                    **mapped_orders
                }), 200
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                return jsonify({'error': f'Database connection error: {str(e)}'}), 503
            print(f"Error fetching wallet from Supabase: {str(e)}")
            session['use_session_fallback'] = True
            session.modified = True
            
    if TICK_SYNC_WRITE_ENABLED:
        return jsonify({'error': 'Supabase connection failed (TICK_SYNC_WRITE_ENABLED is active)'}), 503
        
    # 2. Fallback to local persistent wallet
    wallet_data = load_local_wallet(user_id)
    return jsonify({
        **wallet_data,
        **mapped_orders
    }), 200

@app.route('/api/exchange/history', methods=['GET'])
@login_required
def exchange_history():
    user_id = session.get('user_id')
    
    if supabase and not is_fallback_mode():
        try:
            res = supabase.table('trades').select('*').eq('user_id', user_id).order('timestamp', desc=True).execute()
            data = getattr(res, 'data', [])
            return jsonify(data), 200
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                return jsonify({'error': f'Database connection error: {str(e)}'}), 503
            print(f"Error fetching history from Supabase: {str(e)}")
            session['use_session_fallback'] = True
            session.modified = True
            
    if TICK_SYNC_WRITE_ENABLED:
        return jsonify({'error': 'Supabase connection failed (TICK_SYNC_WRITE_ENABLED is active)'}), 503
        
    # Fallback to local persistent trades
    return jsonify(load_local_trades(user_id)), 200

def is_in_sell_zone(symbol):
    """
    Checks if the latest price of the symbol is in the 24h sell zone (>= avg_24h).
    Calculated using Supabase database with 24-hour time constraint.
    """
    global local_ticks
    symbol_ticks = []
    
    limit_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    limit_time = limit_dt.isoformat()
    
    if supabase and not is_fallback_mode():
        try:
            res = supabase.table('crypto_ticks').select('price').eq('symbol', symbol).gte('created_at', limit_time).order('created_at', desc=True).limit(17280).execute()
            db_ticks = getattr(res, 'data', [])
            symbol_ticks = [float(t['price']) for t in db_ticks]
        except Exception as e:
            print(f"Error fetching ticks from Supabase for is_in_sell_zone: {e}")
            
    if not symbol_ticks:
        with state_lock:
            symbol_ticks = [
                float(t['price']) for t in local_ticks 
                if t.get('symbol') == symbol and datetime.datetime.fromisoformat(t.get('created_at').replace('Z', '+00:00')) >= limit_dt
            ]
            
    if not symbol_ticks:
        return False
        
    max_24h = max(symbol_ticks)
    min_24h = min(symbol_ticks)
    avg_24h = (max_24h + min_24h) / 2.0
    
    # Get current price
    current_price = 0.0
    if symbol == 'BTCUSDT':
        current_price = latest_prices.get('BTC', 0.0)
    elif symbol == 'ETHUSDT':
        current_price = latest_prices.get('ETH', 0.0)
        
    if current_price <= 0.0:
        return False
        
    return current_price >= avg_24h

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

    if trade_type == 'buy' and is_in_sell_zone(symbol):
        return jsonify({'error': 'Купівля заборонена: поточний курс перебуває в зоні продажу'}), 400

    fee_rate = 0.001  # 0.1% fee
    fee = btc_amount * price * fee_rate
    total_usd_value = btc_amount * price
    
    # Load wallet
    wallet = get_user_wallet(user_id)
    usd_balance = float(wallet['usd_balance'])
    
    updated_wallet = dict(wallet)
    
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
            
            updated_wallet.update({
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
            
            updated_wallet.update({
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
            
            updated_wallet.update({
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
            
            updated_wallet.update({
                'usd_balance': new_usd_balance,
                'eth_balance': new_eth_balance,
                'eth_avg_buy_price': new_avg_buy_price
            })
        else:
            return jsonify({'error': 'Invalid trade type'}), 400
    else:
        return jsonify({'error': 'Unsupported symbol'}), 400

    # Save wallet
    save_user_wallet(user_id, updated_wallet)
    
    # Save trade history
    trade_log = {
        'user_id': user_id,
        'type': trade_type,
        'symbol': symbol,
        'btc_amount': btc_amount,
        'price': price,
        'fee': fee,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    }
    bg_insert_trade(user_id, trade_log)
    
    check_wallet_invariants(updated_wallet)
    
    return jsonify({
        'usd_balance': updated_wallet['usd_balance'],
        'btc_balance': updated_wallet.get('btc_balance', 0.0),
        'eth_balance': updated_wallet.get('eth_balance', 0.0),
        'avg_buy_price': updated_wallet.get('avg_buy_price', 0.0),
        'eth_avg_buy_price': updated_wallet.get('eth_avg_buy_price', 0.0),
        'message': 'Угоду успішно виконано!'
    }), 200

@app.route('/api/exchange/reset', methods=['POST'])
@login_required
def exchange_reset():
    user_id = session.get('user_id')
    
    # Deactivate active limit orders
    if supabase and not is_fallback_mode():
        try:
            supabase.table('limit_orders').update({'active': False}).eq('user_id', user_id).execute()
        except Exception as e:
            if TICK_SYNC_WRITE_ENABLED:
                return jsonify({'error': f'Database connection error: {str(e)}'}), 503
            print(f"Error resetting limit orders in Supabase: {e}")
    else:
        if TICK_SYNC_WRITE_ENABLED:
            return jsonify({'error': 'Supabase connection failed (TICK_SYNC_WRITE_ENABLED is active)'}), 503
        if os.path.exists(LIMIT_ORDERS_FILE):
            try:
                with open(LIMIT_ORDERS_FILE, 'r', encoding='utf-8') as f:
                    all_orders = json.load(f)
                for o in all_orders:
                    if o.get('user_id') == user_id:
                        o['active'] = False
                with open(LIMIT_ORDERS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_orders, f, indent=2)
            except Exception:
                pass

    # Reset main wallet balance and trades
    if supabase and not is_fallback_mode():
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
            if TICK_SYNC_WRITE_ENABLED:
                return jsonify({'error': f'Database connection error: {str(e)}'}), 503
            print(f"Supabase reset failed: {str(e)}")
            
    if TICK_SYNC_WRITE_ENABLED:
        return jsonify({'error': 'Supabase connection failed (TICK_SYNC_WRITE_ENABLED is active)'}), 503
            
    # Reset local persistent fallback
    reset_wallet = {
        'usd_balance': 100.0,
        'btc_balance': 0.0,
        'eth_balance': 0.0,
        'avg_buy_price': 0.0,
        'eth_avg_buy_price': 0.0
    }
    save_local_wallet(user_id, reset_wallet)
    
    LOCAL_TRADES_FILE = os.path.join(DATA_DIR, "local_trades.json")
    if os.path.exists(LOCAL_TRADES_FILE):
        try:
            with open(LOCAL_TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            filtered = [t for t in trades if t.get('user_id') != user_id]
            with open(LOCAL_TRADES_FILE, 'w', encoding='utf-8') as f:
                json.dump(filtered, f, indent=2)
        except Exception:
            pass

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
        'message': 'Баланс успішно скинуто! (Очищено в локальному кеші)'
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

    if order_type == 'buy' and is_in_sell_zone(symbol):
        return jsonify({'error': 'Купівля заборонена: поточний курс перебуває в зоні продажу'}), 400

    fee_rate = 0.001
    fee = btc_amount * price * fee_rate

    # Load current wallet state
    wallet = get_user_wallet(user_id)
    usd_balance = float(wallet['usd_balance'])
    btc_balance = float(wallet.get('btc_balance', 0.0))
    eth_balance = float(wallet.get('eth_balance', 0.0))
    
    # Check if there is already an active order of this type/symbol
    active_orders = get_active_limit_orders_for_user(user_id)
    mapped_orders = map_orders_to_keys(active_orders)
    
    existing_key = None
    if symbol == 'BTCUSDT':
        existing_key = 'active_limit_order' if order_type == 'buy' else 'active_sell_limit_order'
    else:
        existing_key = 'active_limit_order_eth' if order_type == 'buy' else 'active_sell_limit_order_eth'
        
    if mapped_orders[existing_key] is not None:
        return jsonify({'error': f'Вже існує активний ордер на {order_type} для {symbol}'}), 400

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

    # Write back updates to wallet
    updated_wallet = {
        'usd_balance': new_usd,
        'btc_balance': new_btc,
        'eth_balance': new_eth,
        'avg_buy_price': float(wallet.get('avg_buy_price', 0.0)),
        'eth_avg_buy_price': float(wallet.get('eth_avg_buy_price', 0.0))
    }
    save_user_wallet(user_id, updated_wallet)

    # Insert limit order
    import uuid
    order_data = {
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'symbol': symbol,
        'type': order_type,
        'btc_amount': btc_amount,
        'price': price,
        'fee': fee,
        'usd_amount': usd_amount,
        'active': True,
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    }
    add_limit_order_to_db(order_data)

    # Get updated list of active limit orders to return
    updated_active_orders = get_active_limit_orders_for_user(user_id)
    mapped_updated = map_orders_to_keys(updated_active_orders)

    return jsonify({
        **mapped_updated,
        'message': 'Лімітний ордер успішно розміщено!'
    }), 200

@app.route('/api/exchange/limit-order/cancel', methods=['POST'])
@login_required
def cancel_limit_order():
    user_id = session.get('user_id')
    data = request.json or {}
    order_type = data.get('type', 'buy')
    symbol = data.get('symbol', 'BTCUSDT')

    # Load active orders
    active_orders = get_active_limit_orders_for_user(user_id)
    mapped_orders = map_orders_to_keys(active_orders)
    
    existing_key = None
    if symbol == 'BTCUSDT':
        existing_key = 'active_limit_order' if order_type == 'buy' else 'active_sell_limit_order'
    else:
        existing_key = 'active_limit_order_eth' if order_type == 'buy' else 'active_sell_limit_order_eth'
        
    order = mapped_orders[existing_key]

    if not order:
        return jsonify({'error': f'Немає активних лімітних ордерів на {order_type} для {symbol}'}), 400

    # Load current wallet state
    wallet = get_user_wallet(user_id)
    usd_balance = float(wallet['usd_balance'])
    btc_balance = float(wallet.get('btc_balance', 0.0))
    eth_balance = float(wallet.get('eth_balance', 0.0))

    if order_type == 'buy':
        new_usd = usd_balance + float(order['usd_amount']) + float(order['fee'])
        new_btc = btc_balance
        new_eth = eth_balance
    else:
        new_usd = usd_balance
        if symbol == 'BTCUSDT':
            new_btc = round(btc_balance + float(order['btc_amount']), 8)
            new_eth = eth_balance
        else:
            new_eth = round(eth_balance + float(order['btc_amount']), 8)
            new_btc = btc_balance

    # Save wallet
    updated_wallet = {
        'usd_balance': new_usd,
        'btc_balance': new_btc,
        'eth_balance': new_eth,
        'avg_buy_price': float(wallet.get('avg_buy_price', 0.0)),
        'eth_avg_buy_price': float(wallet.get('eth_avg_buy_price', 0.0))
    }
    save_user_wallet(user_id, updated_wallet)

    # Deactivate the order
    cancel_limit_order_in_db(user_id, symbol, order_type)

    return jsonify({'message': 'Ордер успішно скасовано, кошти повернуто.'}), 200

@app.route('/api/exchange/limit-order/check', methods=['POST'])
@login_required
def check_limit_order():
    user_id = session.get('user_id')
    btc_price = latest_prices.get("BTC", 0.0)
    eth_price = latest_prices.get("ETH", 0.0)
    triggered = bg_check_limit_orders(user_id, btc_price, eth_price)
    if triggered:
        return jsonify({'triggered': True, 'message': 'Ордери перевірено та виконано!'}), 200
    return jsonify({'triggered': False, 'message': 'Цільову ціну не досягнуто.'}), 200

@app.route('/api/exchange/bot-state', methods=['GET'])
@login_required
def get_bot_state_api():
    user_id = session.get('user_id')
    symbol = request.args.get('symbol', 'BTCUSDT')
    if symbol not in ['BTCUSDT', 'ETHUSDT']:
        return jsonify({'error': 'Invalid symbol'}), 400
        
    s = bg_get_bot_state(user_id, symbol)
    trades = bg_get_bot_trades(user_id, symbol)
    window_size = get_bot_window_size(user_id, symbol)
    
    reg = latest_regression.get(symbol, {"angle": 0.0, "signal": "НЕЙТРАЛЬНИЙ"})
    
    return jsonify({
        'usd': float(s['usd_balance']),
        'asset': float(s['asset_balance']),
        'tradeState': s['trade_state'],
        'tradeSubState': s['trade_sub_state'],
        'buyPrice': float(s['buy_price']),
        'trades': trades,
        'window_size': window_size,
        'regression_angle': reg["angle"],
        'regression_signal': reg["signal"]
    }), 200

@app.route('/api/exchange/bot-reset', methods=['POST'])
@login_required
def reset_bot_api():
    user_id = session.get('user_id')
    data = request.json or {}
    symbol = data.get('symbol', 'BTCUSDT')
    if symbol not in ['BTCUSDT', 'ETHUSDT']:
        return jsonify({'error': 'Invalid symbol'}), 400
        
    # Reset state
    initial_state = {
        'user_id': user_id,
        'symbol': symbol,
        'usd_balance': 100.0,
        'asset_balance': 0.0,
        'trade_state': 'idle',
        'trade_sub_state': 'waiting_below_13',
        'buy_price': 0.0
    }
    bg_save_bot_state(user_id, symbol, initial_state)
    bg_clear_bot_trades(user_id, symbol)
    
    return jsonify({
        'success': True,
        'message': f'Баланс бота для {symbol} успішно скинуто!'
    }), 200

@app.route('/api/exchange/bot-window-size', methods=['POST'])
@login_required
def update_bot_window_size():
    user_id = session.get('user_id')
    data = request.json or {}
    symbol = data.get('symbol', 'BTCUSDT')
    size = data.get('size', 1500)
    try:
        size = int(size)
        if size < 2:
            return jsonify({'error': 'Invalid window size'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid window size format'}), 400
        
    save_bot_window_size(user_id, symbol, size)
    return jsonify({'success': True, 'window_size': size}), 200

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
        
    symbol_ticks = []
    limit_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    limit_time = limit_dt.isoformat()
    
    if supabase and not is_fallback_mode():
        try:
            res = supabase.table('crypto_ticks').select('price').eq('symbol', symbol).gte('created_at', limit_time).order('created_at', desc=True).limit(17280).execute()
            db_ticks = getattr(res, 'data', [])
            symbol_ticks = [float(t['price']) for t in reversed(db_ticks)]
        except Exception as e:
            print(f"Error fetching ticks from Supabase: {str(e)}")
            
    if not symbol_ticks:
        with state_lock:
            symbol_ticks = [
                float(t['price']) for t in local_ticks 
                if t.get('symbol') == symbol and datetime.datetime.fromisoformat(t.get('created_at').replace('Z', '+00:00')) >= limit_dt
            ]
            
    return jsonify({
        'success': True,
        'ticks': symbol_ticks,
        'tick_database_size': 17280
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
