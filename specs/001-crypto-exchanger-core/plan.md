# Implementation Plan: Crypto Exchanger Core (Ядро обмінника криптовалют)

**Branch**: `001-crypto-exchanger-core` | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-crypto-exchanger-core/spec.md`

---

## Summary
Створення симулятора торгівлі криптовалютами (BTC та ETH) у форматі єдиного Flask-додатку. Програма буде отримувати ринкові котирування з Binance API кожні 5 секунд у фоновому потоці, записувати дані в локальний JSON-файл (`src/data/crypto_ticks.json`), а раз на 1 годину (3600 секунд) виконувати груповий експорт у Supabase. При старті додатка виконується двостороння синхронізація для відновлення історії.

---

## Technical Context

**Language/Version**: Python 3.12+, HTML5, ES6 JavaScript, CSS3
**Primary Dependencies**: `Flask`, `flask-cors`, `supabase`, `python-dotenv`
**Storage**: Локальний JSON (`src/data/crypto_ticks.json`) + Supabase (таблиці `crypto_ticks`, `wallets`, `trades`)
**Testing**: Ручна верифікація за сценаріями специфікації
**Target Platform**: Desktop & Mobile Web
**Project Type**: Flask Web Application із фоновим воркером та системою синхронізації
**Performance Goals**: Оновлення локальних котирувань кожні 5 секунд; експорт у Supabase раз на 1 годину; час виконання ордера/угоди < 1 секунди
**Constraints**: Ліміт 17280 тіків на символ; авторизація тільки для `yarovision@gmail.com`; оформлення у стилі "Coffee & Espresso" та шрифт `JetBrains Mono`

---

## Constitution Check

- **Правило I (Crypto Trading Focus)**: ПРОЙДЕНО.
- **Правило II (Single-User Access)**: ПРОЙДЕНО.
- **Правило III (Hard History Limit & Local Caching)**: Тіки записуються локально кожні 5 секунд та обмежуються лімітом 17280 записів. Експорт у Supabase відбувається раз на 1 годину. (ПРОЙДЕНО)
- **Правило IV (Bootstrapping & Synchronization)**: При запуску додатка виконується синхронізація локальних тіків з базою Supabase. (ПРОЙДЕНО)
- **Правило V (Visual Identity)**: ПРОЙДЕНО.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-crypto-exchanger-core/
├── plan.md              # Цей файл
├── research.md          # Результати досліджень
├── data-model.md        # Опис бази даних та файлової структури
├── quickstart.md        # Інструкція швидкого запуску
└── tasks.md             # Список завдань для реалізації
```

### Source Code (repository root)

```text
src/
├── app.py               # Flask додаток, фоновий воркер та логіка синхронізації
├── data/
│   └── crypto_ticks.json # Локальний файл збереження тіків (до 17280 на символ)
├── static/
│   ├── js/
│   │   └── main.js      # Клієнтська логіка
│   ├── css/
│   │   └── styles.css   # Фірмові кавові стилі
│   └── index.html       # Головна сторінка UI
├── .env                 # Налаштування Supabase та Flask
└── requirements.txt     # Залежності Python
```

---

## Responsive Design & Layout Adaptation
Для відповідності вимозі **FR-009**, інтерфейс розроблено за допомогою гнучких сіток (CSS Grid) та флексбоксів (Flexbox) з підтримкою трьох рівнів адаптивності через CSS Media Queries:
1. **Десктопи (>= 1024px)**: Класичний триколонковий макет робочої області (`.workspace`) з фіксованою висотою `100vh` та незалежною прокруткою колонок.
2. **Планшети (600px - 1023px)**: Двоколонковий або гнучкий макет з можливістю перенесення блоків.
3. **Мобільні пристрої (< 600px)**: Одноколонкова структура (вертикальний стек панелей) з автоматичною висотою головного контейнера (`height: auto`), що забезпечує природне прокручування сторінки та зручне сенсорне керування. Також елементи шапки (`.app-header`) трансформуються у гнучкі адаптивні блоки для запобігання перекриттю тексту.

## Multi-Asset Architecture (BTC & ETH)
Для відповідності вимозі **FR-011**, архітектуру додатка було розширено для підтримки кількох торгових активів:
1. **Сховище даних**:
   * Таблиця `wallets` отримала поля `eth_balance` та `eth_avg_buy_price` для ізольованого зберігання балансів.
   * Таблиця `trades` отримала колонку `symbol` для розрізнення угод між BTCUSDT та ETHUSDT.
2. **Торгова сесія**:
   * Лімітні ордери тепер зберігаються окремо в сесії для кожного активу: `limit_order` та `sell_limit_order` для BTC, `limit_order_eth` та `sell_limit_order_eth` для ETH.
3. **Клієнтський інтерфейс**:
   * Тікери в хедері виступають як кнопки вибору активного токена, перемикаючи глобальний стан `state.selectedAsset`.
   * Всі відображення балансів, орієнтирів продажу, форм торгівлі та історії транзакцій динамічно перебудовуються і фільтруються клієнтським скриптом.

## Complexity Tracking

*Жодних порушень конституції.*
