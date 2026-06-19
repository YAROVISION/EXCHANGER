# Exchanger (Обмінник) Constitution

## Core Principles

### I. Crypto Trading Simulation Focus
The application operates as a real-time cryptocurrency trading simulator. It must reliably fetch current market prices for BTC and ETH from the public Binance API.

### II. Single-User Access Gate
Access is restricted strictly to a single designated user: `yarovision@gmail.com`. 
- Any authentication flow (using Supabase Auth) must check the authenticated user's email.
- If the email does not match `yarovision@gmail.com`, the session must be immediately terminated and access denied.
- Registration/sign-ups for new accounts should be disabled or blocked.

### III. Hard History Limit & Local Caching
To minimize database writes and ensure system reliability:
- Live prices must be appended locally every 5 seconds to `src/data/crypto_ticks.json` (capped at 17280 ticks per symbol locally).
- The local ticks must be uploaded to the Supabase database in a single batch once every hour (3600 seconds).
- The database maintains a rolling history of exactly 17280 price ticks per active trading pair via a PostgreSQL trigger.

### IV. Bootstrapping & Synchronization
Before starting the live price polling loop on application startup or recovery after shutdown:
- The system MUST perform a synchronization check with the Supabase database.
- It must download the latest historical ticks from Supabase if local history is missing or incomplete.
- It must upload any locally stored ticks that have not yet been synced to Supabase.

### V. Visual Identity & Design System
The user interface must convey a premium, cohesive aesthetic utilizing the "Coffee & Espresso" visual scheme:
- **Dark Coffee / Espresso (Primary/Backgrounds)**:
  - `--coffee-dark`: `#2C1A11`
  - `--coffee-darker`: `#1C100A`
  - `--coffee-espresso`: `#3D2517`
- **Milky Coffee / Latte / Cream (Surfaces/Secondary)**:
  - `--coffee-light`: `#D5B99A`
  - `--coffee-cream`: `#EADBC8`
  - `--coffee-latte`: `#F5EBE0`
- **Accent & Borders**:
  - `--coffee-accent`: `#8B5E3C`
  - `--coffee-border`: `#CBB29C`
- **Typography & Layout**:
  - Font family: `'JetBrains Mono', monospace`
  - Reset styles (`* { margin: 0; padding: 0; box-sizing: border-box; }`)
  - Modern, responsive, terminal-like trading interface.
  - **Mobile Responsiveness Constraints**:
    - Mobile layout (< 600px breakpoint) must stack columns vertically and disable any fixed screen-height restrictions (e.g. use `height: auto` instead of `100vh` on the main workspace) to support standard finger scrolling.
    - Tablet layout (600px - 1024px) should dynamically transition elements using flexible layouts.
    - Touch targets (buttons, inputs, links) must have clear padding and sufficient sizes to prevent accidental taps.

## Tech Stack Constraints
- **Core Database & Auth**: Supabase (PostgreSQL + Supabase GoTrue Auth)
- **Market Data Feed**: Binance Public API (REST/WebSockets)
- **Local Cache File**: `src/data/crypto_ticks.json`
- **UI Platform**: Modern Web standard (HTML5, Vanilla CSS custom properties, JS)

## Governance
- Any modifications to the data storage limits or allowed user credentials must be updated in this Constitution document first.
- The UI styles must inherit the CSS custom properties defined in this constitution's Visual Identity section.

**Version**: 1.1.0 | **Ratified**: 2026-06-17 | **Last Amended**: 2026-06-17
