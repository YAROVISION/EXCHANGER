# Quickstart & Validation Guide: Crypto Exchanger Core

Цей посібник містить інструкції щодо розгортання, налаштування та верифікації роботи проекту «Обмінник».

---

## 📋 Передумови (Prerequisites)
- **Python**: версія 3.12 або новіша
- **Supabase**: безкоштовний проект (акаунт на [supabase.com](https://supabase.com))
- **Доступ до Інтернету**: для отримання даних з Binance API

---

## 🚀 Крок 1: Налаштування бази даних (Supabase SQL Editor)

### Варіант А: Створення нових таблиць з нуля
Скопіюйте та виконайте наступний SQL-код у розділі **SQL Editor** вашого Supabase-проекту:

```sql
-- 1. Створення таблиць
CREATE TABLE IF NOT EXISTS public.crypto_ticks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol text NOT NULL,
    price numeric NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS public.wallets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE NOT NULL,
    usd_balance numeric NOT NULL DEFAULT 100.00 CHECK (usd_balance >= 0),
    btc_balance numeric NOT NULL DEFAULT 0.00000000 CHECK (btc_balance >= 0),
    eth_balance numeric NOT NULL DEFAULT 0.00000000 CHECK (eth_balance >= 0),
    avg_buy_price numeric NOT NULL DEFAULT 0.00000000 CHECK (avg_buy_price >= 0),
    eth_avg_buy_price numeric NOT NULL DEFAULT 0.00000000 CHECK (eth_avg_buy_price >= 0),
    updated_at timestamptz DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS public.trades (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    symbol text NOT NULL DEFAULT 'BTCUSDT',
    type text NOT NULL CHECK (type IN ('buy', 'sell')),
    btc_amount numeric NOT NULL CHECK (btc_amount > 0),
    price numeric NOT NULL CHECK (price > 0),
    fee numeric NOT NULL CHECK (fee >= 0),
    timestamp timestamptz DEFAULT now() NOT NULL
);

-- 2. Створення індексів
CREATE INDEX IF NOT EXISTS idx_crypto_ticks_symbol_created ON public.crypto_ticks (symbol, created_at DESC);

-- 3. Функція та тригер для очищення історії (FIFO ліміт 17280)
CREATE OR REPLACE FUNCTION prune_old_ticks()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM public.crypto_ticks
    WHERE id IN (
        SELECT id FROM public.crypto_ticks
        WHERE symbol = NEW.symbol
        ORDER BY created_at DESC
        OFFSET 17280
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trigger_prune_old_ticks
AFTER INSERT ON public.crypto_ticks
FOR EACH ROW
EXECUTE FUNCTION prune_old_ticks();

-- 4. Увімкнення RLS (Row Level Security)
ALTER TABLE public.wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crypto_ticks ENABLE ROW LEVEL SECURITY;

-- 5. Політики доступу (RLS Policies)
CREATE POLICY "Allow public read on ticks" ON public.crypto_ticks
    FOR SELECT USING (true);

-- Доступ до гаманців та транзакцій тільки для користувача yarovision@gmail.com
CREATE POLICY "Only yarovision can access wallets" ON public.wallets
    FOR ALL USING (auth.jwt() ->> 'email' = 'yarovision@gmail.com');

CREATE POLICY "Only yarovision can access trades" ON public.trades
    FOR ALL USING (auth.jwt() ->> 'email' = 'yarovision@gmail.com');
```

### Варіант Б: Міграція існуючих таблиць (якщо вони були створені раніше)
Якщо у вас вже створені таблиці `wallets` та `trades`, виконайте наступні команди для додавання підтримки ETH та збереження валютних пар:

```sql
-- 1. Додавання колонок для ETH у таблицю wallets
ALTER TABLE public.wallets 
ADD COLUMN IF NOT EXISTS eth_balance numeric NOT NULL DEFAULT 0.00000000 CHECK (eth_balance >= 0),
ADD COLUMN IF NOT EXISTS eth_avg_buy_price numeric NOT NULL DEFAULT 0.00000000 CHECK (eth_avg_buy_price >= 0);

-- 2. Додавання колонки symbol у таблицю trades
ALTER TABLE public.trades 
ADD COLUMN IF NOT EXISTS symbol text NOT NULL DEFAULT 'BTCUSDT';
```

---

## ⚙️ Крок 2: Конфігурація середовища
Створіть файл `src/.env` або `.env` у корені проекту та додайте ваші ключі Supabase:

```env
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
FLASK_SECRET_KEY=yoursecretkeyhere
```

---

## 🏃 Крок 3: Встановлення та запуск

### 1. Налаштування віртуального середовища та встановлення залежностей
Якщо віртуальне середовище ще не створено або не налаштовано:
```bash
# Створення віртуального середовища
python -m venv .venv

# Встановлення залежностей
# Для Windows:
.\.venv\Scripts\pip install flask flask-cors supabase python-dotenv requests
# Для Linux/macOS:
./.venv/bin/pip install flask flask-cors supabase python-dotenv requests
```

### 2. Запуск додатка
Для запуску Flask додатка (який автоматично запускає фоновий потік для оновлення даних Binance):

#### Варіант А: Без активації середовища (швидкий запуск)
* **Windows (PowerShell/CMD)**:
  ```powershell
  .\.venv\Scripts\python src/app.py
  ```
* **Linux/macOS**:
  ```bash
  ./.venv/bin/python src/app.py
  ```

#### Варіант Б: З попередньою активацією середовища
* **Windows (PowerShell)**:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  python src/app.py
  ```
* **Linux/macOS**:
  ```bash
  source .venv/bin/activate
  python src/app.py
  ```

---

## 🧪 Сценарії ручної верифікації (Manual Verification Scenarios)

### Сценарій 1: Авторизація дозволеного користувача
1. Надішліть `POST` запит на `/api/auth/login` з email `yarovision@gmail.com`.
2. **Очікуваний результат**: Успішний вхід (status code 200), повернення даних користувача.

### Сценарій 2: Спроба авторизації стороннього користувача
1. Надішліть `POST` запит на `/api/auth/login` з будь-яким іншим email.
2. **Очікуваний результат**: Помилка 401 (Unauthorized) або 403 (Forbidden).

### Сценарій 3: Автоматичне виконання лімітних ордерів
1. Увійдіть як `yarovision@gmail.com`.
2. Надішліть `POST` запит на `/api/exchange/limit-order` для купівлі BTC за ціною, трохи вищою за поточну ринкову ціну.
3. **Очікуваний результат**: Ордер створюється та автоматично виконується воркером протягом 5 секунд, баланси гаманця оновлюються, а в таблиці `trades` з'являється новий запис.

---

## 🌐 Деплоймент (Production Deployment)

При перенесенні проекту у реальне робоче середовище (production) вбудований вебсервер Flask використовувати **категорично заборонено**. При запуску ви побачите наступне застереження:
> `WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.`

### Чому не можна використовувати вбудований сервер у продакшені?
- **Низька продуктивність та однопотоковість:** Вбудований сервер не вміє ефективно масштабуватися та обробляти велику кількість одночасних з'єднань. При великому навантаженні запити будуть чергуватися або сервіс зависне.
- **Стабільність та стійкість до збоїв:** Сервер не має механізмів автоматичного перезапуску при критичних помилках чи витоках пам'яті.
- **Ризики безпеки:** У режимі відлагодження (debug mode) сервер виводить детальні системні помилки прямо на екран користувача, що допомагає зловмисникам дізнатися про вразливості системи.

### Рекомендований стек для розгортання

Для надійного запуску проекту рекомендується використовувати наступну зв'язку:

1. **WSGI-сервер (Web Server Gateway Interface):**
   Замість прямого запуску `python src/app.py` використовуйте промислові сервери, які створюють пул фонових процесів (workers) та надійно обробляють запити:
   * **Для Linux/macOS:** [Gunicorn](https://gunicorn.org/)
     ```bash
     pip install gunicorn
     gunicorn --workers 4 --bind 0.0.0.0:5000 src.app:app
     ```
   * **Для Windows:** [Waitress](https://docs.pylonsproject.org/projects/waitress/)
     ```bash
     pip install waitress
     waitress-serve --host=0.0.0.0 --port=5000 src.app:app
     ```

2. **Зворотний проксі (Reverse Proxy):**
   Розташуйте WSGI-сервер за проксі-сервером **Nginx** або **Apache**. Вони відповідатимуть за:
   * Налаштування HTTPS (SSL/TLS шифрування).
   * Захист від базових DDoS-атак та фільтрацію шкідливого трафіку.
   * Швидку віддачу статичних файлів (CSS, JS, зображення), не навантажуючи Python-код.
