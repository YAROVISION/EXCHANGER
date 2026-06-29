import urllib.request
import urllib.parse
import json

def test_trade_flow():
    # We use a cookie processor to maintain the Flask session cookie
    cookie_jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cookie_jar)
    urllib.request.install_opener(opener)

    print("--- STARTING END-TO-END VERIFICATION FLOW ---")

    # Step 1: Mock Login
    print("1. Logging in via mock endpoint...")
    login_url = "http://127.0.0.1:5000/api/auth/mock-login-test"
    with urllib.request.urlopen(login_url) as res:
        print("Login response:", res.read().decode())

    # Step 1.5: Reset wallet
    print("\n1.5. Resetting wallet to initial state...")
    reset_url = "http://127.0.0.1:5000/api/exchange/reset"
    req_reset = urllib.request.Request(reset_url, method='POST')
    with urllib.request.urlopen(req_reset) as res:
        print("Reset response:", res.read().decode())

    # Step 2: Fetch Wallet initially (should set fallback flag)
    print("\n2. Fetching initial wallet (triggers schema check)...")
    wallet_url = "http://127.0.0.1:5000/api/exchange/wallet"
    with urllib.request.urlopen(wallet_url) as res:
        initial_wallet = json.loads(res.read().decode())
        print("Initial Wallet State:")
        print(json.dumps(initial_wallet, indent=2))

    # Step 3: Perform ETH buy trade
    print("\n3. Performing market buy of 0.01 ETH...")
    trade_url = "http://127.0.0.1:5000/api/exchange/trade"
    trade_data = json.dumps({
        "type": "buy",
        "amount": 0.01,
        "price": 1750.0,
        "symbol": "ETHUSDT"
    }).encode('utf-8')
    
    try:
        req = urllib.request.Request(trade_url, data=trade_data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as res:
            trade_res = json.loads(res.read().decode())
            print("Trade Response:")
            print(json.dumps(trade_res, indent=2))
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code, e.reason)
        print("Response body:", e.read().decode())
        raise

    # Step 4: Fetch Wallet again
    print("\n4. Fetching wallet post-trade...")
    with urllib.request.urlopen(wallet_url) as res:
        post_wallet = json.loads(res.read().decode())
        print("Post-Trade Wallet State:")
        print(json.dumps(post_wallet, indent=2))
        
        # Verify changes
        assert post_wallet['eth_balance'] == 0.01, "ETH balance should be 0.01!"
        assert post_wallet['usd_balance'] < 100.0, "USD balance should be deducted!"
        print("[SUCCESS] Wallet values verified!")

    # Step 5: Fetch History
    print("\n5. Fetching trade history...")
    history_url = "http://127.0.0.1:5000/api/exchange/history"
    with urllib.request.urlopen(history_url) as res:
        history_data = json.loads(res.read().decode())
        print("Trade History State:")
        print(json.dumps(history_data, indent=2))
        
        # Verify transaction is in history
        assert len(history_data) > 0, "Trade history should not be empty!"
        last_trade = history_data[0]
        assert last_trade['symbol'] == 'ETHUSDT', "Trade symbol should be ETHUSDT!"
        assert last_trade['btc_amount'] == 0.01, "Trade amount should be 0.01!"
        print("[SUCCESS] Trade history verified!")

    print("\n--- ALL TESTS COMPLETED SUCCESSFULLY! ---")

if __name__ == '__main__':
    test_trade_flow()
