# US Industry & Thematic ETFs Dashboard

A comprehensive, real-time tracking dashboard for 30 US Industry & Thematic ETFs and SPDR Sector Benchmarks.

## Key Features
- **Distance from ATH & 52-Week High:** Visual progress bars, adjusted ATH, and prior swing highs.
- **Relative Strength (RS vs SPY):** Multi-horizon relative performance (1M, 3M, 6M, 12M) with dynamic 1-99 RS Rank.
- **Cycle & Momentum Classification:** 4-quadrant RRG (Relative Rotation Graph) — Leading, Improving, Weakening, Lagging.
- **Reversal Candidate Detector:** Spots downtrend sectors displaying early turn-up momentum signals.
- **Stock Scanner:** Scans leading stock holdings inside the top ETFs.
- **Heatmap & Charts:** Interactive performance heatmap, 60-day sparklines, and 1-year interactive detail charts with SMA 50/200.
- **Watchlist & Sharing:** Add custom tickers (persisted locally) and share filtered views via URL.

## Quick Start (Local Server)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the local server
python3 server.py
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

## Mobile Access

### 1. Same Wi-Fi (Home / Office)
Ensure your phone is connected to the same Wi-Fi network as this machine, then open:
`http://<YOUR_LOCAL_IP>:8000` (e.g. `http://192.168.0.69:8000`)

### 2. Free Cloud Deployment (24/7 Access Anywhere)
You can deploy this repository to **Render** or **Railway** for free:
1. Log in to [render.com](https://render.com) (using your GitHub account).
2. Click **New +** -> **Web Service**.
3. Select this repository (`etf-dashboard`).
4. Build command: `pip install -r requirements.txt`
5. Start command: `python3 server.py`
6. Click **Deploy** — Render will give you a private HTTPS URL (e.g. `https://etf-dashboard-xxx.onrender.com`) that you can open from your phone anywhere!

### 3. Automatic Data Updates
A GitHub Actions workflow (`daily_update.yml`) runs after US market close Monday–Friday to refresh `data.json` and `scanner.json`.
