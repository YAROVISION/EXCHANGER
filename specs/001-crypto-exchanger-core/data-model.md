# Data Model: Crypto Exchanger Core (Модель даних)

Цей документ описує схему бази даних PostgreSQL у Supabase, структуру локального файлу збереження котирувань та правила валідації.

---

## 1. Схема локального файлу (`crypto_ticks.json`)
Файл розташований за шляхом `src/data/crypto_ticks.json` та містить серіалізований масив об'єктів тіків. Максимальна кількість записів для кожного символу (`BTCUSDT` та `ETHUSDT`) обмежена числом 17280.

### Структура JSON:
```json
[
  {
    "symbol": "BTCUSDT",
    "price": 68450.25,
    "created_at": "2026-06-17T13:00:00Z"
  },
  {
    "symbol": "ETHUSDT",
    "price": 3520.10,
    "created_at": "2026-06-17T13:00:00Z"
  }
]
```

---

## 2. Таблиці бази даних (Database Tables)

### Таблиця: `crypto_ticks`
Зберігає історію цін, що вивантажується раз на 1 годину.

| Назва стовпця | Тип даних | Обмеження (Constraints) | Опис |
| :--- | :--- | :--- | :--- |
| `id` | `bigint` | `PRIMARY KEY GENERATED ALWAYS AS IDENTITY` | Унікальний ID запису |
| `symbol` | `text` | `NOT NULL` | Назва пари (BTCUSDT, ETHUSDT) |
| `price` | `numeric` | `NOT NULL` | Ціна активу |
| `created_at` | `timestamptz`| `DEFAULT now() NOT NULL` | Час створення запису |

#### Індекси:
- `idx_crypto_ticks_symbol_created`: `(symbol, created_at DESC)`

---

### Таблиця: `wallets`
Зберігає віртуальні баланси користувачів для USD, BTC та ETH.

| Назва стовпця | Тип даних | Обмеження (Constraints) | Опис |
| :--- | :--- | :--- | :--- |
| `id` | `uuid` | `PRIMARY KEY` | Унікальний ID гаманця |
| `user_id` | `uuid` | `UNIQUE NOT NULL` | Зв'язок із таблицею користувачів |
| `usd_balance` | `numeric` | `NOT NULL DEFAULT 100.0` | Баланс USD/USDT |
| `btc_balance` | `numeric` | `NOT NULL DEFAULT 0.0 CHECK (btc_balance >= 0)` | Баланс Bitcoin |
| `eth_balance` | `numeric` | `NOT NULL DEFAULT 0.0 CHECK (eth_balance >= 0)` | Баланс Ethereum |
| `avg_buy_price` | `numeric` | `NOT NULL DEFAULT 0.0` | Середня ціна купівлі BTC |
| `eth_avg_buy_price` | `numeric` | `NOT NULL DEFAULT 0.0` | Середня ціна купівлі ETH |
| `updated_at` | `timestamptz` | `DEFAULT now()` | Час останнього оновлення |

---

### Таблиця: `trades`
Зберігає історію симуляційних угод для BTC та ETH.

| Назва стовпця | Тип даних | Обмеження (Constraints) | Опис |
| :--- | :--- | :--- | :--- |
| `id` | `bigint` | `PRIMARY KEY GENERATED ALWAYS AS IDENTITY` | Унікальний ID угоди |
| `user_id` | `uuid` | `NOT NULL` | Зв'язок із користувачем |
| `symbol` | `text` | `NOT NULL DEFAULT 'BTCUSDT'` | Валютна пара (BTCUSDT або ETHUSDT) |
| `type` | `text` | `NOT NULL CHECK (type IN ('buy', 'sell'))` | Тип угоди |
| `btc_amount` | `numeric` | `NOT NULL` | Кількість купленого/проданого активу |
| `price` | `numeric` | `NOT NULL` | Ціна виконання угоди |
| `fee` | `numeric` | `NOT NULL` | Комісія за угоду (0.1%) |
| `timestamp` | `timestamptz` | `DEFAULT now() NOT NULL` | Час угоди |

---

## 3. Бізнес-правила та Валідація (Business Rules)

1. **Баланс не може бути негативним**: Стовпці балансів у `wallets` мають обмеження `CHECK`.
2. **Локальний FIFO ліміт (17280)**: При кожному записі котирувань у локальний файл система видаляє найстаріші записи для цього `symbol`, якщо загальна кількість тіків перевищує 17280.
3. **Батч-синхронізація (раз на годину)**: Фоновий процес збирає всі тіки, створені з моменту останнього вивантаження, та записує їх у базу Supabase за допомогою одного групового запиту.
4. **Синхронізація при запуску**:
   - При старті завантажуються останні 17280 тіків з Supabase для кожного активу (у разі відсутності локального файлу).
   - Якщо локальний файл має записи, які відсутні у базі Supabase, вони вивантажуються перед початком роботи.
