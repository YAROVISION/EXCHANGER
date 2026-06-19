import random

def simulate_trade(wallet, trade_type, symbol, amount, price):
    """Mimics app.py state updates for validation"""
    usd_balance = wallet['usd_balance']
    btc_balance = wallet['btc_balance']
    eth_balance = wallet['eth_balance']
    avg_buy_price = wallet['avg_buy_price']
    eth_avg_buy_price = wallet['eth_avg_buy_price']
    
    fee_rate = 0.001
    fee = amount * price * fee_rate
    total_usd_value = amount * price
    
    if symbol == 'BTCUSDT':
        if trade_type == 'buy':
            total_cost = total_usd_value + fee
            if usd_balance < total_cost:
                return wallet  # Insufficient funds, skip
            usd_balance -= total_cost
            btc_balance = round(btc_balance + amount, 8)
            avg_buy_price = ((wallet['btc_balance'] * avg_buy_price) + (amount * price)) / btc_balance if btc_balance > 0 else 0.0
        elif trade_type == 'sell':
            if round(btc_balance, 8) < round(amount, 8):
                return wallet  # Insufficient balance, skip
            usd_balance += (total_usd_value - fee)
            btc_balance = round(btc_balance - amount, 8)
            avg_buy_price = avg_buy_price if btc_balance > 0 else 0.0
            
    elif symbol == 'ETHUSDT':
        if trade_type == 'buy':
            total_cost = total_usd_value + fee
            if usd_balance < total_cost:
                return wallet  # Insufficient funds, skip
            usd_balance -= total_cost
            eth_balance = round(eth_balance + amount, 8)
            eth_avg_buy_price = ((wallet['eth_balance'] * eth_avg_buy_price) + (amount * price)) / eth_balance if eth_balance > 0 else 0.0
        elif trade_type == 'sell':
            if round(eth_balance, 8) < round(amount, 8):
                return wallet  # Insufficient balance, skip
            usd_balance += (total_usd_value - fee)
            eth_balance = round(eth_balance - amount, 8)
            eth_avg_buy_price = eth_avg_buy_price if eth_balance > 0 else 0.0

    return {
        'usd_balance': usd_balance,
        'btc_balance': btc_balance,
        'eth_balance': eth_balance,
        'avg_buy_price': avg_buy_price,
        'eth_avg_buy_price': eth_avg_buy_price
    }

def verify_invariants(wallet):
    """Enforces mathematical rules (DbC) on the wallet state"""
    usd = wallet['usd_balance']
    btc = wallet['btc_balance']
    eth = wallet['eth_balance']
    btc_avg = wallet['avg_buy_price']
    eth_avg = wallet['eth_avg_buy_price']
    
    assert usd >= 0.0, f"USD balance is negative: {usd}"
    assert btc >= 0.0, f"BTC balance is negative: {btc}"
    assert eth >= 0.0, f"ETH balance is negative: {eth}"
    assert btc_avg >= 0.0, f"BTC avg buy price is negative: {btc_avg}"
    assert eth_avg >= 0.0, f"ETH avg buy price is negative: {eth_avg}"
    
    # Balance zero rules
    if round(btc, 8) == 0.0:
        assert btc_avg == 0.0, f"BTC balance is 0 but avg price is {btc_avg}"
    if round(eth, 8) == 0.0:
        assert eth_avg == 0.0, f"ETH balance is 0 but avg price is {eth_avg}"

def run_pbt_simulation():
    print("--- STARTING PROPERTY-BASED VERIFICATION ---")
    random.seed(42)  # For deterministic runs
    
    wallet = {
        'usd_balance': 100.0,
        'btc_balance': 0.0,
        'eth_balance': 0.0,
        'avg_buy_price': 0.0,
        'eth_avg_buy_price': 0.0
    }
    
    iterations = 1000
    successful_trades = 0
    
    for i in range(iterations):
        trade_type = random.choice(['buy', 'sell'])
        symbol = random.choice(['BTCUSDT', 'ETHUSDT'])
        
        # Select realistic amount and price range
        if symbol == 'BTCUSDT':
            price = random.uniform(50000.0, 75000.0)
            amount = random.uniform(0.0001, 0.002)
        else:
            price = random.uniform(1500.0, 3000.0)
            amount = random.uniform(0.005, 0.05)
            
        # Run state update
        new_wallet = simulate_trade(wallet, trade_type, symbol, amount, price)
        
        if new_wallet != wallet:
            successful_trades += 1
            
        wallet = new_wallet
        
        # Assert invariants hold at this state transition
        try:
            verify_invariants(wallet)
        except AssertionError as e:
            print(f"[FAIL] Invariant violated at iteration {i}: {e}")
            print("Current Wallet State:", wallet)
            return False
            
    print(f"[SUCCESS] Verified {iterations} randomized operations.")
    print(f"Executed successful trades: {successful_trades}")
    print("Final Wallet State:", wallet)
    print("---------------------------------------------")
    return True

if __name__ == '__main__':
    run_pbt_simulation()
