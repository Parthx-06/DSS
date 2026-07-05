# 📊 DSS — Sales Intelligence Dashboard

> An AI-powered **Decision Support System** that transforms any CSV dataset into a full business intelligence suite — with market predictions, anomaly detection, automated email reports, and supplier alerts.

---

## 🚀 Live Demo

Deploy your own instance on [Render](https://render.com) using the included `render.yaml` config.

---

## ✨ Features

### 🤖 Agentic 8-Step Pipeline
Upload a CSV and trigger a fully autonomous pipeline that runs end-to-end:

| Step | Action | Description |
|------|--------|-------------|
| 1 | 📊 **CSV Analysis** | Auto-detects column types (numeric, categorical, time), computes stats |
| 2 | 📈 **Chart Generation** | Generates up to 10 Chart.js visualizations automatically |
| 3 | 🔍 **Anomaly Detection** | Flags growth spikes, drops, and high-variance categories |
| 4 | 📰 **Market News** | Fetches live Google News RSS articles per product/category |
| 5 | 🤖 **AI Predictions** | LLaMA 3.3-70B (via Groq) generates market forecasts with confidence scores |
| 6 | 📧 **Manager Report** | Auto-generates and emails a rich HTML intelligence report |
| 7 | 📦 **Supplier Alerts** | Sends targeted stock-increase/decrease advisories per product |
| 8 | 🎯 **DSS Engine** | Runs 7 advanced analytics modules (see below) |

---

### 📊 Auto-Generated Charts (Up to 10)
The system auto-detects your data shape and generates relevant charts:

- **Bar Chart** — Total metric by category
- **Line Chart** — Trend over time (per category)
- **Pie Chart** — Distribution by category
- **Grouped Bar** — Multi-category comparison
- **Area Line** — Secondary metric trend
- **Horizontal Bar** — Average metric per category
- **Stacked Bar** — Time × category breakdown
- **Doughnut** — Share by secondary grouping
- **Radar** — Multi-metric scorecard
- **Growth Rate Trajectory** — Period-over-period % change

---

### 🎯 DSS Analytics Engine (7 Modules)

| Module | Description |
|--------|-------------|
| **Pareto / ABC Analysis** | Classifies categories into A/B/C tiers (80/95/100% cumulative share) |
| **Statistical Forecasting** | Linear regression + moving average with confidence intervals |
| **Decision Matrix** | Multi-criteria weighted scoring across all numeric dimensions |
| **Risk Scoring** | Composite risk score: volatility + concentration + growth instability |
| **HHI Concentration Index** | Herfindahl-Hirschman Index measuring dependency/diversification risk |
| **Sensitivity Analysis** | Elasticity and impact of 10% change per category |
| **Period Comparison** | First-half vs second-half performance with momentum signals |

---

### 🤖 AI-Powered Modules

- **Market Prediction** — Groq LLaMA 3.3-70B analyzes your data + live news to forecast trends, confidence %, and recommended actions per category
- **What-If Scenario Engine** — Type any hypothetical scenario ("What if shipping costs rise 20%?") and get AI-powered impact analysis
- **Strategic Advisor** — Generates a full strategic brief: immediate actions, growth strategies, stock recommendations, gap analysis, and future predictions

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3, Flask |
| **AI / LLM** | [Groq](https://groq.com) — LLaMA 3.3-70B Versatile |
| **Data** | Pandas (generic CSV engine — works with any dataset) |
| **News** | Google News RSS (free, no key required) |
| **Email** | SMTP (Gmail) + `mailto:` fallback |
| **Charts** | Chart.js (rendered in browser) |
| **Deployment** | Gunicorn + Render |

---

## ⚙️ Setup

### 1. Clone the repo

```bash
git clone https://github.com/Parthx-06/DSS.git
cd DSS
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the root directory:

```env
# AI
GROQ_API_KEY=your_groq_api_key_here

# Email (Gmail SMTP)
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
MANAGER_EMAIL=manager@example.com
SUPPLIER_EMAIL=supplier@example.com

# App
SECRET_KEY=your_random_secret_key_here
```

> **Note:** For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password.

### 5. Run locally

```bash
python app.py
```

Visit `http://localhost:5000`

---

## 📁 Project Structure

```
DSS/
├── app.py                  # Main Flask application (1,484 lines)
├── requirements.txt        # Python dependencies
├── Procfile                # Gunicorn start command (for Railway/Heroku)
├── render.yaml             # Render.com one-click deploy config
├── .env                    # Environment variables (not committed)
├── .gitignore
├── templates/
│   ├── index.html          # Landing / upload page
│   └── dashboard.html      # Full dashboard UI
├── static/                 # CSS, JS, assets
└── uploads/                # Uploaded CSVs (ephemeral, not committed)
```

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload a CSV file |
| `POST` | `/api/analyze` | Analyze CSV → stats + charts + anomalies |
| `GET`  | `/api/news` | Fetch live market news for detected categories |
| `POST` | `/api/predict` | Run AI market prediction (Groq LLaMA) |
| `POST` | `/api/dss-analysis` | Run full 7-module DSS engine |
| `POST` | `/api/strategic-advisor` | AI strategic business briefing |
| `POST` | `/api/what-if` | What-if scenario analysis |
| `POST` | `/api/manager-report` | Generate + email HTML intelligence report |
| `POST` | `/api/supplier-alert` | Send supplier stock advisory emails |
| `POST` | `/api/run-pipeline` | Run full 8-step autonomous pipeline |
| `GET`  | `/api/pipeline-status` | Poll real-time pipeline progress |

---

## 🚀 Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New → Web Service**
3. Connect your GitHub repo — Render auto-detects `render.yaml`
4. Add your environment variables in the **Environment** tab
5. Click **Deploy** 🎉

The `render.yaml` handles everything:
- **Build:** `pip install -r requirements.txt`
- **Start:** `gunicorn app:app`

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

> Built with ❤️ using Flask, Groq AI, and Chart.js
