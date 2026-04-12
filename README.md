# VLSI Testing ATPG

A Flask web application for automatic test pattern generation and design space exploration over combinational netlists. The app compares ATPG engines, runs simulation kernels, and visualizes fault coverage, backtracks, runtime, memory, and final test vectors.

## Features

- Browser-based ATPG console for selecting netlists and algorithms.
- Basic flow execution with netlist parsing, levelization, and event-driven simulation.
- D algorithm and PODEM runs with per-fault reporting.
- Design space exploration routes for comparing D vs PODEM, PODEM vs PODEM_NO_HEUR, D vs D_QUICK, SIMULATE vs EVENT_DRIVEN, and fill-bit policies.
- Sample netlists in the `netlists/` folder.
- Optional static image reuse or generated SVG netlist graphs.

## Requirements

- Python 3.10 or newer
- Flask 3.0.3

## Setup

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Start the app locally with:

```powershell
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

## Project Layout

- `app.py` main Flask app and API responses
- `d.py` baseline D-algorithm engine
- `d2.py` alternate D-algorithm variant
- `podem.py` PODEM engine
- `netlist_graph.py` netlist parsing, levelization, and simulation
- `backend/routes/dse/` API routes for DSE comparisons
- `backend/utils/dse_helpers.py` shared metrics and formatting helpers
- `templates/` HTML views for the console and explainer page
- `static/` CSS and JavaScript for the UI
- `netlists/` sample benchmark netlists
- `images/` optional netlist and generated diagram assets

## API Overview

- `GET /api/netlists` returns the available netlist files.
- `POST /api/run` runs the selected ATPG algorithms.
- `POST /api/dse` runs DSE #1.
- `POST /api/dse-podem-variants` runs DSE #2.
- `POST /api/dse-d-variants` runs DSE #3.
- `POST /api/dse-sim-kernels` runs DSE #4.
- `POST /api/dse-fill-variants` runs DSE #5.

## Deployment

The repository includes a `vercel.json` for Vercel deployment. The configuration packages the Flask app together with the `images/`, `netlists/`, `static/`, `templates/`, and `backend/` folders.

## Notes

- Netlists are parsed from the `netlists/` directory.
- Generated SVG diagrams are reused from `images/` when available.
- The explainer page at `/explainer` summarizes the routes and engine behavior.