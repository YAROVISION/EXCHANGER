// Exchanger Application State
let state = {
    user: null,
    wallet: null,
    trades: [],
    prices: {
        BTC: 0.0,
        ETH: 0.0
    },
    prevPrices: {
        BTC: 0.0,
        ETH: 0.0
    },
    activeTab: 'market',
    selectedAsset: 'BTC',
    botHistoryWindowSize: 1500,
    botState: {
        BTC: {
            usd: 100.00,
            asset: 0.0,
            tradeState: 'idle',
            tradeSubState: 'waiting_below_13',
            buyPrice: 0,
            trades: [],
            priceHistory: [],
            averageHistory: [],
            val87History: [],
            val75History: [],
            val25History: [],
            val13History: [],
            val13Plus03History: []
        },
        ETH: {
            usd: 100.00,
            asset: 0.0,
            tradeState: 'idle',
            tradeSubState: 'waiting_below_13',
            buyPrice: 0,
            trades: [],
            priceHistory: [],
            averageHistory: [],
            val87History: [],
            val75History: [],
            val25History: [],
            val13History: [],
            val13Plus03History: []
        }
    }
};

// DOM Elements
const loginOverlay = document.getElementById('login-overlay');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const appContainer = document.getElementById('app-container');
const userEmailDisplay = document.getElementById('user-email-display');
const logoutBtn = document.getElementById('logout-btn');

// Balances
const usdBalanceDisplay = document.getElementById('usd-balance-display');
const btcBalanceDisplay = document.getElementById('btc-balance-display');
const avgBuyDisplay = document.getElementById('avg-buy-display');
const resetBtn = document.getElementById('reset-btn');

// Tickers
const btcTicker = document.getElementById('btc-ticker');
const ethTicker = document.getElementById('eth-ticker');

// Tabs
const tabButtons = document.querySelectorAll('.tab-btn');
const marketTab = document.getElementById('market-tab');
const limitTab = document.getElementById('limit-tab');

// Market form
const marketAmountInput = document.getElementById('market-amount');
const marketBuyBtn = document.getElementById('market-buy-btn');
const marketSellBtn = document.getElementById('market-sell-btn');

// Limit form
const limitPriceInput = document.getElementById('limit-price');
const limitAmountInput = document.getElementById('limit-amount');
const limitBuyBtn = document.getElementById('limit-buy-btn');
const limitSellBtn = document.getElementById('limit-sell-btn');

// Orders and History containers
const activeOrdersContainer = document.getElementById('active-orders-container');
const historyContainer = document.getElementById('history-container');
const updateTimerDisplay = document.getElementById('update-timer');

// Init
document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
    initTabs();
    initForms();
    initAssetSelection();
    initBot();
    
    // Start price loop polling
    setInterval(updatePricesAndTriggers, 5000);
});

// Asset Ticker Switcher
function initAssetSelection() {
    const tickers = document.querySelectorAll('.clickable-ticker');
    tickers.forEach(ticker => {
        const select = () => {
            const asset = ticker.dataset.asset; // 'BTC' or 'ETH'
            if (state.selectedAsset === asset) return;
            
            state.selectedAsset = asset;
            
            // Update active class
            tickers.forEach(t => t.classList.remove('active'));
            ticker.classList.add('active');
            
            // Refresh UI components
            updateWalletUI();
            updateFutureTargetsUI();
            updateHistoryUI();
            updateFormLabels();
            updateBotUI();
        };

        ticker.addEventListener('click', select);
        ticker.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                select();
            }
        });
    });
}

// Auth Status check
async function checkAuthStatus() {
    try {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        if (data.logged_in) {
            loginSuccess(data.user);
        } else {
            showLogin();
        }
    } catch (err) {
        showLogin();
    }
}

// Login
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.textContent = '';
    
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    
    if (email !== "yarovision@gmail.com") {
        loginError.textContent = "Вхід заборонено: Тільки yarovision@gmail.com";
        return;
    }
    
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        
        const data = await res.json();
        if (res.ok) {
            loginSuccess(data.user);
        } else {
            loginError.textContent = data.error || "Неправильні облікові дані";
        }
    } catch (err) {
        loginError.textContent = "Помилка сервера. Спробуйте пізніше.";
    }
});

// Logout
logoutBtn.addEventListener('click', async () => {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        showLogin();
    } catch (err) {
        console.error("Logout failed", err);
    }
});

function loginSuccess(user) {
    state.user = user;
    userEmailDisplay.textContent = user.email;
    loginOverlay.classList.add('hidden');
    appContainer.classList.remove('hidden');
    refreshAppData();
}

function showLogin() {
    state.user = null;
    appContainer.classList.add('hidden');
    loginOverlay.classList.remove('hidden');
    loginForm.reset();
}

// Data Refresh
async function refreshAppData() {
    if (!state.user) return;
    await Promise.all([
        fetchWallet(),
        fetchHistory(),
        fetchPrices()
    ]);
}

async function fetchWallet() {
    try {
        const res = await fetch('/api/exchange/wallet');
        if (res.ok) {
            state.wallet = await res.json();
            updateWalletUI();
        }
    } catch (err) {
        console.error("Error fetching wallet", err);
    }
}

async function fetchHistory() {
    try {
        const res = await fetch('/api/exchange/history');
        if (res.ok) {
            state.trades = await res.json();
            updateHistoryUI();
        }
    } catch (err) {
        console.error("Error fetching history", err);
    }
}

async function fetchPrices() {
    try {
        const res = await fetch('/api/exchange/prices');
        if (res.ok) {
            const data = await res.json();
            state.prevPrices = { ...state.prices };
            state.prices = data;
            updateTickersUI();
        }
    } catch (err) {
        console.error("Error fetching prices", err);
    }
}

