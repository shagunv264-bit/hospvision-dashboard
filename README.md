# 🏥 HospVision — Real-Time Hospital Resource Management Dashboard

> A real-time hospital resource management system tracking bed occupancy, ICU capacity, and equipment status across multiple departments and branches. Built with Python, Streamlit, Plotly, and SQLite.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.64-red)](https://streamlit.io)
[![Plotly](https://img.shields.io/badge/Plotly-7.0-purple)](https://plotly.com)
[![SQLite](https://img.shields.io/badge/Database-SQLite-green)](https://sqlite.org)

---

## 📋 Problem Statement

Hospital administrators and clinical staff currently lack a unified, real-time view of critical operational resources across multiple departments and branches, forcing them to rely on manual reporting, phone calls, and disconnected spreadsheets to track bed occupancy, ICU availability, and the status of life-critical equipment such as ventilators, CT scanners, and dialysis machines. This fragmented approach leads to delayed decision-making, inefficient resource allocation, and increased risk to patient outcomes — particularly during peak-demand periods or emergencies. **HospVision** addresses this by providing a centralized, data-driven platform that continuously monitors and visualizes resource utilization across all hospital branches, triggers real-time alerts when occupancy or equipment thresholds are breached, and enables administrators to make faster, informed decisions to optimize patient care and operational efficiency.

---

## ✨ Features

- 📊 **Real-time KPI cards** — Total beds, occupied, available, ICU status, equipment uptime
- 🚨 **Live alert panel** — Auto-triggers critical/warning alerts based on configurable thresholds
- 📈 **24-hour occupancy trend** — Multi-branch line chart with daily wave simulation
- 🌡️ **Department heatmap** — Colour-coded occupancy grid across all departments × branches
- 🔧 **Equipment status** — Stacked bar + donut chart for operational/maintenance/out-of-service units
- 🏥 **5 hospital branches** — Main Campus, North Wing, South Wing, East Campus, Pediatrics
- 🔄 **Auto-refresh** — Configurable live refresh (10s to 2 min)
- 🗄️ **SQLite database** — Persistent storage with full historical occupancy trend logging
- 🎛️ **Sidebar filters** — Filter by branch, department, and custom thresholds

---

## 🖥️ Dashboard Preview

| Section | Description |
|---|---|
| KPI Row | 6 real-time metric cards |
| Alert Panel | Critical & warning banners |
| Occupancy Gauge | Overall bed occupancy dial |
| Branch Bar Chart | Beds grouped by branch |
| 24h Trend | Line chart per branch |
| Heatmap | Department × Branch occupancy grid |
| Equipment Panel | Fleet health charts + OOS table |
| Detail Table | Sortable department-level data |

---

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/shagunv264-bit/hospvision-dashboard.git
cd hospvision-dashboard
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up the database
```bash
python db_setup.py
```

### 4. Run the dashboard
```bash
python -m streamlit run app.py
```

### 5. Open in browser
```
http://localhost:8501
```

> **Windows users:** Double-click `run_dashboard.bat` to launch automatically.

---

## 📁 Project Structure

```
hospvision-dashboard/
├── app.py               # Main Streamlit dashboard
├── db_setup.py          # Database schema creation + seeding
├── db_utils.py          # All SQLite query helpers
├── requirements.txt     # Python dependencies
├── run_dashboard.bat    # Windows one-click launcher
└── README.md            # This file
```

---

## 🗄️ Database Schema

```
branches          → Hospital branches
departments       → Departments with bed counts
bed_occupancy     → Timestamped occupancy snapshots
equipment         → Per-branch unit counts by status
occupancy_trend   → Hourly occupancy % per branch
alerts            → Active/resolved alert log
```

---

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| Python 3.10+ | Core language |
| Streamlit 1.64 | Web dashboard framework |
| Plotly 7 | Interactive charts |
| Pandas | Data manipulation |
| SQLite | Local persistent database |

---

## 📊 Data Update API

You can update live data programmatically using `db_utils`:

```python
import db_utils

# Update bed occupancy
db_utils.update_bed_occupancy("Main Campus", "Emergency", occupied=45, icu_occupied=8)

# Update equipment counts
db_utils.update_equipment("North Wing", "Ventilators", operational=8, maintenance=2, out_of_service=1)

# Insert a custom alert
db_utils.insert_alert("critical", "Oxygen supply low in ICU", branch="North Wing")
```

---

## 👤 Author

**Shagun** — [github.com/shagunv264-bit](https://github.com/shagunv264-bit)

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).
