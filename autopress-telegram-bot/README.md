# AutoPress Telegram Bot

An independent Telegram Bot service for **AutoPress** that acts as a client to the existing AutoPress backend API.

## Architecture

```text
Telegram User
      ↓
Telegram Bot (autopress-telegram-bot)
      ↓
Handlers (Interaction & Routing)
      ↓
Services (Business Logic)
      ├── User Service
      ├── Credit Service
      ├── Job Service
      ├── Payment Service
      └── AutoPress API Service
                    ↓
          Existing AutoPress Backend (AutoPress-backend)
                    ↓
          Existing Processing Engine
```

> **Note**: This bot is a standalone client service. It does **not** duplicate or re-implement the Fayda/PDF processing engine, rembg, or OCR logic; instead, it delegates processing requests to the AutoPress backend API.

---

## Project Structure

```text
autopress-telegram-bot/
├── bot.py                     # Entry point & bot lifecycle initialization
├── config.py                  # Environment & settings loader
├── requirements.txt           # Python dependencies
├── .env.example               # Example environment configuration
├── .gitignore                 # Git ignore rules
├── README.md                  # Documentation
│
├── handlers/                  # Telegram interaction & command handlers
│   ├── __init__.py
│   ├── start.py               # /start command handler
│   ├── menu.py                # Main menu & navigation handlers
│   ├── upload.py              # PDF upload & batch file handling
│   ├── credits.py             # Balance check & credit purchase handlers
│   ├── jobs.py                # Job history & status checking
│   ├── profile.py             # User profile & account details
│   ├── language.py            # Language switcher (English / Amharic)
│   └── help.py                # /help and support information
│
├── services/                  # Business & domain logic
│   ├── __init__.py
│   ├── autopress_api.py       # HTTP client connecting to AutoPress backend
│   ├── user_service.py        # Telegram user management
│   ├── credit_service.py      # Credit calculation & deduction
│   ├── job_service.py         # Job creation & status polling
│   └── payment_service.py     # Payment verification & manual top-up handling
│
├── database/                  # Data layer (SQLite / PostgreSQL)
│   ├── __init__.py
│   ├── models.py              # Database schema definitions
│   ├── database.py            # DB engine & session factory
│   └── repositories/          # Repository abstraction layer
│       ├── __init__.py
│       ├── user_repository.py
│       ├── credit_repository.py
│       ├── job_repository.py
│       └── payment_repository.py
│
├── keyboards/                 # Inline and Reply keyboard builders
│   ├── __init__.py
│   ├── main_menu.py           # Main dashboard keyboards
│   ├── upload.py              # File slot & upload actions
│   ├── credits.py             # Top-up & packages keyboards
│   └── common.py              # Back, Cancel, Confirm buttons
│
├── states/                    # Conversation state machine
│   ├── __init__.py
│   └── conversation_states.py # State definitions (IDLE, WAITING_FOR_PDF, etc.)
│
├── utils/                     # Shared utilities
│   ├── __init__.py
│   ├── messages.py            # Message formatting & templating
│   ├── validators.py          # PDF validation & format checks
│   └── logger.py              # Logging setup
│
├── locales/                   # Multilingual localization
│   ├── en.py                  # English language pack
│   └── am.py                  # Amharic language pack
│
└── tests/                     # Unit and integration test suite
    ├── __init__.py
    ├── test_users.py
    ├── test_credits.py
    ├── test_jobs.py
    └── test_handlers.py
```

---

## Setup & Running

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Configure your `TELEGRAM_BOT_TOKEN` and `AUTOPRESS_API_URL` in `.env`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```
