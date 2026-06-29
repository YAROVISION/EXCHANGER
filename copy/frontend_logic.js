/**
 * Kronos Frontend Logic for:
 * - Real-time Price Polling (Binance API)
 * - Price History & Statistics Calculation (Max, Min, Average, 25% and 75% levels)
 * - Virtual Trading Strategy Simulation (Auto-trading based on levels)
 * - Trades Analytics compiler (Calculates averages & lists last 5 deals)
 * - Price History Plotly Chart Rendering (Dynamic height, color palettes)
 */

// ==========================================
// 1. STATE VARIABLES
// ==========================================
let walletUsd = 100.00;
let walletBtc = 0.00000000;
let currentBtcPrice = 0.00;
let exchangeMode = 'buy'; // 'buy' or 'sell'
let activePosition = null; // { btcAmount, purchaseDate, purchasePrice }

// Price History arrays (Dynamic size)
let btcPriceHistory50 = [];       // Raw BTC price updates
let btcAverageHistory50 = [];     // Running average calculation history
let btc75History50 = [];          // 75% level history
let btc25History50 = [];          // 25% level history
let btc13History50 = [];          // 13% level history
let btc13Plus03History50 = [];    // 13% level + 0.3% buffer history

// History window size (Corresponds to "Кількість тіків", defaults to 1500)
let btcHistoryWindowSize = 1500; 

// Virtual Trading strategy variables
let virtualWalletUsd = 100.00;
let virtualWalletBtc = 0.00;
let virtualTradeState = 'idle'; // 'idle' or 'holding'
let virtualTradeSubState = 'waiting_75'; // 'waiting_75' or 'waiting_breakeven'
let virtualBuyPrice = 0;

// Authentication States (Required for admin check)
let isLoggedIn = true; // Set to true or handle via auth callbacks
let userEmail = 'yarovision@gmail.com'; // Admin email who has access to metrics

// ==========================================
// 2. REAL-TIME PRICE POLLING
// ==========================================
let btcPriceInterval = null;

/**
 * Starts the interval to poll BTC price from Binance API every 5 seconds
 */
function startBtcPricePolling() {
    fetchBtcRealTimePrice();
    if (btcPriceInterval) clearInterval(btcPriceInterval);
    btcPriceInterval = setInterval(fetchBtcRealTimePrice, 5000);
}

/**
 * Fetches real-time BTC price, appends to history, and updates UI
 */
async function fetchBtcRealTimePrice() {
    try {
        // Axios is used in Kronos, but standard fetch can be used too
        const response = await axios.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT');
        if (response.data && response.data.price) {
            currentBtcPrice = parseFloat(response.data.price);
            
            // Add price to history
            addBtcPriceToHistory(currentBtcPrice);
            
            // Refresh Exchange UI and calculate metrics
            updateExchangeUI();
            
            // Note: Limit order checking functions (checkLimitOrderExecution, checkSellLimitOrderExecution)
            // are also triggered here in the main application.
        }
    } catch (error) {
        console.warn('❌ Failed to fetch Binance price ticker, falling back to local HTML parsing:', error);
        // Fallback: Read price from existing page elements
        const todayOpenText = document.getElementById('today-open-text');
        if (todayOpenText && todayOpenText.textContent !== '-') {
            const priceVal = parseFloat(todayOpenText.textContent.replace('$', '').replace(/,/g, '').trim());
            if (!isNaN(priceVal) && priceVal > 0) {
                currentBtcPrice = priceVal;
                addBtcPriceToHistory(currentBtcPrice);
                updateExchangeUI();
            }
        }
    }
}

// ==========================================
// 3. STATISTICAL HISTORY & CALCULATIONS
// ==========================================

/**
 * Appends a new price tick to arrays and removes oldest elements if size limit exceeded
 */
