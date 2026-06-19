---
name: Exchanger Coffee Design System
colors:
  primary: "#2C1A11"       # Dark Coffee / primary text dark / --coffee-dark
  secondary: "#D5B99A"     # Milky Coffee / --coffee-light
  tertiary: "#8B5E3C"      # Accent / --coffee-accent
  neutral: "#1C100A"       # Espresso dark background / --coffee-darker
  surface: "#3D2517"       # Surface / panel background / --coffee-espresso
  on-surface: "#F5EBE0"    # Cream light text / --coffee-latte
  error: "#EF5350"         # Danger red / --color-danger
  success: "#66BB6A"       # Success green / --color-success
  border: "#CBB29C"        # --coffee-border
  cream: "#EADBC8"         # --coffee-cream
typography:
  headline-display:
    fontFamily: JetBrains Mono
    fontSize: 1.8rem
    fontWeight: 700
    lineHeight: 1.2
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 1.3rem
    fontWeight: 700
    lineHeight: 1.2
  body-md:
    fontFamily: JetBrains Mono
    fontSize: 0.95rem
    fontWeight: 400
    lineHeight: 1.5
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 0.8rem
    fontWeight: 600
    letterSpacing: 0.05em
    textTransform: uppercase
rounded:
  sm: 4px
  md: 6px
  lg: 12px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-surface}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.md}"
    padding: 12px 24px
  button-primary-hover:
    backgroundColor: "#A06D46"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
    border: "1px solid {colors.border}"
---
## Overview
Дизайн-система Exchanger базується на естетиці «Кава та Еспресо». Візуальний стиль є монохромним, теплим і технологічним за рахунок використання моноширинного шрифту JetBrains Mono. Основна увага приділяється контрасту між глибокими кавовими відтінками фону та ніжними вершковими тонами елементів інтерфейсу.

## Colors
Палітра базується на п'яти основних тонах кавової гами:
- `neutral` (`#1C100A`): найтемніший еспресо для загального фону додатку.
- `surface` (`#3D2517`): насичений еспресо для карток, панелей та модальних вікон.
- `primary` (`#2C1A11`): темно-кавовий відтінок для тексту на світлому фоні.
- `on-surface` (`#F5EBE0`): ніжна пінка лате для основного світлого тексту та важливих міток.
- `border` (`#CBB29C`): середньо-кремовий колір для розділювальних ліній.
- `tertiary` (`#8B5E3C`): теплий кавовий колір-акцент для активних кнопок та фокусування.

Для статусів використовуються:
- `success` (`#66BB6A`) — зелений колір успішних операцій.
- `error` (`#EF5350`) — червоний колір помилок та скасування.

## Typography
Використовується виключно шрифт **JetBrains Mono** для додання інтерфейсу вигляду фінансового торгового терміналу.
- `headline-display` (1.8rem, bold) — для заголовка екрану входу.
- `headline-lg` (1.3rem, bold) — для заголовків панелей та карток.
- `body-md` (0.95rem, regular) — для основного вмісту, форм та списків.
- `label-caps` (0.8rem, semi-bold, uppercase) — для підписів кнопок та вкладок.

## Layout & Spacing
- Інтервали базуються на фіксованій сітці: `xs` (4px), `sm` (8px), `md` (16px), `lg` (24px) та `xl` (40px).
- Радіуси округлення кутів (`rounded`): `sm` (4px) для дрібних елементів/інпутів, `md` (6px) для кнопок, `lg` (12px) для панелей та карток входу.

## Components
### Buttons
- **Основні кнопки** (`button-primary`) використовують колір фону `tertiary` та колір тексту `on-surface`. На ховері колір змінюється на світліший варіант `#A06D46`.
- **Кнопки дій** (Buy / Sell) мають власні колірні коди: КУПИТИ використовує зелений фон, ПРОДАТИ — червоний фон.

### Cards
- Картки (`card`) мають округлення `lg` (12px), внутрішні відступи `lg` (24px) та тонку рамку 1px кольору `border`.

## Do's and Don'ts
- **DO** дотримуватися виключно шрифту JetBrains Mono для всіх елементів додатку.
- **DO** використовувати округлення кутів 12px для всіх панелей.
- **DON'T** використовувати білий або занадто яскраві неонові кольори для фонів та кнопок.
- **DON'T** змінювати колір рамок на будь-який інший, окрім `border` (`#CBB29C`) або `tertiary` (`#8B5E3C`) при фокусуванні.
