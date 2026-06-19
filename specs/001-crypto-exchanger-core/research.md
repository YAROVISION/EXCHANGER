# Technical Research: Crypto Exchanger Core (Ядро обмінника криптовалют)

У цьому документі наведено дослідження та обґрунтування технічних рішень для проекту симулятора торгівлі «Обмінник».

---

## 1. Джерело даних (Binance API)

### Обране рішення
Використання **Binance Public REST API** (`https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT` та `ETHUSDT`) з періодичним опитуванням (polling) кожні 5 секунд.

### Обґрунтування
- **WebSocket (wss://stream.binance.com:9443/ws)** дає надто велику частоту оновлень (кілька разів на секунду), що вимагатиме агрегації на нашій стороні для збереження рівно 1 тіку на 5 секунд.
- **REST API** з простим `setInterval` або планувальником дозволяє точно контролювати частоту запитів (1 запит на 5 секунд) та мінімізувати навантаження на мережу та базу даних.

### Альтернативи
- *Binance WebSocket Stream*: Відхилено через надмірну складність фільтрації та обмеження частоти записів до БД.

---

## 2. Збереження та очищення історії (Supabase FIFO)

### Обране рішення
Використання **PostgreSQL Trigger** у Supabase. При кожній вставці нового тіку для конкретного символу автоматично видаляються найстаріші тіки, якщо їхня кількість для цього символу перевищує 17280.

#### SQL Реалізація:
```sql
CREATE OR REPLACE FUNCTION prune_old_ticks()
RETURNS TRIGGER AS $$
BEGIN
  DELETE FROM crypto_ticks
  WHERE id IN (
    SELECT id FROM crypto_ticks
    WHERE symbol = NEW.symbol
    ORDER BY created_at DESC
    OFFSET 17280
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_prune_old_ticks
AFTER INSERT ON crypto_ticks
FOR EACH ROW
EXECUTE FUNCTION prune_old_ticks();
```

### Обґрунтування
- **Trigger у БД** гарантує цілісність даних на рівні СУБД, незалежно від того, звідки вставляються записи.
- Очищення через `OFFSET 17280` працює як FIFO-черга і є високоефективним.

### Альтернативи
- *Очищення на стороні Worker*: Відхилено, оскільки це збільшує кількість запитів до бази даних (потрібно спочатку рахувати кількість, а потім слати `DELETE`).

---

## 3. Авторизація для одного користувача (`yarovision@gmail.com`)

### Обране рішення
1. **Налаштування Supabase Auth**: Реєстрація нових користувачів відключається в панелі керування Supabase Auth (disable signups).
2. **Перевірка на фронтенді**: Після успішного входу через Email/Пароль фронтенд перевіряє `user.email === 'yarovision@gmail.com'`. Якщо ні — викликається `supabase.auth.signOut()` та показується помилка.
3. **Database RLS (Row Level Security)**: Додаємо правила RLS, які дозволяють читання та запис тільки користувачу з конкретним email.

#### RLS Policy Приклад:
```sql
CREATE POLICY "Only yarovision can access wallets" ON user_wallets
  FOR ALL
  USING (auth.jwt() ->> 'email' = 'yarovision@gmail.com');
```

### Обґрунтування
- RLS на рівні бази даних гарантує, що навіть у разі зламу фронтенду, інші користувачі не зможуть прочитати чи змінити дані в Supabase.

---

## 4. Стек технологій та Дизайн

### Обране рішення
- **Frontend**: Single Page Application на **Vite + Vanilla JS** (без важких фреймворків для швидкого завантаження).
- **Backend/Worker**: Невеликий Node.js JS-скрипт (Worker), який працює паралельно з фронтендом та забезпечує безперервне збирання даних кожні 5 секунд.
- **Дизайн**: Колірна гама "Coffee & Espresso" (CSS змінні у `:root`), шрифт `JetBrains Mono`, адаптивна верстка під мобільні та десктопні пристрої, скляні ефекти (glassmorphism) для інтерфейсу торгівлі.
