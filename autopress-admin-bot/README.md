# AutoPress Admin Telegram Bot

Production-ready Telegram administration bot for the AutoPress Fayda ID Print Automation platform.

**Scope:** Exclusively manages users, manual payment top-up requests, credit balances, and processing activity associated with `@AutoPressFaydaBot`. Website-only users and public customer routes remain isolated.

---

## Architecture Overview

```text
Authorized Telegram Admin
       │
       ▼
[Admin Telegram Bot] (python-telegram-bot v22.8)
       │  (Strict Numeric ID Authorization + Rate Limiting)
       │
       ▼  (Authenticated HTTP / Bearer Token)
[AutoPress Flask Backend] (http://localhost:5000)
       │  (Atomic DB Transactions, WAL Mode, Foreign Keys)
       │
       ▼
[autopress.db] (Central SQLite Database)
   ├── users (source='telegram')
   ├── payment_receipts (PENDING/APPROVED/REJECTED)
   ├── credit_transactions (Ledger Audit Trail)
   └── processing_records (Fayda ID PDF jobs)
```

---

## Features

1. **Strict Numeric ID Authorization**: Whitelists only configured numeric Telegram IDs in `ADMIN_TELEGRAM_IDS` / `ADMIN_TELEGRAM_ID`. Rejects usernames or unverified users at both command and callback level.
2. **10-Item Main Dashboard**:
   - `👥 Registered Users`: Paginated list of users registered via the Telegram bot.
   - `🔍 Search User`: Instant lookup by Telegram ID, `@username`, internal user ID, or name.
   - `💳 Manage Credits`: Controlled workflow (Display balance → Select Add/Deduct → Validate amount → Audit reason → Confirmation screen → Commit & notify user).
   - `⏳ Pending Payments`: Review manual top-up requests with requested credits and amount in ETB.
   - `🖼️ View Receipt Image`: Directly downloads and displays payment proof screenshots.
   - `✅ Approve Payment`: Atomically issues requested credits, updates status, and confirms receipt idempotently.
   - `❌ Reject Payment`: Rejection with administrator audit note.
   - `📜 Payment History`: Complete paginated payment audit trail.
   - `📊 Transaction History`: Live ledger entries showing amounts, reasons, and balance after.
   - `🖨️ Processing Jobs`: Audit completed and failed PDF processing batches.
   - `📈 Statistics`: Clear distinction between ETB revenue and operational credit quantities.
   - `🔔 Notifications`: Toggle administrative notifications.

---

## Prerequisites & Installation (Parrot OS Linux)

### 1. Requirements
- Python 3.10+ (Tested on Python 3.13)
- An active AutoPress backend running on `http://localhost:5000`

### 2. Virtual Environment Setup
From the repository root:
```bash
cd ~/Desktop/AutoPress/autopress-admin-bot

# If venv is not yet created:
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt
```

---

## Environment Configuration

Create or update `.env` in `autopress-admin-bot/`:

```env
# Telegram Bot Token from @BotFather for the Admin Bot
ADMIN_BOT_TOKEN=8791941649:AAFjIHi5qWlqy8jx0Y4YMdcylQC2dEgtrnM

# Authorized Administrator Numeric Telegram IDs (comma-separated if multiple)
ADMIN_TELEGRAM_IDS=1806429941

# AutoPress Backend API Base URL
BACKEND_BASE_URL=http://localhost:5000

# Backend Authentication Credentials
ADMIN_EMAIL=admin@autopress.com
ADMIN_PASSWORD=Admin123456!

# Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL=INFO
```

---

## Running the Admin Bot

Ensure the AutoPress backend is running, then launch the admin bot:

```bash
cd ~/Desktop/AutoPress/autopress-admin-bot
source venv/bin/activate
python bot.py
```

### Running as a Background Daemon (Optional)
```bash
nohup python bot.py > admin_bot.log 2>&1 &
```

---

## Running Automated Tests

Run the automated test suite covering authorization, backend API integration, input validation, and interactive workflows:

```bash
cd ~/Desktop/AutoPress/autopress-admin-bot
source venv/bin/activate
python -m unittest discover tests -v
```

---

## Security Checklist Before Production

- [x] **No Hardcoded Secrets**: Tokens and credentials loaded strictly from `.env`.
- [x] **Git Protection**: `.env` and `venv/` are listed in `.gitignore`.
- [x] **Numeric ID Verification**: Authorization checks `effective_user.id` against integer whitelist, never trusting usernames.
- [x] **Input Sanitization**: HTML escaping (`html.escape`) applied to all user-provided strings before rendering.
- [x] **Idempotent Financial Operations**: Backend enforces unique transactions, prevents double credit issuance, and locks concurrent balance deductions.
- [x] **Error Shielding**: Stack traces and backend secrets are filtered from user-facing error messages.

