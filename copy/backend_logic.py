# -*- coding: utf-8 -*-
"""
Kronos Python Backend Logic for:
- Background Thread for BTC Price Tick Accumulation (polling Binance API)
- Local File Persistence and Supabase sync for price history ticks
- Flask endpoints for exchange history and tick history limits
"""

import os
import time
import json
import urllib.request
import threading
import datetime
from flask import jsonify, request, session

# ==========================================
# 1. DATABASE & FILE PATH DEFINITIONS
# ==========================================
# File where accumulated ticks are stored
TICKS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
    'data', 
    'ticks_history.json'
)

# Defaults
tick_database_size = 17280  # Max size of raw tick storage database
ticks_list = []             # Array holding raw price points (up to tick_database_size)
ticks_lock = threading.Lock()

# Mock Supabase integration toggle (Checks if configured in your project)
supabase = None  # Or initialize using: create_client(url, key)
TICK_SYNC_WRITE_ENABLED = False # Toggle writing updates to Supabase (e.g. False in dev)

# ==========================================
# 2. PERSISTENCE & INITIALIZATION
# ==========================================

def load_ticks_history():
    """
    Loads saved ticks from Supabase if configured, falling back to local file.
    """
    global ticks_list, tick_database_size
    loaded_from_supabase = False
    
    # 1. Try loading from Supabase tables
    if supabase:
        try:
            print("Fetching ticks history from Supabase...")
            res = supabase.table('ticks_store').select('*').eq('id', 1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                with ticks_lock:
                    ticks_list = row.get('ticks', [])
                    tick_database_size = row.get('tick_database_size', 17280)
                print(f"✅ Loaded {len(ticks_list)} ticks from Supabase (DB size limit: {tick_database_size}).")
                loaded_from_supabase = True
            else:
                print("ℹ️ No tick history record found in Supabase (id=1).")
        except Exception as e:
            print(f"⚠️ Failed to load ticks from Supabase: {e}")
            
    # 2. Local JSON file fallback
    if not loaded_from_supabase:
        try:
            if os.path.exists(TICKS_FILE):
                with open(TICKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        with ticks_lock:
                            ticks_list = data.get('ticks', [])
                            tick_database_size = data.get('tick_database_size', 17280)
                    elif isinstance(data, list):
                        with ticks_lock:
                            ticks_list = data
                print(f"Loaded {len(ticks_list)} ticks from local history file.")
        except Exception as e:
            print(f"Error loading ticks history from local file: {e}")


def save_ticks_history():
    """
    Saves accumulated ticks list locally to data/ticks_history.json
    """
    try:
        os.makedirs(os.path.dirname(TICKS_FILE), exist_ok=True)
        with open(TICKS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'ticks': ticks_list,
                'tick_database_size': tick_database_size
            }, f, indent=2)
    except Exception as e:
        print(f"Error saving ticks history locally: {e}")


def save_ticks_to_supabase():
    """
    Pushes current local ticks buffer and size settings to Supabase
    """
    if not supabase or not TICK_SYNC_WRITE_ENABLED:
        return
    try:
        with ticks_lock:
            local_ticks = list(ticks_list)
            local_size = tick_database_size
            
        print(f"Syncing {len(local_ticks)} ticks with Supabase...")
        supabase.table('ticks_store').upsert({
            'id': 1,
            'ticks': local_ticks,
            'tick_database_size': local_size,
            'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).execute()
        print("✅ Successfully synced ticks history with Supabase.")
    except Exception as e:
        print(f"❌ Error saving ticks to Supabase: {e}")


# ==========================================
# 3. GRACEFUL SHUTDOWN HANDLERS
# ==========================================

def register_shutdown_handlers():
    """
    Catches SIGINT/SIGTERM to save memory buffers to disk/cloud on server shutdown.
    """
    import signal
    import sys
    
    def graceful_shutdown(signum, frame):
        print(f"\n🛑 Received shutdown signal ({signum}). Gracefully saving state...")
        
        # 1. Sync cloud DB
        if supabase and TICK_SYNC_WRITE_ENABLED:
            try:
                save_ticks_to_supabase()
            except Exception as e:
                print(f"Error saving to Supabase during shutdown: {e}")
                
        # 2. Write local file
        try:
            save_ticks_history()
            print("✅ State saved locally successfully.")
        except Exception as e:
            print(f"Error saving to local file during shutdown: {e}")
            
        print("Goodbye!")
        sys.exit(0)
        
    try:
        signal.signal(signal.SIGTERM, graceful_shutdown)
        signal.signal(signal.SIGINT, graceful_shutdown)
        print("Registered shutdown signal handlers (SIGTERM, SIGINT).")
    except ValueError as e:
        print(f"⚠️ Could not register signal handlers: {e}")


# ==========================================
# 4. BACKGROUND TICK ACCUMULATION LOOP
# ==========================================

def tick_accumulation_loop():
    """
    Daemon thread loop fetching the current BTCUSDT spot price 
    from Binance API every 5 seconds.
    """
    global ticks_list
    print("Starting background tick accumulation thread...")
    last_supabase_save = time.time()
    
    while True:
        try:
            url = 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode())
                price = float(res_data['price'])
                
                if price > 0:
                    with ticks_lock:
                        ticks_list.append(price)
                        # Keep list within DB size limits
                        while len(ticks_list) > tick_database_size:
                            ticks_list.pop(0)
                        save_ticks_history()
                        
                    # Hourly Sync to Supabase
                    current_time = time.time()
                    if current_time - last_supabase_save >= 3600:
                        save_ticks_to_supabase()
                        last_supabase_save = current_time
                        
        except Exception as e:
            # Silent fallback / logs on failure
            pass
            
        time.sleep(5)


# ==========================================
# 5. FLASK API ENDPOINTS
# ==========================================

# 5.1 Route to Fetch Ticks History
# JavaScript fetch ticks source: fetchTicksHistory()
@app.route('/api/exchange/ticks-history', methods=['GET'])
def get_ticks_history():
    with ticks_lock:
        return jsonify({
            'success': True,
            'ticks': ticks_list,
            'tick_database_size': tick_database_size
        })


# 5.2 Route to Modify Tick Database Limits
# JavaScript source call: handleDatabaseSizeChange(value)
@app.route('/api/exchange/tick-database-size', methods=['POST'])
def update_tick_database_size():
    global tick_database_size, ticks_list
    data = request.get_json() or {}
    new_size = data.get('size')
    
    if new_size is None:
        return jsonify({'error': 'Missing size parameter'}), 400
    try:
        new_size = int(new_size)
        if new_size < 2:
            return jsonify({'error': 'Size must be at least 2'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid size value'}), 400
        
    with ticks_lock:
        tick_database_size = new_size
        # Trim current memory buffer if it exceeds new limit
        while len(ticks_list) > tick_database_size:
            ticks_list.pop(0)
        save_ticks_history()
        
    # Sync with Supabase immediately on size change
    try:
        save_ticks_to_supabase()
    except Exception as e:
        print(f"Error syncing size change to Supabase: {e}")
        
    return jsonify({
        'success': True,
        'tick_database_size': tick_database_size
    })


# 5.3 Route to Fetch Completed Trades (For last 5 deals analytics)
# JavaScript fetch analytics source: updateTradesAnalytics()
@app.route('/api/exchange/history', methods=['GET'])
def exchange_history():
    # Helper decorator `@login_required` is standard.
    # Fetches active user's trade history from database/session context.
    user_id = session.get('user_id')
    
    # 1. Fetch from Supabase trades table if available
    if supabase:
        try:
            res = supabase.table('trades').select('*').eq('user_id', user_id).order('timestamp', desc=True).execute()
            data = getattr(res, 'data', [])
            return jsonify(data), 200
        except Exception as e:
            print(f"Error fetching history from Supabase: {str(e)}")
            
    # 2. Session Fallback
    if 'trades' not in session:
        session['trades'] = []
    return jsonify(session['trades']), 200