function addBtcPriceToHistory(price) {
    if (price <= 0 || isNaN(price)) return;
    
    btcPriceHistory50.push(price);
    while (btcPriceHistory50.length > btcHistoryWindowSize) {
        btcPriceHistory50.shift();
    }
    
    // Calculate current running average and add to history
    const sum = btcPriceHistory50.reduce((a, b) => a + b, 0);
    const avg = sum / btcPriceHistory50.length;
    btcAverageHistory50.push(avg);
    while (btcAverageHistory50.length > btcHistoryWindowSize) {
        btcAverageHistory50.shift();
    }
    
    // Calculate current 75% and 25% levels and add to history
    const max = Math.max(...btcPriceHistory50);
    const min = Math.min(...btcPriceHistory50);
    const diff = max - min;
    const val75 = min + 0.75 * diff;
    const val25 = min + 0.25 * diff;
    const val13 = min + 0.13 * diff;
    
    btc75History50.push(val75);
    while (btc75History50.length > btcHistoryWindowSize) {
        btc75History50.shift();
    }
    btc25History50.push(val25);
    while (btc25History50.length > btcHistoryWindowSize) {
        btc25History50.shift();
    }
    btc13History50.push(val13);
    while (btc13History50.length > btcHistoryWindowSize) {
        btc13History50.shift();
    }
    btc13Plus03History50.push(val13 * 1.003);
    while (btc13Plus03History50.length > btcHistoryWindowSize) {
        btc13Plus03History50.shift();
    }
}

/**
 * Re-computes all statistical arrays when ticks history limit changes
 */
function recalculateAllHistoryMetrics() {
    btcAverageHistory50 = [];
    btc75History50 = [];
    btc25History50 = [];
    btc13History50 = [];
    btc13Plus03History50 = [];

    for (let i = 0; i < btcPriceHistory50.length; i++) {
        const startIdx = Math.max(0, i - btcHistoryWindowSize + 1);
        const windowPrices = btcPriceHistory50.slice(startIdx, i + 1);
        
        const sum = windowPrices.reduce((a, b) => a + b, 0);
        const avg = sum / windowPrices.length;
        btcAverageHistory50.push(avg);

        const max = Math.max(...windowPrices);
        const min = Math.min(...windowPrices);
        const diff = max - min;
        const val75 = min + 0.75 * diff;
        const val25 = min + 0.25 * diff;
        const val13 = min + 0.13 * diff;

        btc75History50.push(val75);
        btc25History50.push(val25);
        btc13History50.push(val13);
        btc13Plus03History50.push(val13 * 1.003);
    }
}

/**
 * Triggered by history window size input field on change
 */
function handleWindowSizeChange(value) {
    let newSize = parseInt(value);
    if (isNaN(newSize) || newSize < 2) {
        newSize = 2; // Minimum size is 2
    }
    btcHistoryWindowSize = newSize;

    // Trim raw price array to match new window limit
    while (btcPriceHistory50.length > btcHistoryWindowSize) {
        btcPriceHistory50.shift();
    }

    // Recalculate metrics arrays
    recalculateAllHistoryMetrics();

    // Redraw and update displays
    updatePriceHistoryMetrics();
}

/**
 * Communicates tick database limit changes (up to 100k) to python backend
 */
async function handleDatabaseSizeChange(value) {
    let newSize = parseInt(value);
    if (isNaN(newSize) || newSize < 2) {
        newSize = 2;
        document.getElementById('metrics-database-size').value = 2;
    }
    try {
        const response = await fetch('/api/exchange/tick-database-size', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ size: newSize })
        });
        if (response.ok) {
            console.log("Tick database size successfully synchronized on backend:", newSize);
        }
    } catch (e) {
        console.error("Failed to update backend tick database size:", e);
    }
}

/**
 * Loads accumulated tick logs stored on Python backend
 */
async function fetchTicksHistory() {
    try {
        const response = await fetch('/api/exchange/ticks-history');
        if (response.ok) {
            const data = await response.json();
            const loadedTicks = data.ticks || [];
            
            if (data.tick_database_size) {
                const dbSizeInput = document.getElementById('metrics-database-size');
                if (dbSizeInput) {
                    dbSizeInput.value = data.tick_database_size;
                }
            }

            // Populate history with the loaded ticks trimmed to dynamic window size
            btcPriceHistory50 = loadedTicks.slice(-btcHistoryWindowSize);
            
            // Recalculate all helper statistical curves
            recalculateAllHistoryMetrics();
            
            // Redraw chart and update stats
            updatePriceHistoryMetrics();
        }
    } catch (e) {
        console.error("Failed to fetch ticks history from backend:", e);
    }
}

// ==========================================
// 4. METRICS & VIRTUAL TRADING LOGIC
// ==========================================

/**
 * Main update function for statistics section. Combines DOM updates and
 * runs the virtual level-trading strategy.
 */