// UI updates
function updateWalletUI() {
    if (!state.wallet) return;
    
    usdBalanceDisplay.textContent = `$${state.wallet.usd_balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    const isBtc = state.selectedAsset === 'BTC';
    const cryptoBalanceLabel = document.getElementById('crypto-balance-label');
    if (cryptoBalanceLabel) {
        cryptoBalanceLabel.textContent = `Баланс ${state.selectedAsset}`;
    }
    
    const balance = isBtc ? state.wallet.btc_balance : state.wallet.eth_balance;
    const avgPrice = balance > 0 ? (isBtc ? state.wallet.avg_buy_price : state.wallet.eth_avg_buy_price) : 0.0;
    
    btcBalanceDisplay.textContent = `${balance.toFixed(8)} ${state.selectedAsset}`;
    avgBuyDisplay.textContent = `$${avgPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Sync form labels
    updateFormLabels();
    
    // Update wallet targets (FR-010)
    const walletTargetsCard = document.getElementById('wallet-targets-info');
    const walletBreakevenEl = document.getElementById('wallet-breakeven-price');
    const walletMinprofitEl = document.getElementById('wallet-minprofit-price');

    if (walletTargetsCard && walletBreakevenEl && walletMinprofitEl) {
        if (balance > 0 && avgPrice > 0) {
            const breakevenVal = avgPrice * 1.002;
            const minprofitVal = avgPrice * 1.003;
            
            walletBreakevenEl.textContent = `$${breakevenVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            walletMinprofitEl.textContent = `$${minprofitVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            walletTargetsCard.classList.remove('hidden');
        } else {
            walletTargetsCard.classList.add('hidden');
        }
    }

    // Render active orders
    activeOrdersContainer.innerHTML = '';
    const buyOrder = isBtc ? state.wallet.active_limit_order : state.wallet.active_limit_order_eth;
    const sellOrder = isBtc ? state.wallet.active_sell_limit_order : state.wallet.active_sell_limit_order_eth;
    
    if ((!buyOrder || !buyOrder.active) && (!sellOrder || !sellOrder.active)) {
        activeOrdersContainer.innerHTML = '<div class="no-data">Немає активних лімітних ордерів</div>';
        return;
    }
    
    if (buyOrder && buyOrder.active) {
        createOrderUI(buyOrder, 'buy');
    }
    if (sellOrder && sellOrder.active) {
        createOrderUI(sellOrder, 'sell');
    }
}

function createOrderUI(order, type) {
    const item = document.createElement('div');
    item.className = 'order-item';
    
    const typeLabel = type === 'buy' ? 'Buy Limit' : 'Sell Limit';
    const typeClass = type === 'buy' ? 'buy' : 'sell';
    
    item.innerHTML = `
        <div class="order-info">
            <span class="order-type-badge ${typeClass}">${typeLabel}</span>
            <span class="order-details">Кількість: <strong>${order.btc_amount.toFixed(4)} ${state.selectedAsset}</strong> по ціні <strong>$${order.price.toLocaleString()}</strong></span>
        </div>
        <button class="btn-cancel-order" onclick="cancelLimitOrder('${type}')">Скасувати</button>
    `;
    activeOrdersContainer.appendChild(item);
}

function updateTickersUI() {
    updateTickerItem(btcTicker, state.prices.BTC, state.prevPrices.BTC);
    updateTickerItem(ethTicker, state.prices.ETH, state.prevPrices.ETH);
    updateFutureTargetsUI();
}

function updateFutureTargetsUI() {
    const targetsCard = document.getElementById('market-targets-info');
    const titleEl = document.getElementById('targets-title');
    const breakevenEl = document.getElementById('breakeven-price');
    const minprofitEl = document.getElementById('minprofit-price');

    const currentPrice = state.prices[state.selectedAsset];

    if (targetsCard && breakevenEl && minprofitEl && currentPrice > 0) {
        const breakevenVal = currentPrice * 1.002;
        const minprofitVal = currentPrice * 1.003;
        
        if (titleEl) {
            titleEl.textContent = `🎯 Орієнтири для продажу (при купівлі за $${currentPrice.toLocaleString()}):`;
        }
        breakevenEl.textContent = `$${breakevenVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        minprofitEl.textContent = `$${minprofitVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }
}

function updateFormLabels() {
    const asset = state.selectedAsset;
    
    const marketTradeTitle = document.getElementById('market-trade-title');
    if (marketTradeTitle) {
        marketTradeTitle.textContent = `Купівля / Продаж ${asset} за ринковою ціною`;
    }
    
    const marketAmountLabel = document.getElementById('market-amount-label');
    if (marketAmountLabel) {
        marketAmountLabel.textContent = `Кількість для угоди (${asset})`;
    }
    
    const marketBuyBtn = document.getElementById('market-buy-btn');
    if (marketBuyBtn) {
        marketBuyBtn.textContent = `КУПИТИ ${asset}`;
    }
    
    const marketSellBtn = document.getElementById('market-sell-btn');
    if (marketSellBtn) {
        marketSellBtn.textContent = `ПРОДАТИ ${asset}`;
    }
    
    const limitAmountLabel = document.getElementById('limit-amount-label');
    if (limitAmountLabel) {
        limitAmountLabel.textContent = `Кількість (${asset})`;
    }
}

function updateTickerItem(element, currentPrice, prevPrice) {
    const valEl = element.querySelector('.ticker-value');
    const changeEl = element.querySelector('.ticker-change');
    
    valEl.textContent = `$${currentPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    if (prevPrice > 0) {
        const diff = currentPrice - prevPrice;
        const pct = (diff / prevPrice) * 100;
        changeEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
        
        if (diff > 0) {
            changeEl.className = 'ticker-change up';
        } else if (diff < 0) {
            changeEl.className = 'ticker-change down';
        }
    }
}

function updateHistoryUI() {
    historyContainer.innerHTML = '';
    
    const targetSymbol = state.selectedAsset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';
    const filteredTrades = state.trades.filter(t => (t.symbol || 'BTCUSDT') === targetSymbol);
    
    if (filteredTrades.length === 0) {
        historyContainer.innerHTML = '<div class="no-data">Угод ще не здійснено</div>';
        return;
    }
    
    filteredTrades.forEach(trade => {
        const item = document.createElement('div');
        item.className = 'history-item';
        
        const typeClass = trade.type === 'buy' ? 'buy' : 'sell';
        const formattedDate = new Date(trade.timestamp).toLocaleString();
        const total = trade.btc_amount * trade.price;
        const assetSymbol = state.selectedAsset;
        
        let targetsHtml = '';
        if (trade.type === 'buy') {
            const breakevenVal = trade.price * 1.002;
            const minprofitVal = trade.price * 1.003;
            targetsHtml = `
                <div class="history-item-targets">
                    <div class="history-target-row">
                        <span class="history-target-label">Беззбитковість (0% прибутку, +0.2%):</span>
                        <span class="history-target-value">$${breakevenVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="history-target-row">
                        <span class="history-target-label">Мінімальний прибуток (+0.3%):</span>
                        <span class="history-target-value">$${minprofitVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                </div>
            `;
        }
        
        item.innerHTML = `
            <div class="history-item-header">
                <span class="history-type ${typeClass}">${trade.type === 'buy' ? 'купівля' : 'продаж'}</span>
                <span class="history-time">${formattedDate}</span>
            </div>
            <div class="history-item-body">
                <span>Кількість: ${trade.btc_amount.toFixed(6)} ${assetSymbol}</span>
                <span>Ціна: $${trade.price.toLocaleString()}</span>
            </div>
            <div class="history-item-body">
                <span>Сума: $${total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                <span class="history-fee">Комісія: $${trade.fee.toFixed(4)}</span>
            </div>
            ${targetsHtml}
        `;
        historyContainer.appendChild(item);
    });
}

// Background Price Loader & Limit Order execution checker
let countdown = 5;
async function updatePricesAndTriggers() {
    countdown = 5;
    await fetchPrices();
    
    // Update bot histories and run strategy on every price tick (5s)
    ['BTC', 'ETH'].forEach(asset => {
        let currentPrice = state.prices[asset];
        if (currentPrice > 0) {
            let s = state.botState[asset];
            s.priceHistory.push(currentPrice);
            while (s.priceHistory.length > state.botHistoryWindowSize) {
                s.priceHistory.shift();
            }
            
            // Calculate current average, 75%, 13%, etc., and append to histories
            const sum = s.priceHistory.reduce((a, b) => a + b, 0);
            const avg = sum / s.priceHistory.length;
            s.averageHistory.push(avg);
            while (s.averageHistory.length > state.botHistoryWindowSize) {
                s.averageHistory.shift();
            }
            
            const max = Math.max(...s.priceHistory);
            const min = Math.min(...s.priceHistory);
            const diff = max - min;
            const val87 = min + 0.87 * diff;
            const val75 = min + 0.75 * diff;
            const val25 = min + 0.25 * diff;
            const val13 = min + 0.13 * diff;
            
            s.val87History.push(val87);
            while (s.val87History.length > state.botHistoryWindowSize) {
                s.val87History.shift();
            }
            
            s.val75History.push(val75);
            while (s.val75History.length > state.botHistoryWindowSize) {
                s.val75History.shift();
            }
            
            s.val25History.push(val25);
            while (s.val25History.length > state.botHistoryWindowSize) {
                s.val25History.shift();
            }
            
            s.val13History.push(val13);
            while (s.val13History.length > state.botHistoryWindowSize) {
                s.val13History.shift();
            }
            
            s.val13Plus03History.push(val13 * 1.003);
            while (s.val13Plus03History.length > state.botHistoryWindowSize) {
                s.val13Plus03History.shift();
            }
            
            // runBotTradingStrategy is now executed on the backend server for background processing
        }
    });
    
    if (state.activeTab === 'bot') {
        await fetchBotState(state.selectedAsset);
    }
    
    // Call limit check endpoint to automatically execute matched orders if there are active limit orders
    if (state.user && state.wallet) {
        const hasActiveLimit = 
            (state.wallet.active_limit_order && state.wallet.active_limit_order.active) ||
            (state.wallet.active_sell_limit_order && state.wallet.active_sell_limit_order.active) ||
            (state.wallet.active_limit_order_eth && state.wallet.active_limit_order_eth.active) ||
            (state.wallet.active_sell_limit_order_eth && state.wallet.active_sell_limit_order_eth.active);
            
        if (hasActiveLimit) {
            try {
                const res = await fetch('/api/exchange/limit-order/check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await res.json();
                if (data.triggered) {
                    alert(data.message);
                    refreshAppData();
                }
            } catch (err) {
                console.error("Auto trigger check failed", err);
            }
        }
    }
}

// Tabs
function initTabs() {
    const marketTab = document.getElementById('market-tab');
    const limitTab = document.getElementById('limit-tab');
    const botTab = document.getElementById('bot-tab');
    const realHistorySection = document.getElementById('real-history-section');
    const botHistorySection = document.getElementById('bot-history-section');
    const activeOrdersSection = document.getElementById('active-orders-section');
    const walletSection = document.getElementById('wallet-section');
    const botCourseStatsSection = document.getElementById('bot-course-stats-section');
    
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const tabName = btn.dataset.tab;
            state.activeTab = tabName;
            
            marketTab.classList.add('hidden');
            limitTab.classList.add('hidden');
            botTab.classList.add('hidden');
            
            if (tabName === 'bot') {
                if (realHistorySection) realHistorySection.classList.add('hidden');
                if (botHistorySection) botHistorySection.classList.remove('hidden');
                if (activeOrdersSection) activeOrdersSection.classList.add('hidden');
                if (walletSection) walletSection.classList.add('hidden');
                if (botCourseStatsSection) botCourseStatsSection.classList.remove('hidden');
                
                botTab.classList.remove('hidden');
                fetchBotState(state.selectedAsset);
                setTimeout(updatePriceHistoryChart, 50);
                setTimeout(() => {
                    const chartDiv = document.getElementById('metrics-history-chart');
                    if (chartDiv) Plotly.Plots.resize(chartDiv);
                }, 200);
            } else {
                if (realHistorySection) realHistorySection.classList.remove('hidden');
                if (botHistorySection) botHistorySection.classList.add('hidden');
                if (activeOrdersSection) activeOrdersSection.classList.remove('hidden');
                if (walletSection) walletSection.classList.remove('hidden');
                if (botCourseStatsSection) botCourseStatsSection.classList.add('hidden');
                
                if (tabName === 'market') {
                    marketTab.classList.remove('hidden');
                } else if (tabName === 'limit') {
                    limitTab.classList.remove('hidden');
                }
            }
        });
    });
}

// Reset Balance
resetBtn.addEventListener('click', async () => {
    if (!confirm("Ви впевнені, що хочете скинути віртуальний баланс та історію?")) return;
    
    try {
        const res = await fetch('/api/exchange/reset', { method: 'POST' });
        if (res.ok) {
            refreshAppData();
        }
    } catch (err) {
        console.error("Reset failed", err);
    }
});

// Forms Integration
function initForms() {
    // Market operations
    marketBuyBtn.addEventListener('click', () => executeMarketTrade('buy'));
    marketSellBtn.addEventListener('click', () => executeMarketTrade('sell'));
    
    // Limit operations
    limitBuyBtn.addEventListener('click', () => executeLimitOrder('buy'));
    limitSellBtn.addEventListener('click', () => executeLimitOrder('sell'));
}

async function executeMarketTrade(type) {
    const amount = parseFloat(marketAmountInput.value);
    const asset = state.selectedAsset;
    const price = state.prices[asset];
    const symbol = asset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';
    
    if (isNaN(amount) || amount <= 0) {
        alert(`Введіть коректну кількість ${asset}`);
        return;
    }
    
    try {
        const res = await fetch('/api/exchange/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, amount, price, symbol })
        });
        
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            refreshAppData();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Помилка виконання ринкової угоди");
    }
}

async function executeLimitOrder(type) {
    const price = parseFloat(limitPriceInput.value);
    const amount = parseFloat(limitAmountInput.value);
    const asset = state.selectedAsset;
    const symbol = asset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';
    
    if (isNaN(price) || price <= 0) {
        alert("Введіть коректну лімітну ціну");
        return;
    }
    
    if (isNaN(amount) || amount <= 0) {
        alert(`Введіть коректну кількість ${asset}`);
        return;
    }
    
    const usd_amount = price * amount;
    
    try {
        const res = await fetch('/api/exchange/limit-order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, price, btc_amount: amount, usd_amount, symbol })
        });
        
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            limitPriceInput.value = '';
            refreshAppData();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Помилка розміщення лімітного ордера");
    }
}

// Cancel Limit Order (global scope exposure)
window.cancelLimitOrder = async function(type) {
    const symbol = state.selectedAsset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';
    try {
        const res = await fetch('/api/exchange/limit-order/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, symbol })
        });
        
        if (res.ok) {
            refreshAppData();
        }
    } catch (err) {
        console.error("Cancel failed", err);
    }
};

window.adjustValue = function(inputId, direction) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const step = parseFloat(input.step) || 1;
    const min = input.min !== "" ? parseFloat(input.min) : -Infinity;
    const max = input.max !== "" ? parseFloat(input.max) : Infinity;
    
    let val = parseFloat(input.value);
    if (isNaN(val)) {
        if (inputId === 'limit-price' && state.prices && state.prices[state.selectedAsset] > 0) {
            val = state.prices[state.selectedAsset];
        } else {
            val = parseFloat(input.min) || 0;
        }
    } else {
        val = val + direction * step;
    }
    
    // Round to step precision
    const stepStr = input.step || "";
    const decimalPlaces = stepStr.includes('.') ? stepStr.split('.')[1].length : 0;
    val = parseFloat(val.toFixed(decimalPlaces));
    
    if (val < min) val = min;
    if (val > max) val = max;
    input.value = val;
    
    input.dispatchEvent(new Event('change'));
    input.dispatchEvent(new Event('input'));
};

// ==========================================
// BOT LOGIC AND HELPER FUNCTIONS
// ==========================================

function initBot() {
    // 1. Initial load of tick history for both BTC and ETH
    fetchTicksHistoryFor('BTC');
    fetchTicksHistoryFor('ETH');
    
    // 2. Setup inputs and buttons event listeners
    const sizeInput = document.getElementById('metrics-history-size');
    if (sizeInput) {
        sizeInput.value = state.botHistoryWindowSize;
        sizeInput.addEventListener('change', async (e) => {
            let val = parseInt(e.target.value);
            if (isNaN(val) || val < 2) val = 2;
            state.botHistoryWindowSize = val;
            
            // Re-cap histories and recalculate for both assets
            ['BTC', 'ETH'].forEach(asset => {
                let s = state.botState[asset];
                while (s.priceHistory.length > state.botHistoryWindowSize) {
                    s.priceHistory.shift();
                }
                recalculateAssetMetrics(asset);
            });
            
            // Sync window size with backend
            try {
                await fetch('/api/exchange/bot-window-size', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: state.selectedAsset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT', size: val })
                });
                await fetchBotState(state.selectedAsset);
            } catch (err) {
                console.error("Failed to update bot window size on server:", err);
            }
        });
    }
    
    const dbInput = document.getElementById('metrics-database-size');
    if (dbInput) {
        dbInput.addEventListener('change', (e) => {
            let val = parseInt(e.target.value);
            if (isNaN(val) || val < 2) val = 2;
            handleDatabaseSizeChange(val);
        });
    }
    
    const resetBtn = document.getElementById('reset-virtual-profit-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            if (!confirm("Ви впевнені, що хочете скинути віртуальний баланс та історію угод для " + state.selectedAsset + "?")) return;
            try {
                const res = await fetch('/api/exchange/bot-reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: state.selectedAsset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT' })
                });
                if (res.ok) {
                    await fetchBotState(state.selectedAsset);
                }
            } catch (err) {
                console.error("Failed to reset bot state:", err);
            }
        });
    }
}

async function fetchBotState(asset) {
    const symbol = asset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';
    try {
        const res = await fetch(`/api/exchange/bot-state?symbol=${symbol}`);
        if (res.ok) {
            const data = await res.json();
            let s = state.botState[asset];
            s.usd = data.usd;
            s.asset = data.asset;
            s.tradeState = data.tradeState;
            s.tradeSubState = data.tradeSubState;
            s.buyPrice = data.buyPrice;
            s.trades = data.trades;
            s.regressionAngle = data.regression_angle !== undefined ? data.regression_angle : 0.0;
            s.regressionSignal = data.regression_signal || "НЕЙТРАЛЬНИЙ";
            state.botHistoryWindowSize = data.window_size;
            
            const sizeInput = document.getElementById('metrics-history-size');
            if (sizeInput) {
                sizeInput.value = data.window_size;
            }
            
            updateBotUI();
        }
    } catch (e) {
        console.error(`Failed to fetch bot state for ${asset}:`, e);
    }
}

async function fetchTicksHistoryFor(asset) {
    const symbol = asset === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';
    try {
        const res = await fetch(`/api/exchange/ticks-history?symbol=${symbol}`);
        if (res.ok) {
            const data = await res.json();
            const loadedTicks = data.ticks || [];
            
            let s = state.botState[asset];
            s.priceHistory = loadedTicks.slice(-state.botHistoryWindowSize);
            
            recalculateAssetMetrics(asset);
            await fetchBotState(asset); // Get the persistent server state of the bot
        }
    } catch (e) {
        console.error(`Failed to fetch ticks history for ${asset}:`, e);
    }
}

async function handleDatabaseSizeChange(size) {
    try {
        const res = await fetch('/api/exchange/tick-database-size', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ size })
        });
        if (res.ok) {
            const data = await res.json();
            const dbInput = document.getElementById('metrics-database-size');
            if (dbInput) dbInput.value = data.tick_database_size;
        }
    } catch (e) {
        console.error("Failed to update database size:", e);
    }
}

function recalculateAssetMetrics(asset) {
    let s = state.botState[asset];
    s.averageHistory = [];
    s.val87History = [];
    s.val75History = [];
    s.val25History = [];
    s.val13History = [];
    s.val13Plus03History = [];
    
    for (let i = 0; i < s.priceHistory.length; i++) {
        const startIdx = Math.max(0, i - state.botHistoryWindowSize + 1);
        const windowPrices = s.priceHistory.slice(startIdx, i + 1);
        
        const sum = windowPrices.reduce((a, b) => a + b, 0);
        const avg = sum / windowPrices.length;
        s.averageHistory.push(avg);
        
        const max = Math.max(...windowPrices);
        const min = Math.min(...windowPrices);
        const diff = max - min;
        const val87 = min + 0.87 * diff;
        const val75 = min + 0.75 * diff;
        const val25 = min + 0.25 * diff;
        const val13 = min + 0.13 * diff;
        
        s.val87History.push(val87);
        s.val75History.push(val75);
        s.val25History.push(val25);
        s.val13History.push(val13);
        s.val13Plus03History.push(val13 * 1.003);
    }
}

function runBotTradingStrategy(asset, currentPrice) {
    let s = state.botState[asset];
    if (s.priceHistory.length < 2) return;
    
    if (s.priceHistory.length < state.botHistoryWindowSize) return;
    
    const maxPrice = Math.max(...s.priceHistory);
    const minPrice = Math.min(...s.priceHistory);
    if (maxPrice <= minPrice) return;
    const diff = maxPrice - minPrice;
    const val87 = minPrice + 0.87 * diff;
    const val75 = minPrice + 0.75 * diff;
    const val25 = minPrice + 0.25 * diff;
    const val13 = minPrice + 0.13 * diff;
    
    const feeRate = 0.001; 
    
    if (s.tradeState === 'idle') {
        if (s.tradeSubState === 'deactivated_waiting_above_25') {
            if (currentPrice >= val25) {
                s.tradeSubState = 'waiting_below_13';
            }
        } else if (s.tradeSubState !== 'triggered_below_13') {
            if (currentPrice <= val13) {
                s.tradeSubState = 'triggered_below_13';
            }
        } else {
            if (currentPrice <= minPrice) {
                s.tradeSubState = 'deactivated_waiting_above_25';
            } else if (currentPrice >= val25) {
                if (s.usd > 0) {
                    const totalCost = s.usd;
                    s.asset = totalCost / (currentPrice * (1 + feeRate));
                    const fee = s.asset * currentPrice * feeRate;
                    s.usd = 0;
                    s.tradeState = 'holding';
                    s.tradeSubState = 'waiting_75_rising';
                    s.buyPrice = currentPrice;
                    
                    s.trades.unshift({
                        type: 'buy',
                        timestamp: new Date().toISOString(),
                        amount: s.asset,
                        price: currentPrice,
                        fee: fee,
                        total: totalCost
                    });
                } else {
                    s.tradeSubState = 'waiting_below_13';
                }
            }
        }
    } else if (s.tradeState === 'holding') {
        if (s.tradeSubState === 'waiting_75' || s.tradeSubState === 'waiting_75_rising') {
            if (currentPrice >= val75) {
                if (s.asset > 0) {
                    const estimatedRevenue = s.asset * currentPrice * (1 - feeRate);
                    const costOfPurchase = s.asset * s.buyPrice * (1 + feeRate);
                    if (estimatedRevenue > costOfPurchase) {
                        s.tradeSubState = 'waiting_75_falling';
                    } else {
                        s.tradeSubState = 'waiting_breakeven';
                    }
                }
            }
        } else if (s.tradeSubState === 'waiting_75_falling') {
            if (currentPrice < val75) {
                if (s.asset > 0) {
                    const estimatedRevenue = s.asset * currentPrice * (1 - feeRate);
                    s.usd = estimatedRevenue;
                    const fee = s.asset * currentPrice * feeRate;
                    
                    s.trades.unshift({
                        type: 'sell',
                        timestamp: new Date().toISOString(),
                        amount: s.asset,
                        price: currentPrice,
                        fee: fee,
                        total: estimatedRevenue
                    });
                    
                    s.asset = 0;
                    s.tradeState = 'idle';
                    s.tradeSubState = 'waiting_below_13';
                    s.buyPrice = 0;
                }
            } else if (currentPrice >= val87) {
                if (s.asset > 0) {
                    const estimatedRevenue = s.asset * currentPrice * (1 - feeRate);
                    const costOfPurchase = s.asset * s.buyPrice * (1 + feeRate);
                    if (estimatedRevenue > costOfPurchase) {
                        s.tradeSubState = 'waiting_87_falling';
                    } else {
                        s.tradeSubState = 'waiting_breakeven';
                    }
                }
            }
        } else if (s.tradeSubState === 'waiting_87_falling') {
            if (currentPrice < val87) {
                if (s.asset > 0) {
                    const estimatedRevenue = s.asset * currentPrice * (1 - feeRate);
                    s.usd = estimatedRevenue;
                    const fee = s.asset * currentPrice * feeRate;
                    
                    s.trades.unshift({
                        type: 'sell',
                        timestamp: new Date().toISOString(),
                        amount: s.asset,
                        price: currentPrice,
                        fee: fee,
                        total: estimatedRevenue
                    });
                    
                    s.asset = 0;
                    s.tradeState = 'idle';
                    s.tradeSubState = 'waiting_below_13';
                    s.buyPrice = 0;
                }
            }
        } else if (s.tradeSubState === 'waiting_breakeven') {
            if (currentPrice >= s.buyPrice * 1.003) {
                if (s.asset > 0) {
                    const estimatedRevenue = s.asset * currentPrice * (1 - feeRate);
                    s.usd = estimatedRevenue;
                    const fee = s.asset * currentPrice * feeRate;
                    
                    s.trades.unshift({
                        type: 'sell',
                        timestamp: new Date().toISOString(),
                        amount: s.asset,
                        price: currentPrice,
                        fee: fee,
                        total: estimatedRevenue
                    });
                    
                    s.asset = 0;
                    s.tradeState = 'idle';
                    s.tradeSubState = 'waiting_below_13';
                    s.buyPrice = 0;
                }
            }
        }
    }
}

function updateBotUI() {
    const asset = state.selectedAsset;
    let s = state.botState[asset];
    if (!s) return;
    
    const maxEl = document.getElementById('metrics-price-max');
    const minEl = document.getElementById('metrics-price-min');
    const avgEl = document.getElementById('metrics-price-avg');
    const currentEl = document.getElementById('metrics-price-current');
    const pct75El = document.getElementById('metrics-price-75');
    const pct75DiffEl = document.getElementById('metrics-price-75-diff');
    const pct25El = document.getElementById('metrics-price-25');
    const pct25DiffEl = document.getElementById('metrics-price-25-diff');
    const pct13El = document.getElementById('metrics-price-13');
    const pct13DiffEl = document.getElementById('metrics-price-13-diff');
    const virtualProfitEl = document.getElementById('metrics-virtual-profit');
    const angleEl = document.getElementById('metrics-regression-angle');
    const signalEl = document.getElementById('metrics-regression-signal');
    const arrowEl = document.getElementById('regression-angle-arrow');
    
    const format = (val) => `$${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    if (s.priceHistory.length === 0) {
        if (maxEl) maxEl.textContent = '$-.--';
        if (minEl) minEl.textContent = '$-.--';
        if (avgEl) avgEl.textContent = '$-.--';
        if (currentEl) currentEl.textContent = '$-.--';
        if (pct75El) pct75El.textContent = '$-.--';
        if (pct75DiffEl) pct75DiffEl.textContent = '-';
        if (pct25El) pct25El.textContent = '$-.--';
        if (pct25DiffEl) pct25DiffEl.textContent = '-';
        if (pct13El) pct13El.textContent = '$-.--';
        if (pct13DiffEl) pct13DiffEl.textContent = '-';
        if (angleEl) {
            angleEl.textContent = '-.--°';
            angleEl.style.color = 'var(--text-light)';
        }
        if (arrowEl) {
            arrowEl.style.transform = 'rotate(0deg)';
            arrowEl.style.color = 'var(--text-light)';
        }
        if (signalEl) {
            signalEl.textContent = 'НЕЙТРАЛЬНИЙ';
            signalEl.style.color = 'var(--text-light)';
            signalEl.style.fontWeight = 'normal';
        }
        if (virtualProfitEl) {
            virtualProfitEl.innerHTML = `$100.00 USD / 0.00000000 ${asset}<br><span style="font-size:10px; color:var(--coffee-light);">Накопичення історії (0/${state.botHistoryWindowSize})</span>`;
            virtualProfitEl.style.color = 'var(--text-light)';
        }
        updatePriceHistoryChart();
        return;
    }
    
    const maxPrice = Math.max(...s.priceHistory);
    const minPrice = Math.min(...s.priceHistory);
    const avgPrice = s.priceHistory.reduce((a, b) => a + b, 0) / s.priceHistory.length;
    const diff = maxPrice - minPrice;
    const val75 = minPrice + 0.75 * diff;
    const val25 = minPrice + 0.25 * diff;
    const val13 = minPrice + 0.13 * diff;
    
    const currentPrice = state.prices[asset] || s.priceHistory[s.priceHistory.length - 1];
    
    if (maxEl) maxEl.textContent = format(maxPrice);
    if (minEl) minEl.textContent = format(minPrice);
    if (avgEl) avgEl.textContent = format(avgPrice);
    if (currentEl) currentEl.textContent = format(currentPrice);
    if (pct75El) pct75El.textContent = format(val75);
    if (pct75DiffEl) pct75DiffEl.textContent = `75% від різниці: $${(0.75 * diff).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
    if (pct25El) pct25El.textContent = format(val25);
    if (pct25DiffEl) pct25DiffEl.textContent = `25% від різниці: $${(0.25 * diff).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
    if (pct13El) pct13El.textContent = format(val13);
    if (pct13DiffEl) pct13DiffEl.textContent = `13% від різниці: $${(0.13 * diff).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
    
    if (angleEl && s.regressionAngle !== undefined) {
        angleEl.textContent = `${s.regressionAngle >= 0 ? '+' : ''}${s.regressionAngle.toFixed(2)}°`;
        if (s.regressionAngle > 45) {
            angleEl.style.color = 'var(--color-success)';
        } else if (s.regressionAngle < -45) {
            angleEl.style.color = 'var(--color-danger)';
        } else {
            angleEl.style.color = 'var(--text-light)';
        }
    }
    
    if (arrowEl && s.regressionAngle !== undefined) {
        // Rotate arrow by -angle degrees (since CSS rotation is clockwise and mathematical is counter-clockwise)
        arrowEl.style.transform = `rotate(${-s.regressionAngle}deg)`;
        if (s.regressionAngle > 45) {
            arrowEl.style.color = 'var(--color-success)';
        } else if (s.regressionAngle < -45) {
            arrowEl.style.color = 'var(--color-danger)';
        } else {
            arrowEl.style.color = '#D5B99A'; // var(--coffee-light)
        }
    }
    
    if (signalEl && s.regressionSignal !== undefined) {
        signalEl.textContent = s.regressionSignal;
        if (s.regressionSignal.includes("ЛОНГ")) {
            signalEl.style.color = 'var(--color-success)';
            signalEl.style.fontWeight = 'bold';
        } else if (s.regressionSignal.includes("ШОРТ")) {
            signalEl.style.color = 'var(--color-danger)';
            signalEl.style.fontWeight = 'bold';
        } else {
            signalEl.style.color = 'var(--text-light)';
            signalEl.style.fontWeight = 'normal';
        }
    }
    
    // Virtual Profit Display
    const currentEquity = s.usd + (s.asset * currentPrice * 0.999);
    const profit = currentEquity - 100.00;
    const sign = profit >= 0 ? '+' : '';
    const pctChange = (profit / 100.00) * 100;
    
    if (virtualProfitEl) {
        let text = `<div>$${s.usd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} USD / ${s.asset.toFixed(8)} ${asset}</div>`;
        text += `<div style="font-size:10px; color:var(--coffee-light); margin-top:2px;">`;
        text += `Капітал: $${currentEquity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${sign}${pctChange.toFixed(2)}%)`;
        if (s.tradeState === 'holding') {
            text += ` | Вхід: $${s.buyPrice.toLocaleString()}`;
            if (s.tradeSubState === 'waiting_breakeven') {
                text += ` | <span style="color:var(--color-danger); font-weight:bold;">Беззбиток (≥ $${(s.buyPrice * 1.003).toLocaleString(undefined, {maximumFractionDigits: 2})})</span>`;
            } else if (s.tradeSubState === 'waiting_75_rising' || s.tradeSubState === 'waiting_75') {
                text += ` | Ціль: Ріст ≥ 75% ($${val75.toLocaleString(undefined, {maximumFractionDigits: 2})})`;
            } else if (s.tradeSubState === 'waiting_75_falling') {
                const val87 = minPrice + 0.87 * diff;
                text += ` | <span style="color:var(--color-success); font-weight:bold;">Клапан 75% АКТИВОВАНО</span> (Спад < $${val75.toLocaleString(undefined, {maximumFractionDigits: 2})} або Ріст ≥ $${val87.toLocaleString(undefined, {maximumFractionDigits: 2})})`;
            } else if (s.tradeSubState === 'waiting_87_falling') {
                const val87 = minPrice + 0.87 * diff;
                text += ` | <span style="color:var(--color-success); font-weight:bold;">Клапан 87% АКТИВОВАНО</span> (Спад < $${val87.toLocaleString(undefined, {maximumFractionDigits: 2})})`;
            }
        } else if (s.priceHistory.length < state.botHistoryWindowSize) {
            text += ` | Накопичення (${s.priceHistory.length}/${state.botHistoryWindowSize})`;
        } else {
            if (s.tradeSubState === 'triggered_below_13') {
                text += ` | <span style="color:var(--color-success); font-weight:bold;">Клапан активовано (купівля при ≥ $${val25.toLocaleString(undefined, {maximumFractionDigits: 2})})</span>`;
            } else if (s.tradeSubState === 'deactivated_waiting_above_25') {
                text += ` | <span style="color:var(--color-danger); font-weight:bold;">Клапан деактивовано (очікування підйому ≥ $${val25.toLocaleString(undefined, {maximumFractionDigits: 2})})</span>`;
            } else {
                text += ` | Очікування падіння нижче $${val13.toLocaleString(undefined, {maximumFractionDigits: 2})}`;
            }
        }
        text += `</div>`;
        virtualProfitEl.innerHTML = text;
        
        if (profit > 0) {
            virtualProfitEl.style.color = 'var(--color-success)';
        } else if (profit < 0) {
            virtualProfitEl.style.color = 'var(--color-danger)';
        } else {
            virtualProfitEl.style.color = 'var(--text-light)';
        }
    }
    
    // Update Info Panel (4 Cards) under chart
    const totalEquityEl = document.getElementById('bot-total-equity');
    const netProfitEl = document.getElementById('bot-net-profit');
    const avgBuyPriceEl = document.getElementById('bot-avg-buy-price');
    const unrealizedPnlEl = document.getElementById('bot-unrealized-pnl');
    
    if (totalEquityEl) totalEquityEl.textContent = format(currentEquity);
    if (netProfitEl) {
        netProfitEl.textContent = `${sign}$${profit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${sign}${pctChange.toFixed(2)}%)`;
        netProfitEl.style.color = profit >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
    }
    if (avgBuyPriceEl) {
        avgBuyPriceEl.textContent = s.buyPrice > 0 ? format(s.buyPrice) : '$-.--';
    }
    if (unrealizedPnlEl) {
        if (s.asset > 0 && s.buyPrice > 0) {
            const uPnl = s.asset * (currentPrice - s.buyPrice);
            const uPnlPct = ((currentPrice - s.buyPrice) / s.buyPrice) * 100;
            const uSign = uPnl >= 0 ? '+' : '';
            unrealizedPnlEl.textContent = `${uSign}$${uPnl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${uSign}${uPnlPct.toFixed(2)}%)`;
            unrealizedPnlEl.style.color = uPnl >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
        } else {
            unrealizedPnlEl.textContent = '$-.--';
            unrealizedPnlEl.style.color = 'var(--text-light)';
        }
    }
    
    updateBotHistoryUI(asset, s.trades);
    updatePriceHistoryChart();
}

function updateBotHistoryUI(asset, trades) {
    const container = document.getElementById('bot-history-container');
    if (!container) return;
    container.innerHTML = '';
    
    if (trades.length === 0) {
        container.innerHTML = '<div class="no-data">Угод ще не здійснено</div>';
        return;
    }
    
    trades.forEach(trade => {
        const item = document.createElement('div');
        item.className = 'history-item';
        
        const typeClass = trade.type === 'buy' ? 'buy' : 'sell';
        const formattedDate = new Date(trade.timestamp).toLocaleString();
        
        let targetsHtml = '';
        if (trade.type === 'buy') {
            const breakevenVal = trade.price * 1.002;
            const minprofitVal = trade.price * 1.003;
            targetsHtml = `
                <div class="history-item-targets">
                    <div class="history-target-row">
                        <span class="history-target-label">Беззбитковість (0% прибутку, +0.2%):</span>
                        <span class="history-target-value">$${breakevenVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="history-target-row">
                        <span class="history-target-label">Мінімальний прибуток (+0.3%):</span>
                        <span class="history-target-value">$${minprofitVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                </div>
            `;
        }
        
        item.innerHTML = `
            <div class="history-item-header">
                <span class="history-type ${typeClass}">${trade.type === 'buy' ? 'купівля' : 'продаж'}</span>
                <span class="history-time">${formattedDate}</span>
            </div>
            <div class="history-item-body">
                <span>Кількість: ${trade.amount.toFixed(6)} ${asset}</span>
                <span>Ціна: $${trade.price.toLocaleString()}</span>
            </div>
            <div class="history-item-body">
                <span>Сума: $${trade.total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                <span class="history-fee">Комісія: $${trade.fee.toFixed(4)}</span>
            </div>
            ${targetsHtml}
        `;
        container.appendChild(item);
    });
}

function updatePriceHistoryChart() {
    const chartDiv = document.getElementById('metrics-history-chart');
    if (!chartDiv) return;
    
    const asset = state.selectedAsset;
    let s = state.botState[asset];
    if (!s || s.priceHistory.length < 2) {
        chartDiv.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; height:100%; color:var(--coffee-light); font-weight:600; font-size:12px;">📊 Очікування даних (потрібно щонайменше 2 оновлення ціни)...</div>';
        return;
    }
    
    const maxPrice = Math.max(...s.priceHistory);
    const minPrice = Math.min(...s.priceHistory);
    const avgPrice = s.priceHistory.reduce((a, b) => a + b, 0) / s.priceHistory.length;
    const diff = maxPrice - minPrice;
    
    const val87 = minPrice + 0.87 * diff;
    const val75 = minPrice + 0.75 * diff;
    const val25 = minPrice + 0.25 * diff;
    const val13 = minPrice + 0.13 * diff;
    
    const xValues = s.priceHistory.map((_, i) => i + 1);
    const currentPrice = state.prices[asset] || s.priceHistory[s.priceHistory.length - 1];
    
    const priceTrace = {
        x: xValues,
        y: s.priceHistory,
        mode: 'lines',
        name: 'Поточний курс',
        line: {
            color: '#8B5E3C', // var(--coffee-accent)
            width: 2.5,
            shape: 'spline'
        },
        hoverinfo: 'y'
    };
    
    const currentTrace = {
        x: [s.priceHistory.length],
        y: [currentPrice],
        mode: 'markers',
        name: 'Останній тік',
        cliponaxis: false,
        marker: {
            color: '#F5EBE0', // var(--coffee-latte)
            size: 8,
            line: {
                color: '#1C100A',
                width: 1.5
            }
        },
        hoverinfo: 'y'
    };
    
    const val87Line = {
        x: xValues,
        y: s.val87History,
        mode: 'lines',
        name: '87% Рівень',
        line: {
            color: '#d32f2f', // Red
            width: 1.2,
            dash: 'dashdot'
        },
        hoverinfo: 'name+y'
    };
    
    const val75Line = {
        x: xValues,
        y: s.val75History,
        mode: 'lines',
        name: '75% Рівень',
        line: {
            color: '#ef6c00', // Orange
            width: 1.2,
            dash: 'dashdot'
        },
        hoverinfo: 'name+y'
    };
    
    const maxLine = {
        x: [1, s.priceHistory.length],
        y: [maxPrice, maxPrice],
        mode: 'lines',
        name: 'Максимум',
        line: {
            color: '#EF5350', // var(--color-danger)
            width: 1.2,
            dash: 'dot'
        },
        fill: 'tonexty',
        fillcolor: 'rgba(239, 83, 80, 0.08)',
        hoverinfo: 'name+y'
    };
    
    const avgLine = {
        x: xValues,
        y: s.averageHistory,
        mode: 'lines',
        name: 'Середнє',
        line: {
            color: '#D5B99A', // var(--coffee-light)
            width: 1.5,
            dash: 'dash'
        },
        hoverinfo: 'name+y'
    };
    
    const minLine = {
        x: [1, s.priceHistory.length],
        y: [minPrice, minPrice],
        mode: 'lines',
        name: 'Мінімум',
        line: {
            color: '#66BB6A', // var(--color-success)
            width: 1.2,
            dash: 'dot'
        },
        hoverinfo: 'name+y'
    };
    
    const val25Line = {
        x: xValues,
        y: s.val25History,
        mode: 'lines',
        name: '25% Рівень',
        line: {
            color: '#26a69a', // Teal
            width: 1.2,
            dash: 'dashdot'
        },
        hoverinfo: 'name+y'
    };

    const val13Line = {
        x: xValues,
        y: s.val13History,
        mode: 'lines',
        name: '13% Рівень',
        line: {
            color: '#1976d2', // Blue
            width: 1.2,
            dash: 'dashdot'
        },
        fill: 'tonexty',
        fillcolor: 'rgba(102, 187, 106, 0.08)',
        hoverinfo: 'name+y'
    };
    
    const val13Plus03Line = {
        x: xValues,
        y: s.val13Plus03History,
        mode: 'lines',
        name: '0.3%',
        line: {
            color: '#7b1fa2', // Purple
            width: 1.2,
            dash: 'dash'
        },
        hoverinfo: 'name+y'
    };
    
    const data = [priceTrace, currentTrace];
    
    if (s.tradeState === 'holding' && s.buyPrice > 0) {
        const entryTrace = {
            x: [s.priceHistory.length],
            y: [s.buyPrice],
            mode: 'markers',
            name: 'Вхід',
            cliponaxis: false,
            marker: {
                color: '#EF5350',
                symbol: 'star',
                size: 10,
                line: { color: '#ffffff', width: 1.5 }
            },
            hoverinfo: 'name+y'
        };
        data.push(entryTrace);
        
        const breakevenTrace = {
            x: [s.priceHistory.length],
            y: [s.buyPrice * 1.003],
            mode: 'markers',
            name: 'Беззбитковість',
            cliponaxis: false,
            marker: {
                color: '#ff8f00',
                symbol: 'diamond',
                size: 8,
                line: { color: '#ffffff', width: 1.5 }
            },
            hoverinfo: 'name+y'
        };
        data.push(breakevenTrace);
    }
    
    data.push(val87Line, val75Line, maxLine, avgLine, minLine, val25Line, val13Line, val13Plus03Line);
    
    let allValues = [...s.priceHistory];
    if (s.averageHistory.length > 0) allValues.push(...s.averageHistory);
    if (s.val87History.length > 0) allValues.push(...s.val87History);
    if (s.val75History.length > 0) allValues.push(...s.val75History);
    if (s.val25History.length > 0) allValues.push(...s.val25History);
    if (s.val13History.length > 0) allValues.push(...s.val13History);
    if (s.val13Plus03History.length > 0) allValues.push(...s.val13Plus03History);
    if (s.tradeState === 'holding' && s.buyPrice > 0) {
        allValues.push(s.buyPrice);
        allValues.push(s.buyPrice * 1.003);
    }
    
    const yMinVal = Math.min(...allValues);
    const yMaxVal = Math.max(...allValues);
    const pad = (yMaxVal - yMinVal) * 0.05 || 10;
    
    const layout = {
        uirevision: state.selectedAsset, // Preserves zoom and pan state during real-time updates
        margin: { t: 15, b: 60, l: 60, r: 15 },
        height: 318,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        showlegend: true,
        legend: {
            orientation: 'h',
            y: -0.22,
            x: 0.5,
            xanchor: 'center',
            font: { size: 8, color: '#F5EBE0' }
        },
        xaxis: {
            gridcolor: 'rgba(203, 178, 156, 0.1)',
            tickfont: { size: 8, color: '#F5EBE0' },
            range: [1, s.priceHistory.length + Math.max(1, s.priceHistory.length * 0.02)],
            title: {
                text: `Оновлення (останні ${s.priceHistory.length})`,
                font: { size: 9, color: '#D5B99A' }
            }
        },
        yaxis: {
            gridcolor: 'rgba(203, 178, 156, 0.1)',
            tickfont: { size: 8, color: '#F5EBE0' },
            range: [yMinVal - pad, yMaxVal + pad],
            exponentformat: 'none',
            tickformat: '$,.2f'
        },
        hovermode: 'closest'
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        displaylogo: false
    };
    
    Plotly.react('metrics-history-chart', data, layout, config);
}
