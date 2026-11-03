# AutoPress

Enterprise-grade AI-powered National ID (Fayda) processing, document layout imposition, and print shop automation platform. AutoPress delivers real-time document analysis with computer vision, multimodal generative AI, automated background removal, barcode generation, transactional credit management, and multi-card print-ready PDF/PNG rendering -- all orchestrated across a modern web dashboard and dedicated Telegram bot interfaces.

**Creator / Lead Developer:** Bilal Mohamed

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Features](#features)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Installation](#installation)
8. [Configuration](#configuration)
9. [Running the Platform](#running-the-platform)
10. [API Documentation](#api-documentation)
11. [AI Vision & Document Processing Pipeline](#ai-vision--document-processing-pipeline)
12. [Frontend Dashboard](#frontend-dashboard)
13. [Telegram Bots Ecosystem](#telegram-bots-ecosystem)
14. [Credit Ledger & Financial Operations](#credit-ledger--financial-operations)
15. [Infrastructure & Deployment](#infrastructure--deployment)
16. [Environment Variables](#environment-variables)
17. [Contributor](#contributor)
18. [License](#license)

---

## Overview

**AutoPress** is an end-to-end, production-ready print shop automation and document processing platform engineered to streamline the ingestion, enhancement, extraction, and print layout formatting of official identification documents, with a specialized focus on Ethiopian **Fayda National IDs** and custom event cards. 

Commercial print shops frequently lose billable hours manually cropping photos, adjusting Amharic/Ethiopic typography, aligning front-and-back ID cards to standard CR80 PVC dimensions, and tiling multiple customer orders onto single sheets for laminate and direct-to-card printers. AutoPress eliminates this manual labor by unifying state-of-the-art vision models, local neural network segmentation, dynamic barcode synthesis, and automated multi-card imposition templates into an instant, high-throughput pipeline.

### Key Capabilities

* **Multimodal AI ID Extraction:** Automated recognition and extraction of complex bilingual (Amharic & English) ID fields using Google Gemini Vision with intelligent multi-key rotation and zero-loss fallback.
* **Neural Portrait Background Removal:** Sub-second local human silhouette segmentation via ONNX Runtime (`u2net_human_seg` and `birefnet-portrait`) for studio-quality ID photos.
* **Pixel-Perfect Multi-Card Imposition:** Generates print-ready vector PDFs and ultra-high-resolution PNGs with 1, 2, 3, 4, and 5-card layout templates, standard CR80 dimensions, exact bleed, cut guides, and front-to-back coordinate mirroring.
* **Ethiopic Script & Typography Engine:** Full typography rendering with native Ge'ez unicode support utilizing `VisualGeez Unicode` and `Noto Sans Ethiopic` font families.
* **Transactional Credit Ledger:** ACID-compliant credit balance engine with immutable transaction logging, preventing race conditions during concurrent document generation.
* **Dual Telegram Interfaces:**
  * **User Bot (`AutoPressFaydaBot`):** Complete conversational workflow in English and Amharic for uploading documents, previewing cards, checking balances, and submitting payment receipts.
  * **Admin Bot (`AutoPressAdminBot`):** Back-office mobile control center for inspecting audit trails, approving CBE/telebirr payments, allocating credits, searching users, and broadcasting alerts.
* **Modern Web Dashboard:** React 19 and Tailwind CSS web portal with drag-and-drop PDF slot uploaders and interactive side-by-side print previews.
* **Flexible Payment Gateway Verification:** Supports Commercial Bank of Ethiopia (CBE) and Telebirr manual payment verification workflows with screenshot upload and admin review.

---

## Architecture

```
                               +-----------------------------+
                               |     Client Access Points    |
                               |  Web, User Bot, Admin Bot   |
                               +--------------+--------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
         +-----------v-----------+                         +-----------v-----------+
         |  React Web Dashboard  |                         | Telegram Bot Services |
         |   (Vite, Tailwind)    |                         | User Bot & Admin Bot  |
         |      Port 5173        |                         | (python-telegram-bot) |
         +-----------+-----------+                         +-----------+-----------+
                     |                                                 |
                     +------------------------+------------------------+
                                              | HTTP / REST (JWT / API Key)
                                              v
                               +-----------------------------+
                               |     AutoPress REST API      |
                               |       (Python Flask)        |
                               |          Port 5000          |
                               +--------------+--------------+
                                              |
         +--------------------+---------------+--------------------+
         |                    |               |                    |
+--------v--------+  +--------v--------+  +---v-------------+  +---v-------------+
|  AI Vision &    |  |  ONNX Runtime   |  |   PyMuPDF &     |  |  Credit Ledger  |
| Gemini Service  |  | u2net Rembg     |  |  ReportLab Engine| |  Engine (ACID)  |
| (Multi-Key Rot) |  | (Local CPU/GPU) |  | (Multi-Card PDF)|  | (Double-Entry)  |
+--------+--------+  +--------+--------+  +---+-------------+  +---+-------------+
         |                    |               |                    |
         +--------------------+---------------+--------------------+
                                              |
                               +--------------v--------------+
                               |     Persistence Layer       |
                               |   SQLite (WAL Mode) / DB    |
                               |  Firebase Auth & Storage    |
                               +-----------------------------+
```

### System Architecture & Microservices

| Service | Technology | Role | Port(s) |
|---|---|---|---|
| **`autopress-backend`** | Python 3.11+, Flask, Gunicorn | Authoritative REST API, document processor, credit ledger, auth | `5000` |
| **`autopress-frontend`** | React 19, Vite, Tailwind CSS | Web dashboard, multi-slot document uploader, PDF viewer | `5173` |
| **`autopress-telegram-bot`** | Python 3.11+, `python-telegram-bot` | Customer-facing Telegram interface (Amharic & English) | Background Service |
| **`autopress-admin-bot`** | Python 3.11+, `python-telegram-bot` | Administrative command center, payment review, user management | Background Service |
| **`database`** | SQLite 3 (WAL mode) / PostgreSQL-ready | Relational datastore for users, credits, jobs, payment receipts | Internal |
| **`ai-vision-engine`** | Google GenAI SDK | Vision parsing, Amharic/English field extraction | External Cloud API |
| **`rembg-engine`** | ONNX Runtime (`u2net_human_seg`) | Local neural portrait segmentation and background extraction | In-Process / Local |

---

## Technology Stack

### Backend & API Framework
| Category | Technology | Description |
|---|---|---|
| **Language** | Python 3.11+ | Core runtime environment |
| **Web Framework** | Flask 3.1.3 | Lightweight, high-performance RESTful API microservice |
| **WSGI Server** | Gunicorn | Production-grade WSGI HTTP server |
| **Authentication** | PyJWT, Firebase Admin SDK | Dual auth engine: JWT Bearer tokens & Firebase UID validation |
| **Database** | SQLite 3 with WAL Mode | Concurrent, zero-latency ACID transactional data storage |
| **Email Service** | SMTPLib / RFC 822 | Async transactional email dispatch and token validation |
| **Security & CORS** | `flask-cors`, Cryptography | Preflight handling, secure origin whitelisting, constant-time validation |

### AI, Computer Vision & Document Synthesis
| Category | Technology | Description |
|---|---|---|
| **Multimodal Vision** | Google Gemini (2.0 / 1.5 Flash) | Field extraction, OCR, Amharic translation, bounding box detection |
| **Key Management** | Multi-Key Fallback Pool | 30-key rotation buffer with error circuit breakers and quota failover |
| **Background Removal** | `rembg[cpu]`, `onnxruntime` | Offline portrait extraction via `u2net_human_seg` and `birefnet` |
| **PDF Engineering** | PyMuPDF (`fitz`), ReportLab | Vector layout imposition, multi-card geometry, bleed margins |
| **Imaging Engine** | Pillow (PIL) 12.1.1 | High-DPI rasterization, affine transformations, color harmonization |
| **Symbology** | `python-barcode` | Code128 and 2D QR synthesis for National Identification Numbers (FAN) |
| **Ethiopic Fonts** | VisualGeez & Noto Sans Ethiopic | Custom TrueType font packaging for flawless Amharic typesetting |

### Frontend Web Dashboard
| Category | Technology | Description |
|---|---|---|
| **Core Framework** | React 19.2 (App & Component model) | Next-generation reactive web application |
| **Build Tool** | Vite 8.3 | Instant HMR and optimized production bundling |
| **Styling** | Tailwind CSS 4.1 | Utility-first, responsive dark-mode styling |
| **Icons** | Lucide React | Modern, lightweight iconography |
| **Identity** | Firebase Client SDK 12.19 | Client-side authentication and session management |
| **Quality** | Oxlint | High-speed Rust-based JavaScript/TypeScript linter |

### Telegram Bot Ecosystem
| Category | Technology | Description |
|---|---|---|
| **Framework** | `python-telegram-bot` v20+ / v22.8 | Asynchronous Telegram API framework using HTTPX |
| **Networking** | HTTPX (Async HTTP Client) | High-concurrency inter-service communication with backend |
| **State Machine** | ConversationHandler | Multi-step interactive dialogs for uploads and payment submissions |
| **Localization** | Custom Locale Matrix | Complete English (`en.py`) and Amharic (`am.py`) UI translation |

---

## Features

### 1. Fayda National ID Processing
* **Automated Bilingual Parsing:** Automatically recognizes and structures:
  * Full Name in English and Amharic
  * Fayda Identification Number (FAN) and FIN
  * Date of Birth (Gregorian and Ethiopian calendar formats)
  * Gender, Phone Number, and Nationality
  * Region, Zone, Woreda, and Kebele address hierarchies
  * Issue and Expiry Dates
* **Neural Portrait Isolation:** Detects profile headshots, segments hair and clothing cleanly from complex backgrounds, and normalizes DPI to 300+ for crystal-clear badge printing.
* **Barcode & QR Generation:** Rebuilds verified Code128 barcodes and digital verification QR codes directly onto the output template.

### 2. Multi-Card Imposition Engine
* **Flexible Layout Slots:** Supports batching from 1 to 5 customer cards onto a single print sheet:
  * `1-card-template.pdf`: Single front & back layout for individual card printers
  * `2-card-template.pdf`: Dual-card imposition for small runs
  * `3-card-template.pdf` & `4-card-template.pdf`: Optimized medium-volume print spreads
  * `5-card-template.pdf`: High-efficiency 5-up A4 imposition for large print shops
* **CR80 Standardization:** Built to ISO/IEC 7810 ID-1 standards (85.60 mm × 53.98 mm) with proper bleed, rounded corner guides, and aligned reverse faces.
* **Dual Output Formats:** Immediate download available in both vector PDF (for professional print rip software) and raster PNG (for quick previewing and thermal printers).

### 3. Credit Ledger & Financial Security
* **Double-Entry Style Ledger:** Every credit change is recorded in an immutable audit ledger (`credit_transactions`) with previous balance, deduction amount, and post-transaction balance.
* **Atomic Deduction:** Database transactions ensure credits are only consumed upon verified successful document generation. If an AI or PDF error occurs, deductions roll back instantly.
* **Package Tiers & Payments:** Integrated support for credit bundles (e.g., 10, 25, 50, 100 credits) with payment receipt submission for Commercial Bank of Ethiopia (CBE) and Telebirr.

### 4. Dual Telegram Bot Infrastructure
* **Customer Self-Service Bot:**
  * Bilingual interface (English & Amharic) with instant `/language` switching
  * Upload single or multiple PDF/image IDs via Telegram chat
  * Real-time credit balance display and job history lookup
  * Payment receipt upload with instant notification to administrators
* **Administrative Operations Bot:**
  * Real-time payment notifications whenever a customer submits a receipt
  * One-click payment approval or rejection with customized reason dispatch
  * Direct user lookup by ID, email, or Telegram username
  * Instant manual credit adjustments (grants, refunds, penalties)
  * System-wide statistics: total active users, jobs processed, and daily revenue

### 5. Wedding & Event Invitation Automation
* Extensible templating system for batching custom wedding cards, event passes, and invitations (`routes/wedding.py`) with localized font typography and automated preview generation.

---

## Project Structure

```
AutoPress/
|
|-- AutoPress-backend/                 # Core Python Flask REST API & Processing Engine
|   |-- app.py                         # Application entrypoint, CORS setup, Blueprint aggregator
|   |-- database.py                    # SQLite schema definition, connection pools, and migrations
|   |-- models.py                      # Data models (User, CreditLedger, ProcessingRecord, Payment)
|   |-- requirements.txt               # Backend dependencies
|   |-- Dockerfile                     # Containerization specification for API service
|   |
|   |-- routes/                        # Modular REST API endpoints
|   |   |-- auth.py                    # User authentication, registration, token refresh
|   |   |-- admin.py                   # System administration, user lists, credit adjustments
|   |   |-- fayda.py                   # Fayda ID processing, multi-card slot submission
|   |   |-- payment.py                 # Payment submission, package listing, status tracking
|   |   |-- user.py                    # User profile, credit balance, transaction history
|   |   +-- wedding.py                 # Wedding card generation and preview endpoints
|   |
|   |-- services/                      # Enterprise business logic layer
|   |   |-- gemini.py                  # Google Gemini vision extraction with 30-key rotation
|   |   |-- bg_remover.py              # Neural background remover (ONNX u2net / BiRefNet)
|   |   |-- pdf_generator.py           # Imposition layout synthesizer, ReportLab & PyMuPDF
|   |   |-- auth_service.py            # Password hashing, JWT creation, authorization guards
|   |   |-- email_service.py           # Transactional SMTP email delivery
|   |   |-- email_validator.py         # MX record validation and address verification
|   |   |-- firebase_service.py        # Firebase Admin token validation and user syncing
|   |   +-- telegram_service.py        # Outbound notification dispatcher to Telegram bots
|   |
|   |-- fb/                            # Firebase Admin SDK bridge
|   |   +-- admin.py                   # Firebase credentials loading & token verification
|   |
|   |-- fonts/                         # Specialized font files for typography rendering
|   |   |-- VisualGeezUnicode.ttf      # Ge'ez Unicode font for Amharic text
|   |   |-- NotoSansEthiopic-Bold.ttf  # Google Noto Sans Ethiopic Bold
|   |   |-- Roboto-Bold.ttf            # Latin header font
|   |   +-- Roboto-SemiBold.ttf        # Latin body font
|   |
|   |-- models/                        # Pre-trained ONNX model weight cache
|   |   +-- u2net_human_seg.onnx       # Local human silhouette segmentation model
|   |
|   |-- static/previews/               # Generated card previews and cached assets
|   +-- templates/                     # Base PDF imposition templates (1 to 5 card spreads)
|       |-- 1-card-template.pdf
|       |-- 2-card-template.pdf
|       |-- 3-card-template.pdf
|       |-- 4-card-template.pdf
|       |-- 5-card-template.pdf
|       |-- id_front.png
|       +-- id_back.png
|
|-- AutoPress-frontend/                # React 19 Web Dashboard
|   |-- package.json                   # Frontend npm dependencies
|   |-- vite.config.js                 # Vite bundler configuration
|   |-- index.html                     # HTML root template
|   |-- src/
|   |   |-- App.jsx                    # Root application component and generation workflow
|   |   |-- main.jsx                   # React DOM mount point
|   |   |-- firebase.js                # Firebase web client configuration
|   |   |-- components/
|   |   |   |-- Navbar.jsx             # Top navigation, brand, user balance pill
|   |   |   |-- PdfSlotUploader.jsx    # Drag-and-drop multi-file slot selector
|   |   |   +-- PdfViewer.jsx          # Interactive PDF render viewer with download controls
|   |   +-- services/
|   |       +-- api.js                 # Axios API bridge to backend endpoints
|
|-- autopress-telegram-bot/            # User-Facing Telegram Bot (Amharic & English)
|   |-- bot.py                         # Polling loop initialization and error handlers
|   |-- config.py                      # Bot settings and environment validation
|   |-- requirements.txt               # Dependencies (`python-telegram-bot`, `httpx`, `pillow`)
|   |-- database/                      # Local bot datastore and repositories
|   |-- handlers/                      # Telegram interaction handlers
|   |   |-- start.py                   # /start and onboarding
|   |   |-- menu.py                    # Main keyboard navigation
|   |   |-- upload.py                  # Document upload and generation trigger
|   |   |-- credits.py                 # Balance check and credit purchase flow
|   |   |-- jobs.py                    # Past jobs and status tracking
|   |   |-- language.py                # English / Amharic language selection
|   |   +-- profile.py                 # User account details and ID linking
|   |-- keyboards/                     # Inline and reply keyboard layouts
|   |-- locales/                       # Bilingual localization dictionaries
|   |   |-- en.py                      # English translations
|   |   +-- am.py                      # Amharic translations
|   +-- services/                      # Backend API consumer and sync services
|
|-- autopress-admin-bot/               # Administrative Management Telegram Bot
|   |-- bot.py                         # Admin bot initialization and command routing
|   |-- config.py                      # Admin authorization and secret validation
|   |-- requirements.txt               # Dependencies
|   |-- handlers/
|   |   |-- start.py                   # Secure admin login and dashboard summary
|   |   |-- users.py                   # User search, details, and status inspection
|   |   |-- payments.py                # Payment receipt queue, one-click approve/reject
|   |   |-- credits.py                 # Interactive credit grant and deduction wizard
|   |   |-- transactions.py            # Global financial ledger inspection
|   |   |-- jobs.py                    # Processing job monitor and error diagnosis
|   |   +-- statistics.py              # Platform KPIs, revenue, and active metrics
|   +-- services/
|       |-- authorization.py           # Admin Telegram ID and whitelist guards
|       +-- backend_client.py          # Secure authenticated client for backend admin APIs
|
|-- scripts/                           # Administrative & maintenance utilities
|   +-- reconcile_balances.py          # Ledger audit and balance reconciliation tool
|
|-- DEPLOY_CREDITS_FIX.md              # Production deployment & database safety guide
+-- README.md                          # Platform documentation
```

---

## Prerequisites

* **Operating System:** Linux (Ubuntu 22.04+ recommended), macOS, or Windows WSL2
* **Python Runtime:** Python 3.11 or higher
* **Node.js Runtime:** Node.js 20.x or higher and `npm`
* **Docker & Docker Compose:** Docker Engine 24.0+ and Compose v2.20+ (for containerized deployments)
* **SQLite 3:** With JSON1 extension (standard in Python 3.11+)
* **External Accounts & Keys:**
  * Google Gemini API Key(s) (supports up to 30 keys for rotation)
  * Telegram Bot Token(s) from `@BotFather` (one for user bot, one for admin bot)
  * Firebase Project credentials (`firebase-service-account.json`) for authentication

---

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Sherin-SEF-AI/AutoPress.git
cd AutoPress
```

### 2. Backend Setup
```bash
cd AutoPress-backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Download local background removal model (u2net)
python -c "from rembg import new_session; new_session('u2net_human_seg')"
```

### 3. Frontend Dashboard Setup
```bash
cd ../AutoPress-frontend

# Install node dependencies
npm install
```

### 4. Telegram Bots Setup
```bash
# Setup Customer Telegram Bot
cd ../autopress-telegram-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup Admin Telegram Bot
cd ../autopress-admin-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

### Backend Environment Configuration
Create `AutoPress-backend/.env`:
```env
# Server
PORT=5000
APP_ENV=production
SECRET_KEY=generate-a-strong-64-character-random-secret
JWT_SECRET=generate-a-strong-64-character-random-secret

# Admin Bootstrap
ADMIN_EMAIL=admin@autopress.com
ADMIN_PASSWORD=SuperSecurePassword123!

# Credit System
CREDIT_COST_PER_DOCUMENT=1
DEFAULT_SIGNUP_CREDITS=2

# Inter-Service Security
AUTOPRESS_SERVICE_SECRET=generate-a-32-byte-hex-secret
AUTOPRESS_ADMIN_BOT_SECRET=generate-a-32-byte-hex-secret
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuvwxYZ

# Google Gemini Vision Keys (Add multiple for automated rotation)
GEMINI_API_KEY_1=AIzaSyD-YourFirstKeyHere
GEMINI_API_KEY_2=AIzaSyD-YourSecondKeyHere
GEMINI_API_KEY_3=AQ...YourDeveloperKeyHere

# Background Removal Models
REMBG_HOME=/app/models
U2NET_HOME=/app/models

# Optional SMTP Transactional Emails
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=notifications@autopress.com
SMTP_PASSWORD=your-app-password
```

### User Telegram Bot Configuration
Create `autopress-telegram-bot/.env`:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuvwxYZ
AUTOPRESS_API_URL=http://localhost:5000
AUTOPRESS_SERVICE_SECRET=your-shared-service-secret
AUTOPRESS_ADMIN_BOT_SECRET=your-shared-admin-secret
DEFAULT_LANGUAGE=am
ADMIN_TELEGRAM_IDS=1806429941,987654321
```

### Admin Telegram Bot Configuration
Create `autopress-admin-bot/.env`:
```env
ADMIN_BOT_TOKEN=987654321:XYZabcDeFGHiJKlmnOPqrSTUVwx
BACKEND_API_URL=http://localhost:5000
AUTOPRESS_ADMIN_BOT_SECRET=your-shared-admin-secret
SUPER_ADMIN_IDS=1806429941
```

---

## Running the Platform

### Option A: Local Development Mode

#### 1. Start the Flask Backend
```bash
cd AutoPress-backend
source venv/bin/activate
python app.py
# Backend starts on http://localhost:5000
```

#### 2. Start the Frontend Dashboard
```bash
cd AutoPress-frontend
npm run dev
# Frontend runs on http://localhost:5173
```

#### 3. Start the Customer Telegram Bot
```bash
cd autopress-telegram-bot
source venv/bin/activate
python bot.py
```

#### 4. Start the Admin Telegram Bot
```bash
cd autopress-admin-bot
source venv/bin/activate
python bot.py
```

---

### Option B: Production Container Deployment

The backend can be built and deployed via Docker:

```bash
cd AutoPress-backend
docker build -t autopress-backend:latest .
docker run -d \
  --name autopress-backend \
  -p 5000:5000 \
  -v $(pwd)/autopress.db:/app/autopress.db \
  -v $(pwd)/models:/app/models \
  --env-file .env \
  --restart unless-stopped \
  autopress-backend:latest
```

> [!IMPORTANT]
> **Database Persistence Notice:** Always ensure `/app/autopress.db` is mounted to a persistent host volume or backed up before restarting containers, as documented in [`DEPLOY_CREDITS_FIX.md`](file:///home/mrsolo/Desktop/AutoPress/DEPLOY_CREDITS_FIX.md).

---

## API Documentation

The backend exposes RESTful endpoints with JSON request and response bodies. Protected user endpoints accept a standard `Authorization: Bearer <token>` header, while inter-service endpoints utilize shared secret headers.

### Core Endpoint Groups

| Group | Route Prefix | Primary Purpose | Auth Method |
|---|---|---|---|
| **Fayda ID** | `/api/fayda/` | Document parsing, multi-card slot imposition, template download | Bearer Token / Service Secret |
| **Authentication** | `/api/auth/` | Registration, login, password recovery, verification | Public / Bearer Token |
| **User & Credits** | `/api/user/` | Balance queries, transaction ledger history, Telegram linking | Bearer Token / Service Secret |
| **Admin Operations** | `/api/admin/` | User management, manual credit grants, financial audits | Admin Bearer / Bot Secret |
| **Payments** | `/api/payment/` | Package catalog, receipt submission, approval webhooks | Bearer Token / Service Secret |
| **Wedding Cards** | `/api/wedding/` | Custom invitation generation and preview rendering | Bearer Token |
| **System Health** | `/health`, `/debug-info` | Service health status, Gemini model connectivity, CORS checks | Public |

---

### Key API Endpoints

#### 1. Process Fayda ID Cards
* **`POST /api/fayda/process-template`**
  * Submits 1 to 5 Fayda National ID documents (PDF or image).
  * Validates user credit balance, parses data via Gemini Vision, removes background from portraits, builds barcodes, renders onto imposition templates, and deducts credits atomically.
  * **Response:** Binary PDF stream (`Content-Type: application/pdf`).

#### 2. Get User Credit Balance
* **`GET /api/user/credits`**
  * Returns current spendable balance and historical credit transactions.
  * **Sample Response:**
    ```json
    {
      "status": "success",
      "user_id": 42,
      "credits": 25,
      "total_spent": 15
    }
    ```

#### 3. Telegram Inter-Service Credit Deduction
* **`POST /api/user/telegram/deduct`**
  * Protected by `X-Service-Secret` header for atomic deductions by `AutoPressFaydaBot`.
  * **Request Body:**
    ```json
    {
      "telegram_user_id": 1806429941,
      "amount": 1,
      "reason": "1-Card Fayda Imposition Generation"
    }
    ```

#### 4. Submit Payment Receipt
* **`POST /api/payment/submit-receipt`**
  * Submits a transaction reference and screenshot for CBE or Telebirr credit pack purchases.
  * **Payload:** `multipart/form-data` with package selection and screenshot.

#### 5. Admin Approve Payment
* **`POST /api/admin/payments/{receipt_id}/approve`**
  * Protected by `X-Admin-Bot-Secret` or Admin JWT. Allocates credits and sends automatic notification to user.

---

## AI Vision & Document Processing Pipeline

AutoPress incorporates a multi-stage computer vision and generative AI pipeline optimized for low latency and zero data distortion:

```
Uploaded Document (PDF / Image)
            |
            v
   [PyMuPDF Rasterizer] --------> High-DPI 300+ RGB Image Buffer
            |
            +------------------------------------+
            |                                    |
            v                                    v
 [Google Gemini Vision AI]             [Local Neural Segmentation]
 (30-Key Dynamic Rotation)             (ONNX Runtime: u2net_human_seg)
            |                                    |
            v                                    v
  Extracted JSON Payload:               Isolated Studio Headshot
  - English & Amharic Names             (Alpha Transparency Masked)
  - FAN / FIN Numbers                            |
  - DOB, Gender, Phone                           |
  - Address Breakdown                            |
            |                                    |
            +-----------------+------------------+
                              |
                              v
                   [Symbology Generator]
               (Code128 Barcode + 2D QR Code)
                              |
                              v
              [ReportLab & PyMuPDF Compositor]
           (VisualGeez & Noto Sans Ethiopic Fonts)
                              |
                              v
             [Multi-Card Imposition Engine]
      (1, 2, 3, 4, or 5-Card CR80 Template Matrix)
                              |
                              v
           Final Output: Print-Ready Vector PDF / PNG
```

### Model Registry & Vision Engine

| Model Component | Framework | Precision | Execution Provider |
|---|---|---|---|
| **Gemini 2.0 / 1.5 Flash** | Google GenAI SDK | Cloud API | Google Cloud Platform |
| **`u2net_human_seg`** | ONNX Runtime | FP32 | CPU (Optimized via OpenVINO/DirectML) or CUDA |
| **`birefnet-portrait`** | ONNX Runtime | FP32 | High-resolution portrait fallback |
| **Code128 Synthesizer** | `python-barcode` | Vector | Native Python vector synthesis |
| **PyMuPDF Compositor** | MuPDF C-Engine | Native | Low-latency binary composition |

---

## Frontend Dashboard

The frontend is a lightweight, responsive web application engineered using **React 19** and **Tailwind CSS 4**:

* **Multi-Slot Document Uploader (`PdfSlotUploader.jsx`):** Allows users to drag-and-drop up to 5 individual PDF or image files. Slots visually indicate fill status and map directly to the corresponding card layout template.
* **Live In-Browser PDF Previewer (`PdfViewer.jsx`):** Embedded viewer rendering the exact generated output without requiring local file saves.
* **Credit Balance Pill (`Navbar.jsx`):** Live credit counter that dynamically updates upon document generation or balance reloads.
* **Direct Download Controls:** One-click instant saving of vector PDFs and high-resolution raster files.

---

## Telegram Bots Ecosystem

```
                       +-----------------------------+
                       |       Telegram Cloud        |
                       +--------------+--------------+
                                      |
                     +----------------+----------------+
                     |                                 |
         +-----------v-----------+         +-----------v-----------+
         |   AutoPressFaydaBot   |         |   AutoPressAdminBot   |
         |    (Customer Bot)     |         |    (Management Bot)   |
         +-----------+-----------+         +-----------+-----------+
                     |                                 |
                     |  - Document Uploads             |  - Payment Verification
                     |  - Language Switch (EN/AM)      |  - User Lookups
                     |  - Credit Balances              |  - Manual Credit Grants
                     |  - Payment Receipts             |  - Platform KPI Reports
                     |                                 |
                     +----------------+----------------+
                                      |
                                      v
                       +-----------------------------+
                       |   AutoPress Backend API     |
                       | (Authenticated Inter-Service)|
                       +-----------------------------+
```

### Customer Bot (`AutoPressFaydaBot`)
* Designed for field print shop operators and end-users on mobile devices.
* **Locales Supported:** Complete Amharic (አማርኛ) and English localization for all dialogs, errors, and receipt notifications.
* **Seamless Document Generation:** Send a PDF or photo directly in chat; the bot interfaces with the backend and returns the formatted print-ready card file within seconds.
* **Payment Submission:** Users select a credit bundle, receive bank transfer details (CBE Account, Telebirr), and submit transaction screenshots directly.

### Admin Bot (`AutoPressAdminBot`)
* Acts as an on-the-go back-office dashboard for platform administrators.
* **Payment Approval Workflow:** Sends an instant notification when a user submits a receipt. Displays user details, amount paid, and screenshot with inline `[ Approve ]` and `[ Reject ]` buttons.
* **User Management:** Search users by ID or username, view transaction histories, ban/unban accounts, or adjust credit allocations with interactive numeric prompts.
* **System Diagnostics:** Query real-time platform statistics including processed job counts, active users, and system error logs.

---

## Credit Ledger & Financial Operations

AutoPress enforces strict double-entry style accounting principles to prevent fraud, duplicate grants, and negative balance errors:

```
[User Action: Generate 3-Card Template]
                  |
                  v
       Verify Balance >= 3 Credits?
       /                         \
    (No)                         (Yes)
     |                             |
Return 402 Error           Begin Transaction
(Insufficient Balance)             |
                                   v
                         Execute Vision Pipeline
                                   |
                       +-----------+-----------+
                       |                       |
                   (Success)                (Failure)
                       |                       |
                       v                       v
               Commit Deduction            Rollback
             Insert Ledger Record      No Credits Deducted
           (CARD_PROCESSING, -3)     Return Error to Client
```

### Supported Transaction Types
* `ADMIN_GRANT`: Manual credit allocations by system administrators or promotional bonuses.
* `TELEGRAM_PURCHASE`: Credits purchased via Telebirr or CBE bank transfer and approved by an admin.
* `CARD_PROCESSING`: Automated debit for generating 1 to 5-card layout templates.
* `REFUND`: Restored credits following an unrecoverable system or template error.

---

## Infrastructure & Deployment

### Production Directory Structure & Volumes
```
/home/mrsolo/Desktop/AutoPress/
|-- AutoPress-backend/
|   +-- autopress.db           # Authoritative SQLite database
|   +-- models/                # Local cache for u2net ONNX models
|-- autopress-telegram-bot/
|   +-- autopress_bot.db       # Bot state and interaction database
+-- scripts/
    +-- reconcile_balances.py  # Nightly balance reconciliation script
```

### System Services Overview
In production environments, the platform components operate as follows:
1. **`autopress-backend`**: Dockerized container managed via Docker Compose or standalone Docker daemon.
2. **`autopress-telegram-bot.service`**: Linux `systemd` service executing with automatic restart on failure.
3. **`autopress-admin-bot.service`**: Linux `systemd` service ensuring 24/7 administrative notifications.
4. **`AutoPress-frontend`**: Static build served via Nginx or edge platforms (Vercel / Cloudflare Pages).

---

## Environment Variables

### Application & Security
| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Port for Flask WSGI server |
| `APP_ENV` | `production` | Deployment environment (`development` / `production`) |
| `SECRET_KEY` | None | Session encryption secret |
| `JWT_SECRET` | None | Secret for encoding and verifying JWT tokens |
| `AUTOPRESS_SERVICE_SECRET` | None | Shared inter-service authentication token |
| `AUTOPRESS_ADMIN_BOT_SECRET`| None | Shared secret for administrative Telegram bot calls |

### Credit System & Costs
| Variable | Default | Purpose |
|---|---|---|
| `CREDIT_COST_PER_DOCUMENT` | `1` | Base credit cost per processed ID document |
| `DEFAULT_SIGNUP_CREDITS` | `2` | Welcome credit allocation granted upon user registration |

### AI Vision & Gemini Keys
| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY_1` .. `_30` | None | Rotation pool of Google Gemini Vision API keys |
| `U2NET_HOME` | `/app/models` | Local directory containing ONNX segmentation weights |
| `REMBG_HOME` | `/app/models` | Rembg model cache destination |

### Telegram Integration
| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | None | Token for customer-facing bot (`@AutoPressFaydaBot`) |
| `ADMIN_BOT_TOKEN` | None | Token for administrative bot (`@AutoPressAdminBot`) |
| `ADMIN_TELEGRAM_IDS` | None | Comma-separated list of Telegram user IDs with admin privileges |

---

## Contributor

* **Bilal Mohamed** — *Lead Architect, Full-Stack & AI Systems Developer*

---

## License

This project is proprietary and confidential. All rights reserved. Unauthorized copying, distribution, or modification of any part of this repository is strictly prohibited.