function updatePriceHistoryMetrics() {
    const countEl = document.getElementById('price-history-count');
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

    if (countEl) countEl.textContent = btcPriceHistory50.length;

    // Handle empty state
    if (btcPriceHistory50.length === 0) {
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
        
        const virtualProfitEl = document.getElementById('metrics-virtual-profit');
        if (virtualProfitEl) {
            virtualProfitEl.innerHTML = `<div style="font-size: 13px; font-weight: bold; color: var(--coffee-dark);">$100.00 USD / 0.00000000 BTC</div><div style="font-size: 10px; color: var(--coffee-accent); font-weight: normal; margin-top: 2px;">Капітал: $100.00 (0.00%) | Накопичення історії (0/${btcHistoryWindowSize})</div>`;
        }
        
        updatePriceHistoryChart();
        return;
    }

    const maxPrice = Math.max(...btcPriceHistory50);
    const minPrice = Math.min(...btcPriceHistory50);
    const sum = btcPriceHistory50.reduce((a, b) => a + b, 0);
    const avgPrice = sum / btcPriceHistory50.length;
    const diff = maxPrice - minPrice;
    
    const val75 = minPrice + 0.75 * diff;
    const diff75 = 0.75 * diff;
    
    const val25 = minPrice + 0.25 * diff;
    const diff25 = 0.25 * diff;
    
    const val13 = minPrice + 0.13 * diff;
    const diff13 = 0.13 * diff;

    // ------------------------------------------
    // VIRTUAL LEVEL-TRADING ALGORITHM
    // ------------------------------------------
    if (currentBtcPrice > 0 && btcPriceHistory50.length >= 2 && maxPrice > minPrice) {
        if (virtualTradeState === 'idle') {
            if (virtualTradeSubState !== 'triggered_below_13') {
                if (currentBtcPrice <= val13 && btcPriceHistory50.length >= btcHistoryWindowSize) {
                    virtualTradeSubState = 'triggered_below_13';
                }
            } else {
                if (currentBtcPrice >= val25) {
                    if (virtualWalletUsd > 0) {
                        virtualWalletBtc = virtualWalletUsd / (currentBtcPrice * 1.001); // 0.1% buy commission
                        virtualWalletUsd = 0;
                        virtualTradeState = 'holding';
                        virtualTradeSubState = 'waiting_75';
                        virtualBuyPrice = currentBtcPrice;
                    } else {
                        virtualTradeSubState = 'waiting_below_13';
                    }
                }
            }
        } else if (virtualTradeState === 'holding') {
            if (virtualTradeSubState === 'waiting_75') {
                // SELL Target condition 1: Price climbs back to or past the 75% boundary
                if (currentBtcPrice >= val75) {
                    if (virtualWalletBtc > 0) {
                        // Ensure it yields profit exceeding commissions (buy fee + sell fee + target net profit)
                        if (currentBtcPrice * 0.999 >= virtualBuyPrice * 1.001 * 1.001) {
                            virtualWalletUsd = virtualWalletBtc * currentBtcPrice * 0.999; // 0.1% sell commission
                            virtualWalletBtc = 0;
                            virtualTradeState = 'idle';
                            virtualTradeSubState = 'waiting_below_13';
                            virtualBuyPrice = 0;
                        } else {
                            // If 75% boundary is hit but commission eats the profit, transition to breakeven safety mode
                            virtualTradeSubState = 'waiting_breakeven';
                        }
                    }
                }
            }
            if (virtualTradeSubState === 'waiting_breakeven') {
                // SELL Target condition 2: Sell immediately once price hits target breakeven point (Entry * 1.003)
                if (currentBtcPrice >= virtualBuyPrice * 1.003) {
                    if (virtualWalletBtc > 0) {
                        virtualWalletUsd = virtualWalletBtc * currentBtcPrice * 0.999;
                        virtualWalletBtc = 0;
                        virtualTradeState = 'idle';
                        virtualTradeSubState = 'waiting_below_13';
                        virtualBuyPrice = 0;
                    }
                }
            }
        }
    }

    // Formatter utility
    const format = (val) => `$${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

    // Update DOM Stats
    if (maxEl) maxEl.textContent = format(maxPrice);
    if (minEl) minEl.textContent = format(minPrice);
    if (avgEl) avgEl.textContent = format(avgPrice);
    if (currentEl && currentBtcPrice > 0) currentEl.textContent = format(currentBtcPrice);
    
    if (pct75El) pct75El.textContent = format(val75);
    if (pct75DiffEl) pct75DiffEl.textContent = `75% від різниці: $${diff75.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    if (pct25El) pct25El.textContent = format(val25);
    if (pct25DiffEl) pct25DiffEl.textContent = `25% від різниці: $${diff25.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    if (pct13El) pct13El.textContent = format(val13);
    if (pct13DiffEl) pct13DiffEl.textContent = `13% від різниці: $${diff13.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

    // Render Virtual Profit details
    const virtualProfitEl = document.getElementById('metrics-virtual-profit');
    if (virtualProfitEl) {
        const currentEquity = virtualWalletUsd + (virtualWalletBtc * currentBtcPrice * 0.999);
        const profit = currentEquity - 100.00;
        const sign = profit >= 0 ? '+' : '';
        const pctChange = ((currentEquity - 100.00) / 100.00) * 100;
        
        let text = `<div style="font-size: 13px; font-weight: bold; color: var(--coffee-dark);">`;
        text += `$${virtualWalletUsd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} USD`;
        text += ` / `;
        text += `${virtualWalletBtc.toFixed(8)} BTC`;
        text += `</div>`;
        
        text += `<div style="font-size: 10px; color: var(--coffee-accent); font-weight: normal; margin-top: 2px;">`;
        text += `Капітал: $${currentEquity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${sign}${pctChange.toFixed(2)}%)`;
        
        if (virtualTradeState === 'holding') {
            text += ` | Вхід: $${virtualBuyPrice.toLocaleString(undefined, {maximumFractionDigits: 2})}`;
            if (virtualTradeSubState === 'waiting_breakeven') {
                text += ` | <span style="color: #c62828; font-weight: bold;">Очікування беззбитковості (≥ $${(virtualBuyPrice * 1.003).toLocaleString(undefined, {maximumFractionDigits: 2})})</span>`;
            } else {
                text += ` | Очікування 75% рівня (≥ $${val75.toLocaleString(undefined, {maximumFractionDigits: 2})})`;
            }
        } else if (btcPriceHistory50.length < btcHistoryWindowSize) {
            text += ` | Накопичення історії (${btcPriceHistory50.length}/${btcHistoryWindowSize})`;
        }
        text += `</div>`;
        
        virtualProfitEl.innerHTML = text;
        if (profit > 0) {
            virtualProfitEl.style.color = '#2e7d32';
        } else if (profit < 0) {
            virtualProfitEl.style.color = '#c62828';
        } else {
            virtualProfitEl.style.color = 'var(--coffee-dark)';
        }
    }

    // Refresh chart graphic
    updatePriceHistoryChart();
}

/**
 * Resets virtual trading balances
 */
function resetVirtualProfit(event) {
    if (event) event.stopPropagation();
    virtualWalletUsd = 100.00;
    virtualWalletBtc = 0.00;
    virtualTradeState = 'idle';
    virtualBuyPrice = 0;
    updatePriceHistoryMetrics();
}

// ==========================================
// 5. TRADES ANALYTICS (LAST 5 TRADES)
// ==========================================

/**
 * Fetches user's complete trade log, extracts the last 5 transactions,
 * computes volume/averages/commissions, and outputs structured HTML table.
 */
async function updateTradesAnalytics() {
    if (!isLoggedIn || userEmail !== 'yarovision@gmail.com') return;
    const container = document.getElementById('metrics-trades-analytics-content');
    if (!container) return;

    try {
        const response = await fetch('/api/exchange/history');
        if (response.ok) {
            const trades = await response.json();
            if (!trades || trades.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: var(--coffee-accent); padding: 10px 0;">Угоди відсутні. Здійсніть купівлю або продаж біткоїна, щоб побачити аналітику.</div>';
                return;
            }

            // Extract the last 5 deals
            const last5 = trades.slice(0, 5);

            // Calculation registers
            let buyCount = 0;
            let sellCount = 0;
            let totalBuyVolume = 0;
            let totalSellVolume = 0;
            let totalBuyUsd = 0;
            let totalSellUsd = 0;
            let totalFees = 0;

            last5.forEach(t => {
                const amt = parseFloat(t.btc_amount || t.amount || 0);
                const price = parseFloat(t.price || 0);
                const fee = parseFloat(t.fee || 0);
                totalFees += fee;

                if (t.type === 'buy') {
                    buyCount++;
                    totalBuyVolume += amt;
                    totalBuyUsd += amt * price;
                } else if (t.type === 'sell') {
                    sellCount++;
                    totalSellVolume += amt;
                    totalSellUsd += amt * price;
                }
            });

            const avgBuyPrice = buyCount > 0 ? (totalBuyUsd / totalBuyVolume) : 0;
            const avgSellPrice = sellCount > 0 ? (totalSellUsd / totalSellVolume) : 0;

            // Generate HTML layout
            let html = `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 15px; background: rgba(139, 94, 60, 0.05); padding: 12px; border-radius: 6px; border: 1px solid var(--coffee-light);">
                    <div>
                        <span style="font-weight: 600; color: var(--coffee-accent);">Угод (останні 5):</span>
                        <div style="font-size: 16px; font-weight: bold; color: var(--coffee-espresso); margin-top: 4px;">Купівель: ${buyCount} | Продажів: ${sellCount}</div>
                    </div>
                    <div>
                        <span style="font-weight: 600; color: var(--coffee-accent);">Сер. курс купівлі:</span>
                        <div style="font-size: 16px; font-weight: bold; color: #2e7d32; margin-top: 4px;">${avgBuyPrice > 0 ? '$' + avgBuyPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '$-.--'}</div>
                    </div>
                    <div>
                        <span style="font-weight: 600; color: var(--coffee-accent);">Сер. курс продажу:</span>
                        <div style="font-size: 16px; font-weight: bold; color: #c62828; margin-top: 4px;">${avgSellPrice > 0 ? '$' + avgSellPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '$-.--'}</div>
                    </div>
                    <div>
                        <span style="font-weight: 600; color: var(--coffee-accent);">Сумарна комісія:</span>
                        <div style="font-size: 16px; font-weight: bold; color: var(--coffee-dark); margin-top: 4px;">$${totalFees.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}</div>
                    </div>
                </div>
                
                <h6 style="margin: 10px 0 6px 0; font-size: 12px; font-weight: bold; color: var(--coffee-espresso);">📋 Список останніх 5 угод:</h6>
                <table style="width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'JetBrains Mono', monospace;">
                    <thead>
                        <tr style="border-bottom: 2px solid var(--coffee-light); color: var(--coffee-accent); font-weight: bold; text-align: left;">
                            <th style="padding: 6px 4px;">Час</th>
                            <th style="padding: 6px 4px;">Тип</th>
                            <th style="padding: 6px 4px; text-align: right;">Курс (USD)</th>
                            <th style="padding: 6px 4px; text-align: right;">Кількість (BTC)</th>
                            <th style="padding: 6px 4px; text-align: right;">Комісія</th>
                            <th style="padding: 6px 4px; text-align: right;">Сума</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            last5.forEach(t => {
                const typeLabel = t.type === 'buy' ? '<span style="color:#2e7d32; font-weight:bold;">КУПІВЛЯ</span>' : '<span style="color:#c62828; font-weight:bold;">ПРОДАЖ</span>';
                const amt = parseFloat(t.btc_amount || t.amount || 0);
                const price = parseFloat(t.price || 0);
                const fee = parseFloat(t.fee || 0);
                const total = amt * price;
                const dateStr = t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : 'N/A';

                html += `
                    <tr style="border-bottom: 1px solid rgba(139, 94, 60, 0.15);">
                        <td style="padding: 6px 4px; color: var(--coffee-accent);">${dateStr}</td>
                        <td style="padding: 6px 4px;">${typeLabel}</td>
                        <td style="padding: 6px 4px; text-align: right; font-weight: bold; color: var(--coffee-espresso);">$${price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                        <td style="padding: 6px 4px; text-align: right;">${amt.toFixed(8)}</td>
                        <td style="padding: 6px 4px; text-align: right; color: var(--coffee-accent);">$${fee.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}</td>
                        <td style="padding: 6px 4px; text-align: right; font-weight: bold; color: var(--coffee-espresso);">$${total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    </tr>
                `;
            });

            html += `
                    </tbody>
                </table>
            `;
            container.innerHTML = html;
        }
    } catch (e) {
        console.error("Error updating trades analytics:", e);
        container.innerHTML = '<div style="color: #c62828;">Не вдалося завантажити аналітику угод через помилку мережі.</div>';
    }
}

// ==========================================
// 6. METRICS HISTORY GRAPH (PLOTLY)
// ==========================================

/**
 * Draws the animated dynamic line chart inside `#metrics-history-chart` using Plotly.
 * Plotted traces:
 * - BTC price curve (smooth spline)
 * - Last tick marker (dark circle)
 * - Horizontal Minimum (green dot) / Maximum (red dot) lines
 * - Average value curve (dashed line)
 * - 75% boundary curve (orange dash-dot)
 * - 25% boundary curve (blue dash-dot)
 * - 0.3% buffer curve
 * - Strategy buy entry point and breakeven point markers (if holding BTC)
 */
function updatePriceHistoryChart() {
    const chartDiv = document.getElementById('metrics-history-chart');
    if (!chartDiv) return;

    if (btcPriceHistory50.length < 2) {
        chartDiv.style.height = '300px';
        chartDiv.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; height:100%; color:var(--coffee-accent); font-weight:600; font-size:12px;">📊 Очікування даних (потрібно щонайменше 2 оновлення ціни)...</div>';
        return;
    }

    // Clear placeholder text if it exists
    if (chartDiv.querySelector('div') && chartDiv.querySelector('div').textContent.includes('Очікування')) {
        chartDiv.innerHTML = '';
    }

    const maxPrice = Math.max(...btcPriceHistory50);
    const minPrice = Math.min(...btcPriceHistory50);
    const sum = btcPriceHistory50.reduce((a, b) => a + b, 0);
    const avgPrice = sum / btcPriceHistory50.length;
    const diff = maxPrice - minPrice;
    
    const val75 = minPrice + 0.75 * diff;
    const val25 = minPrice + 0.25 * diff;
    const val13 = minPrice + 0.13 * diff;

    const xValues = btcPriceHistory50.map((_, i) => i + 1);

    // Trace 1: Price line
    const priceTrace = {
        x: xValues,
        y: btcPriceHistory50,
        mode: 'lines',
        name: 'Поточний курс',
        line: {
            color: '#8B5E3C', // var(--coffee-accent)
            width: 2.5,
            shape: 'spline' // Smooth spline
        },
        hoverinfo: 'y'
    };

    // Trace 2: Current Tick Dot
    const currentTrace = {
        x: [btcPriceHistory50.length],
        y: [currentBtcPrice],
        mode: 'markers',
        name: 'Останній тік',
        cliponaxis: false,
        marker: {
            color: '#2C1A11', // var(--coffee-dark)
            size: 8,
            line: {
                color: '#ffffff',
                width: 1.5
            }
        },
        hoverinfo: 'y'
    };

    // Helper: generate horizontal guidelines
    const horizontalLineTrace = (value, name, color, dashStyle) => {
        return {
            x: [1, btcPriceHistory50.length],
            y: [value, value],
            mode: 'lines',
            name: name,
            line: {
                color: color,
                width: 1.2,
                dash: dashStyle
            },
            hoverinfo: 'name+y'
        };
    };

    // Statistical Traces
    const val75Line = {
        x: xValues,
        y: btc75History50,
        mode: 'lines',
        name: '75% Рівень',
        line: {
            color: '#ef6c00',
            width: 1.2,
            dash: 'dashdot'
        },
        hoverinfo: 'name+y'
    };
    
    const maxLine = horizontalLineTrace(maxPrice, 'Максимум', '#c62828', 'dot');
    maxLine.fill = 'tonexty';
    maxLine.fillcolor = 'rgba(198, 40, 40, 0.15)'; // Highlight maximum zone
    
    const avgLine = {
        x: xValues,
        y: btcAverageHistory50,
        mode: 'lines',
        name: 'Середнє',
        line: {
            color: '#5d4037',
            width: 1.5,
            dash: 'dash'
        },
        hoverinfo: 'name+y'
    };
    
    const minLine = horizontalLineTrace(minPrice, 'Мінімум', '#388e3c', 'dot');
    
    const val25Line = {
        x: xValues,
        y: btc25History50,
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
        y: btc13History50,
        mode: 'lines',
        name: '13% Рівень',
        line: {
            color: '#1976d2',
            width: 1.2,
            dash: 'dashdot'
        },
        fill: 'tonexty',
        fillcolor: 'rgba(56, 142, 60, 0.15)', // Highlight minimum zone
        hoverinfo: 'name+y'
    };
    
    const val13Plus03Line = {
        x: xValues,
        y: btc13Plus03History50,
        mode: 'lines',
        name: '0.3%',
        line: {
            color: '#7b1fa2',
            width: 1.2,
            dash: 'dash'
        },
        hoverinfo: 'name+y'
    };

    const data = [priceTrace, currentTrace];

    // Overlay Virtual Strategy marker signals if holding active virtual position
    if (virtualTradeState === 'holding' && virtualBuyPrice > 0) {
        const entryTrace = {
            x: [btcPriceHistory50.length],
            y: [virtualBuyPrice],
            mode: 'markers',
            name: 'Точка входу',
            cliponaxis: false,
            marker: {
                color: '#d84315',
                symbol: 'star',
                size: 11,
                line: { color: '#ffffff', width: 1.5 }
            },
            hoverinfo: 'name+y'
        };
        data.push(entryTrace);

        const breakevenTrace = {
            x: [btcPriceHistory50.length],
            y: [virtualBuyPrice * 1.003],
            mode: 'markers',
            name: 'Точка беззбитковості',
            cliponaxis: false,
            marker: {
                color: '#ff8f00',
                symbol: 'diamond',
                size: 9,
                line: { color: '#ffffff', width: 1.5 }
            },
            hoverinfo: 'name+y'
        };
        data.push(breakevenTrace);
    }

    data.push(val75Line, maxLine, avgLine, minLine, val25Line, val13Line, val13Plus03Line);

    // Calculate Y range with padding
    let allDisplayedValues = [...btcPriceHistory50];
    if (btcAverageHistory50.length > 0) allDisplayedValues.push(...btcAverageHistory50);
    if (btc75History50.length > 0) allDisplayedValues.push(...btc75History50);
    if (btc25History50.length > 0) allDisplayedValues.push(...btc25History50);
    if (btc13History50.length > 0) allDisplayedValues.push(...btc13History50);
    if (btc13Plus03History50.length > 0) allDisplayedValues.push(...btc13Plus03History50);
    if (virtualTradeState === 'holding' && virtualBuyPrice > 0) {
        allDisplayedValues.push(virtualBuyPrice);
        allDisplayedValues.push(virtualBuyPrice * 1.003);
    }
    
    let yMinVal = Math.min(...allDisplayedValues);
    let yMaxVal = Math.max(...allDisplayedValues);
    const currentDiff = yMaxVal - yMinVal;
    const padding = currentDiff > 0 ? currentDiff * 0.05 : 10;
    const yMin = yMinVal - padding;
    const yMax = yMaxVal + padding;

    // Adjust chart height dynamically according to data volatility
    let ratio = 1;
    if (maxPrice > minPrice) {
        ratio = (yMaxVal - yMinVal) / (maxPrice - minPrice);
    }
    const dynamicHeight = Math.max(300, Math.min(600, Math.round(300 * ratio)));
    chartDiv.style.height = `${dynamicHeight}px`;

    const layout = {
        margin: { t: 15, b: 70, l: 65, r: 25 },
        height: dynamicHeight - 15,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        showlegend: true,
        legend: {
            orientation: 'h',
            y: -0.32,
            x: 0.5,
            xanchor: 'center',
            font: { size: 9, color: '#2C1A11' }
        },
        xaxis: {
            gridcolor: 'rgba(218, 192, 163, 0.15)',
            tickfont: { size: 9, color: '#2C1A11' },
            range: [1, btcPriceHistory50.length + Math.max(1, btcPriceHistory50.length * 0.02)],
            dtick: Math.max(1, Math.ceil(btcPriceHistory50.length / 10)),
            title: {
                text: `Оновлення (останні ${btcPriceHistory50.length})`,
                font: { size: 10, color: '#8B5E3C' }
            }
        },
        yaxis: {
            gridcolor: 'rgba(218, 192, 163, 0.15)',
            tickfont: { size: 9, color: '#2C1A11' },
            range: [yMin, yMax],
            exponentformat: 'none',
            tickformat: '$,.2f'
        },
        hovermode: 'closest',
        transition: {
            duration: 300,
            easing: 'cubic-in-out'
        },
        frame: {
            duration: 300
        }
    };

    const config = {
        responsive: true,
        displayModeBar: false
    };

    Plotly.react('metrics-history-chart', data, layout, config);
}

// ==========================================
// 7. EXCHANGE MAIN UI REFRESH
// ==========================================

/**
 * Updates wallet balance labels and calculates user's active portfolio metrics
 */
function updateExchangeUI() {
    const usdEl = document.getElementById('wallet-usd-balance');
    const btcEl = document.getElementById('wallet-btc-balance');
    const priceEl = document.getElementById('exchange-btc-price');

    if (usdEl) usdEl.textContent = `$${walletUsd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    if (btcEl) btcEl.textContent = walletBtc.toFixed(8);
    if (priceEl) {
        if (currentBtcPrice > 0) {
            priceEl.textContent = `$${currentBtcPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        } else {
            priceEl.textContent = '$-.--';
        }
    }

    // Refresh active position logs
    const detailsEl = document.getElementById('exchange-position-details');
    const logBoxEl = document.getElementById('exchange-position-log');
    if (detailsEl && logBoxEl) {
        if (walletBtc > 0 && activePosition) {
            logBoxEl.className = 'position-log-box active-pos';
            detailsEl.innerHTML = `
                <div>Кількість BTC в утриманні: <strong>${activePosition.btcAmount.toFixed(8)} BTC</strong></div>
                <div style="margin-top: 4px;">Дата купівлі: <strong>${activePosition.purchaseDate}</strong></div>
                <div style="margin-top: 4px;">Курс купівлі: <strong>$${activePosition.purchasePrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</strong></div>
            `;
        } else {
            logBoxEl.className = 'position-log-box';
            detailsEl.textContent = 'Активні операції відсутні';
        }
    }

    // Calculate & Refresh main User metrics
    const totalEquity = walletUsd + (walletBtc * (currentBtcPrice > 0 ? currentBtcPrice : 0));
    const netProfit = totalEquity - 100.00;
    const netProfitPct = (netProfit / 100.00) * 100;
    const avgBuyPrice = activePosition ? activePosition.purchasePrice : 0.0;
    
    let unrealizedPnl = 0.0;
    let unrealizedPnlPct = 0.0;
    if (walletBtc > 0 && avgBuyPrice > 0 && currentBtcPrice > 0) {
        unrealizedPnl = walletBtc * (currentBtcPrice - avgBuyPrice);
        unrealizedPnlPct = ((currentBtcPrice - avgBuyPrice) / avgBuyPrice) * 100;
    }

    const totalEquityEl = document.getElementById('metrics-total-equity');
    const netProfitEl = document.getElementById('metrics-net-profit');
    const avgBuyPriceEl = document.getElementById('metrics-avg-buy-price');
    const unrealizedPnlEl = document.getElementById('metrics-unrealized-pnl');

    if (totalEquityEl) {
        totalEquityEl.textContent = `$${totalEquity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    if (netProfitEl) {
        const sign = netProfit >= 0 ? '+' : '';
        netProfitEl.textContent = `${sign}$${netProfit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${sign}${netProfitPct.toFixed(2)}%)`;
        if (netProfit > 0) {
            netProfitEl.style.color = '#2e7d32'; // Green
        } else if (netProfit < 0) {
            netProfitEl.style.color = '#c62828'; // Red
        } else {
            netProfitEl.style.color = 'var(--coffee-dark)';
        }
    }

    if (avgBuyPriceEl) {
        if (avgBuyPrice > 0) {
            avgBuyPriceEl.textContent = `$${avgBuyPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        } else {
            avgBuyPriceEl.textContent = '$-.--';
        }
    }

    if (unrealizedPnlEl) {
        if (walletBtc > 0 && avgBuyPrice > 0 && currentBtcPrice > 0) {
            const sign = unrealizedPnl >= 0 ? '+' : '';
            unrealizedPnlEl.textContent = `${sign}$${unrealizedPnl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${sign}${unrealizedPnlPct.toFixed(2)}%)`;
            if (unrealizedPnl > 0) {
                unrealizedPnlEl.style.color = '#2e7d32'; // Green
            } else if (unrealizedPnl < 0) {
                unrealizedPnlEl.style.color = '#c62828'; // Red
            } else {
                unrealizedPnlEl.style.color = 'var(--coffee-dark)';
            }
        } else {
            unrealizedPnlEl.textContent = '$-.--';
            unrealizedPnlEl.style.color = 'var(--coffee-dark)';
        }
    }

    // Refresh Price History & Statistics Section
    updatePriceHistoryMetrics();
}
