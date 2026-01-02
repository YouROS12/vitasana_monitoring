# 💊 Vitasana Monitoring

A clean, modular pharmaceutical product monitoring application with a beautiful UI.

## 🏗️ Architecture

```
vitasana_monitoring/
├── app/
│   ├── core/               # Shared infrastructure
│   │   ├── config.py       # YAML configuration loader
│   │   ├── database.py     # SQLite operations
│   │   └── logging.py      # Logging setup
│   │
│   ├── auth/               # Authentication
│   │   └── session.py      # Login & token management
│   │
│   ├── discovery/          # Product discovery (web scraping)
│   │   └── scraper.py      # Concurrent scraper
│   │
│   ├── monitoring/         # Stock monitoring (API)
│   │   └── tracker.py      # API client
│   │
│   ├── api/                # REST API (FastAPI)
│   │   ├── routes/         # API endpoints
│   │   └── schemas.py      # Pydantic models
│   │
│   └── main.py             # FastAPI app entry
│
├── dashboard.py            # Streamlit UI
├── cli.py                  # Command-line interface
├── config.yaml             # Configuration
└── requirements.txt        # Dependencies
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd vitasana_monitoring
pip install -r requirements.txt
```

### 2. Configure

Edit `config.yaml` with your credentials:

```yaml
credentials:
  username: YOUR_USERNAME
  password: YOUR_PASSWORD
  client_id: YOUR_CLIENT_ID
```

### 3. Start the API Server

```bash
python cli.py serve
```

The API will be available at `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

### 4. Start the Dashboard (in another terminal)

```bash
python cli.py dashboard
```

The dashboard will open at `http://localhost:8501`

---

## 💻 CLI Usage

```bash
# Product discovery
python cli.py discover --start 1 --end 100

# Stock monitoring
python cli.py monitor --limit 500
python cli.py monitor --keywords "vitamin,paracetamol" --workers 10

# Start API server
python cli.py serve --port 8000

# Start dashboard
python cli.py dashboard --port 8501
```

---

## 🎨 Dashboard Features

| Feature | Description |
|---------|-------------|
| 🎮 Task Runner | Run discovery/monitoring with configurable parameters |
| 📦 Products | Browse all products with search and filters |
| 📊 Analytics | View product history and trends |

### Task Runner UI

- **Discovery**: Configure page range, worker count, run and monitor progress
- **Monitoring**: Set limits, keywords, workers, track real-time progress

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/products` | List products |
| GET | `/api/products/latest` | Products with latest status |
| GET | `/api/products/{sku}` | Single product |
| GET | `/api/products/{sku}/history` | Product history |
| POST | `/api/discovery/run` | Start discovery |
| GET | `/api/discovery/status` | Discovery progress |
| POST | `/api/monitoring/run` | Start monitoring |
| GET | `/api/monitoring/status` | Monitoring progress |

---

## 📁 Data

- **Database**: `data/vitasana.db` (SQLite)
- **Logs**: `vitasana.log`

---

## 🔄 Migration from PharmaStock

To import existing data:

```bash
# Copy the old database
cp ../data/pharmastock.db data/vitasana.db
```

---

## 📝 License

Private/Internal use.
