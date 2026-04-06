from flask import Flask, render_template_string, jsonify, request, send_from_directory
from pathlib import Path
import hashlib
import os
import sys
import random
import tracemalloc
from time import perf_counter

# Import ATPG engines
sys.path.insert(0, os.path.dirname(__file__))
from d import DAlgorithmEngine
from d2 import DAlgorithmEngine as DExhaustiveAlgorithmEngine
from podem import PODEMEngine
from netlist_graph import (
    assign_default_inputs,
    generate_faults,
    levelize,
    parse_netlist,
    simulate,
    simulate_event_driven,
)

app = Flask(__name__)
NETLISTS_FOLDER = Path(__file__).parent / 'netlists'
IMAGES_FOLDER = Path(__file__).parent / 'images'

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATPG Web Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --ink: #10243f;
            --ink-soft: #365274;
            --paper: #f8f6ef;
            --panel: #fffdf9;
            --line: #d7cfbf;
            --accent: #ff7a18;
            --accent-strong: #ea580c;
            --d-algo: #0f766e;
            --podem: #b91c1c;
            --glow: rgba(255, 122, 24, 0.2);
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            font-family: 'Space Grotesk', sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 90% 0%, #ffdcb8 0%, transparent 40%),
                radial-gradient(circle at 0% 100%, #d7f0ff 0%, transparent 35%),
                var(--paper);
            padding: 24px;
        }

        .shell {
            max-width: 1240px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 20px;
            min-height: calc(100vh - 48px);
            animation: riseIn 500ms ease-out;
        }

        .shell > .panel,
        .shell > .main {
            max-height: calc(100vh - 48px);
            overflow: visible;
        }

        .workspace-outputs {
            max-width: 1240px;
            margin: 20px auto 0;
            display: grid;
            gap: 20px;
        }

        .outputs-panel {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 10px 30px rgba(16, 36, 63, 0.08);
        }

        .outputs-panel h3 {
            margin: 0 0 10px;
            font-size: 16px;
            color: var(--ink-soft);
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 10px 35px rgba(16, 36, 63, 0.08);
            overflow: hidden;
        }

        .panel-head {
            padding: 16px 18px;
            border-bottom: 1px solid var(--line);
            background: linear-gradient(135deg, #fff4e8, #fffdf9);
        }

        .panel-head h2 {
            margin: 0;
            font-size: 18px;
        }

        .panel-head p {
            margin: 6px 0 0;
            font-size: 13px;
            color: var(--ink-soft);
        }

        .panel-body {
            padding: 16px 18px 18px;
            display: grid;
            gap: 12px;
        }

        label {
            display: grid;
            gap: 6px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--ink-soft);
        }

        select,
        input[type="text"],
        input[type="file"] {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #ffffff;
            padding: 10px 12px;
            color: var(--ink);
            font-size: 14px;
            font-family: 'Space Grotesk', sans-serif;
        }

        .btn-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        button {
            border: 0;
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: transform 120ms ease, box-shadow 120ms ease;
            flex: 1;
            min-width: 100px;
        }

        .btn-primary {
            background: var(--accent);
            color: #fff;
            box-shadow: 0 8px 20px var(--glow);
        }

        .btn-primary:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .btn-soft {
            background: #ffe9d2;
            color: #7c2d12;
        }

        button:hover:not(:disabled) {
            transform: translateY(-1px);
        }

        .main {
            display: grid;
            gap: 20px;
            align-content: start;
        }

        .hero {
            padding: 24px;
            border-radius: 18px;
            background: linear-gradient(135deg, #112a46, #1e4d75);
            color: #ebf7ff;
            box-shadow: 0 16px 40px rgba(16, 36, 63, 0.25);
        }

        .hero h1 {
            margin: 0;
            font-size: clamp(22px, 3vw, 34px);
            line-height: 1.1;
        }

        .hero p {
            margin: 10px 0 0;
            max-width: 860px;
            font-size: 14px;
            color: #c9e8ff;
        }

        .results {
            display: grid;
            gap: 16px;
        }

        .result-card {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: #ffffff;
            overflow: hidden;
            animation: cardIn 280ms ease-out;
        }

        .result-head {
            border-bottom: 1px solid var(--line);
            padding: 12px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
            background: #fff8ef;
        }

        .result-head strong {
            font-size: 15px;
        }

        .badge {
            border-radius: 999px;
            padding: 4px 10px;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }

        .badge-d { background: var(--d-algo); }
        .badge-podem { background: var(--podem); }
        .badge-run { background: #4b5563; }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 10px;
            padding: 14px;
        }

        .stat {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 10px;
            background: #fffdf8;
        }

        .stat .k {
            font-size: 11px;
            color: var(--ink-soft);
            text-transform: uppercase;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .stat .v {
            font-size: 16px;
            font-weight: 700;
        }

        details {
            padding: 0 14px 14px;
        }

        summary {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 9px 10px;
            cursor: pointer;
            font-weight: 700;
            background: #f4f9ff;
        }

        .faults {
            margin-top: 8px;
            max-height: 280px;
            overflow: auto;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #fff;
        }

        .fault-item {
            padding: 8px 10px;
            border-bottom: 1px solid #ece8df;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            line-height: 1.4;
        }

        .fault-item:last-child {
            border-bottom: 0;
        }

        .status {
            min-height: 20px;
            font-size: 13px;
            color: #0f5132;
            padding: 6px;
            border-radius: 6px;
            background: #f1f5fe;
        }

        .status.running {
            color: #1e40af;
            animation: pulse 1.5s ease-in-out infinite;
        }

        .status.error {
            color: #7c2d12;
            background: #fed7aa;
        }

        .status.success {
            color: #0f5132;
            background: #dcfce7;
        }

        .empty {
            text-align: center;
            color: var(--ink-soft);
            border: 1px dashed var(--line);
            border-radius: 12px;
            padding: 20px;
            background: #fff;
        }

        .dse-panel {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: #ffffff;
            padding: 14px;
            max-height: calc(100vh - 210px);
            overflow-y: auto;
        }

        .dse-controls {
            display: grid;
            gap: 8px;
            margin-bottom: 10px;
        }

        .dse-metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 8px;
            padding: 6px 0;
        }

        .dse-block {
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px;
            margin-top: 10px;
            background: #fffaf2;
        }

        .dse-metrics {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            padding: 8px 0;
        }

        .dse-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 8px;
        }

        .dse-table th,
        .dse-table td {
            border: 1px solid var(--line);
            padding: 8px;
            text-align: left;
        }

        .dse-table th {
            background: #f4f9ff;
        }

        .dse-chart {
            margin-top: 10px;
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 10px;
            background: #fffdf8;
        }

        .dse-mini-charts {
            display: flex;
            gap: 8px;
            margin-top: 10px;
            overflow-x: auto;
            padding-bottom: 4px;
        }

        .dse-mini-charts .dse-chart {
            min-width: 210px;
            margin-top: 0;
            flex: 0 0 210px;
            padding: 8px;
        }

        .dse-mini-charts .dse-chart canvas {
            width: 100%;
        }

        .vector-summary {
            margin: 0 14px 14px;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #fff;
            padding: 10px;
        }

        .vector-summary h4 {
            margin: 0 0 8px 0;
            font-size: 13px;
            color: var(--ink-soft);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .vector-list {
            max-height: 160px;
            overflow: auto;
            border: 1px solid #ece8df;
            border-radius: 8px;
            background: #fffdf8;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
        }

        .vector-item {
            padding: 6px 8px;
            border-bottom: 1px solid #ece8df;
        }

        .vector-item:last-child {
            border-bottom: 0;
        }

        .basic-image-panel {
            margin: 0 14px 14px;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #fff;
            padding: 10px;
        }

        .basic-image-title {
            margin: 0 0 8px 0;
            font-size: 13px;
            color: var(--ink-soft);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .basic-image {
            width: 100%;
            max-height: 340px;
            object-fit: contain;
            border: 1px solid #ece8df;
            border-radius: 8px;
            background: #fffdf8;
        }

        @keyframes riseIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes cardIn {
            from {
                opacity: 0;
                transform: translateY(6px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }

        @media (max-width: 980px) {
            .shell {
                grid-template-columns: 1fr;
                min-height: auto;
            }

            .dse-panel {
                max-height: none;
                overflow: visible;
            }
        }
    </style>
</head>
<body>
    <div class="shell">
        <aside class="panel">
            <div class="panel-head">
                <h2>Run Configuration</h2>
                <p>Select netlists & algorithms, then execute.</p>
            </div>
            <div class="panel-body">
                <label style="text-transform: uppercase; font-size: 12px; font-weight: 700; color: #365274; margin-bottom: 8px; display: block;">
                    Select Netlists
                </label>
                <div id="netlistsContainer" style="display: grid; gap: 6px; max-height: 160px; overflow-y: auto; border: 1px solid #d7cfbf; border-radius: 10px; padding: 10px; background: #fffdf9;">
                    <p style="margin: 0; color: #999; font-size: 13px;">Loading netlists...</p>
                </div>

                <label style="text-transform: uppercase; font-size: 12px; font-weight: 700; color: #365274; margin-top: 14px; margin-bottom: 8px; display: block;">
                    Select Algorithms
                </label>
                <div style="display: grid; gap: 6px;">
                    <label style="display: flex; align-items: center; gap: 8px; font-weight: 400; text-transform: none; margin: 0; color: #10243f; cursor: pointer;">
                        <input type="checkbox" id="algoBasic" value="BASIC" />
                        <span>Basic Flow</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; font-weight: 400; text-transform: none; margin: 0; color: #10243f; cursor: pointer;">
                        <input type="checkbox" id="algoD" checked value="D" />
                        <span>D Algorithm</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; font-weight: 400; text-transform: none; margin: 0; color: #10243f; cursor: pointer;">
                        <input type="checkbox" id="algoPODEM" checked value="PODEM" />
                        <span>PODEM</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; font-weight: 400; text-transform: none; margin: 0; color: #10243f; cursor: pointer;">
                        <input type="checkbox" id="algoDExhaustive" value="D_EXHAUSTIVE" />
                        <span>D_EXHAUSTIVE</span>
                    </label>
                </div>

                <div class="btn-row" style="margin-top: 14px;">
                    <button class="btn-primary" id="runBtn" onclick="runATPC()">Run ATPG</button>
                </div>

                <div id="status" class="status"></div>
            </div>
        </aside>

        <main class="main">
            <section class="hero">
                <h1>ATPG Web Console</h1>
                <p>Full-stack web interface for automatic test pattern generation. Select a netlist, choose your algorithm and execute directly from the browser with real-time results.</p>
            </section>

            <section class="dse-panel">
                <h2 style="margin: 0 0 6px 0; font-size: 18px;">Design Space Exploration (DSE)</h2>
                <p style="margin: 0 0 10px 0; color: #365274; font-size: 13px;">Use DSE to compare ATPG tradeoffs across netlists across three dedicated comparisons.</p>

                <div class="dse-controls">
                    <div style="display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap;">
                        <div style="flex: 1; min-width: 300px;">
                            <strong style="font-size: 12px; color: #365274; letter-spacing: 0.04em; text-transform: uppercase;">Metrics To Compare</strong>
                            <div class="dse-metrics-grid">
                                <label style="display:flex; align-items:center; gap:6px; text-transform:none; font-weight:500; color:#10243f;"><input type="checkbox" id="metricCoverage" checked />Coverage (%)</label>
                                <label style="display:flex; align-items:center; gap:6px; text-transform:none; font-weight:500; color:#10243f;"><input type="checkbox" id="metricTime" checked />Time (ms)</label>
                                <label style="display:flex; align-items:center; gap:6px; text-transform:none; font-weight:500; color:#10243f;"><input type="checkbox" id="metricBacktracks" checked />Backtracks</label>
                                <label style="display:flex; align-items:center; gap:6px; text-transform:none; font-weight:500; color:#10243f;"><input type="checkbox" id="metricMemory" checked />Peak Memory (KB)</label>
                                <label style="display:flex; align-items:center; gap:6px; text-transform:none; font-weight:500; color:#10243f;"><input type="checkbox" id="metricTestVectors" checked />Final Test Vectors</label>
                            </div>
                        </div>
                        <div style="flex: 1; min-width: 250px; border-left: 1px solid #d7cfbf; padding-left: 20px; display: flex; align-items: center;">
                            <div style="color: #365274; font-size: 13px; line-height: 1.5;">
                                DSE runs in single-pass mode only. Metrics are reported directly from one ATPG execution per netlist.
                            </div>
                        </div>
                    </div>
                </div>

                <div class="dse-block">
                    <h3 style="margin: 0 0 6px 0; font-size: 16px;">DSE #1: D vs PODEM</h3>
                    <p style="margin: 0 0 10px 0; color: #365274; font-size: 13px;">Compares baseline D engine directly against heuristic-enabled PODEM.</p>
                    <div class="btn-row" style="margin-top: 4px; margin-bottom: 8px;">
                        <button class="btn-soft" id="runDseBtn" onclick="runDSE()">Run DSE #1</button>
                    </div>
                    <p style="margin: 0; color: #365274; font-size: 12px;">Output appears below the first screen in the unified results area.</p>
                </div>

                <div class="dse-block">
                    <h3 style="margin: 0 0 6px 0; font-size: 16px;">DSE #2: PODEM vs PODEM_NO_HEUR</h3>
                    <p style="margin: 0 0 10px 0; color: #365274; font-size: 13px;">Compares heuristic-enabled PODEM against the non-heuristic PODEM baseline.</p>
                    <div class="btn-row" style="margin-top: 4px; margin-bottom: 8px;">
                        <button class="btn-soft" id="runDsePodemVariantsBtn" onclick="runDsePodemVariants()">Run DSE #2</button>
                    </div>
                    <p style="margin: 0; color: #365274; font-size: 12px;">Output appears below the first screen in the unified results area.</p>
                </div>

                <div class="dse-block">
                    <h3 style="margin: 0 0 6px 0; font-size: 16px;">DSE #3: D vs D_EXHAUSTIVE</h3>
                    <p style="margin: 0 0 10px 0; color: #365274; font-size: 13px;">Compares baseline D engine from d.py against D_EXHAUSTIVE from d2.py.</p>
                    <div class="btn-row" style="margin-top: 4px; margin-bottom: 8px;">
                        <button class="btn-soft" id="runDseDVariantsBtn" onclick="runDseDVariants()">Run DSE #3</button>
                    </div>
                    <p style="margin: 0; color: #365274; font-size: 12px;">Output appears below the first screen in the unified results area.</p>
                </div>

                <div class="dse-block">
                    <h3 style="margin: 0 0 6px 0; font-size: 16px;">DSE #4: SIMULATE vs EVENT_DRIVEN</h3>
                    <p style="margin: 0 0 10px 0; color: #365274; font-size: 13px;">Compares levelized simulate() and event-driven simulate_event_driven() kernels in Basic flow.</p>
                    <div class="btn-row" style="margin-top: 4px; margin-bottom: 8px;">
                        <button class="btn-soft" id="runDseSimKernelsBtn" onclick="runDseSimKernels()">Run DSE #4</button>
                    </div>
                    <p style="margin: 0; color: #365274; font-size: 12px;">Output appears below the first screen in the unified results area.</p>
                </div>

                <div class="dse-block">
                    <h3 style="margin: 0 0 6px 0; font-size: 16px;">DSE #5: Fill-bit policies</h3>
                    <p style="margin: 0 0 10px 0; color: #365274; font-size: 13px;">Compares 0-fill, 1-fill, and deterministic random-fill on partially specified test vectors.</p>
                    <div class="btn-row" style="margin-top: 4px; margin-bottom: 8px;">
                        <button class="btn-soft" id="runDseFillVariantsBtn" onclick="runDseFillVariants()">Run DSE #5</button>
                    </div>
                    <p style="margin: 0; color: #365274; font-size: 12px;">Output appears below the first screen in the unified results area.</p>
                </div>
            </section>
        </main>
    </div>

    <section class="workspace-outputs">
        <div class="outputs-panel">
            <h3>ATPG Run Output</h3>
            <section id="results" class="results">
                <div class="empty">Select a netlist and click Run ATPG.</div>
            </section>
        </div>

        <div class="outputs-panel">
            <h3>DSE #1 Output (D vs PODEM)</h3>
            <section id="dseResultsPrimary" class="results">
                <div class="empty">Run DSE #1 to compare D and PODEM variants.</div>
            </section>
        </div>

        <div class="outputs-panel">
            <h3>DSE #2 Output (PODEM vs PODEM_NO_HEUR)</h3>
            <section id="dseResultsPodemVariants" class="results">
                <div class="empty">Run DSE #2 to compare PODEM and PODEM_NO_HEUR.</div>
            </section>
        </div>

        <div class="outputs-panel">
            <h3>DSE #3 Output (D vs D_EXHAUSTIVE)</h3>
            <section id="dseResultsDVariants" class="results">
                <div class="empty">Run DSE #3 to compare D and D_EXHAUSTIVE.</div>
            </section>
        </div>

        <div class="outputs-panel">
            <h3>DSE #4 Output (SIMULATE vs EVENT_DRIVEN)</h3>
            <section id="dseResultsSimKernels" class="results">
                <div class="empty">Run DSE #4 to compare simulate() and simulate_event_driven().</div>
            </section>
        </div>

        <div class="outputs-panel">
            <h3>DSE #5 Output (Fill-bit policies)</h3>
            <section id="dseResultsFillVariants" class="results">
                <div class="empty">Run DSE #5 to compare 0-fill, 1-fill, and random-fill.</div>
            </section>
        </div>
    </section>

    <script>
        const netlistsContainer = document.getElementById('netlistsContainer');
        const algoBasic = document.getElementById('algoBasic');
        const algoD = document.getElementById('algoD');
        const algoPODEM = document.getElementById('algoPODEM');
        const algoDExhaustive = document.getElementById('algoDExhaustive');
        const runBtn = document.getElementById('runBtn');
        const runDseBtn = document.getElementById('runDseBtn');
        const runDsePodemVariantsBtn = document.getElementById('runDsePodemVariantsBtn');
        const runDseDVariantsBtn = document.getElementById('runDseDVariantsBtn');
        const runDseSimKernelsBtn = document.getElementById('runDseSimKernelsBtn');
        const runDseFillVariantsBtn = document.getElementById('runDseFillVariantsBtn');
        const metricCoverage = document.getElementById('metricCoverage');
        const metricTime = document.getElementById('metricTime');
        const metricBacktracks = document.getElementById('metricBacktracks');
        const metricMemory = document.getElementById('metricMemory');
        const metricTestVectors = document.getElementById('metricTestVectors');
        const status = document.getElementById('status');
        const results = document.getElementById('results');
        const dseResultsPrimary = document.getElementById('dseResultsPrimary');
        const dseResultsPodemVariants = document.getElementById('dseResultsPodemVariants');
        const dseResultsDVariants = document.getElementById('dseResultsDVariants');
        const dseResultsSimKernels = document.getElementById('dseResultsSimKernels');
        const dseResultsFillVariants = document.getElementById('dseResultsFillVariants');

        function getSelectedNetlists() {
            return Array.from(document.querySelectorAll('.netlist-cb:checked')).map(cb => cb.value);
        }

        function getSelectedMetrics() {
            const selectedMetrics = [];
            if (metricCoverage.checked) selectedMetrics.push('coverage');
            if (metricTime.checked) selectedMetrics.push('time');
            if (metricBacktracks.checked) selectedMetrics.push('backtracks');
            if (metricMemory.checked) selectedMetrics.push('memory');
            if (metricTestVectors.checked) selectedMetrics.push('test_vectors');
            return selectedMetrics;
        }

        async function loadNetlists() {
            try {
                const resp = await fetch('/api/netlists');
                const data = await resp.json();
                const netlists = data.netlists || [];

                if (netlists.length === 0) {
                    netlistsContainer.innerHTML = '<p style="margin: 0; color: #999; font-size: 13px;">No netlists found.</p>';
                    return;
                }

                netlistsContainer.innerHTML = netlists.map(nl => `
                    <label style="display: flex; align-items: center; gap: 8px; font-weight: 400; text-transform: none; margin: 0; color: #10243f; cursor: pointer;">
                        <input type="checkbox" class="netlist-cb" value="${nl}" checked />
                        <span style="font-size: 13px;">${nl}</span>
                    </label>
                `).join('');

                status.textContent = `Loaded ${netlists.length} netlists.`;
                status.classList.remove('running', 'error');
            } catch (err) {
                status.textContent = 'Failed to load netlists: ' + err.message;
                status.classList.add('error');
            }
        }

        async function runATPC() {
            const selectedNetlists = getSelectedNetlists();
            const selectedAlgos = [];
            if (algoBasic.checked) selectedAlgos.push('BASIC');
            if (algoD.checked) selectedAlgos.push('D');
            if (algoPODEM.checked) selectedAlgos.push('PODEM');
            if (algoDExhaustive.checked) selectedAlgos.push('D_EXHAUSTIVE');

            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist.';
                status.classList.add('error');
                return;
            }

            if (selectedAlgos.length === 0) {
                status.textContent = 'Please select at least one algorithm.';
                status.classList.add('error');
                return;
            }

            runBtn.disabled = true;
            status.textContent = `Running ${selectedAlgos.join('+')} on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            results.innerHTML = '';

            try {
                const resp = await fetch('/api/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ netlists: selectedNetlists, algorithms: selectedAlgos })
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();

                if (data.error) {
                    status.textContent = 'Error: ' + data.error;
                    status.classList.add('error');
                    results.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `Rendered ${(data.results || []).length} result block(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderResults(data.results || []);
            } catch (err) {
                status.textContent = 'Run failed: ' + err.message;
                status.classList.add('error');
                results.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runBtn.disabled = false;
            }
        }

        async function runDSE() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE.';
                status.classList.add('error');
                return;
            }

            const selectedMetrics = getSelectedMetrics();
            if (selectedMetrics.length === 0) {
                status.textContent = 'Select at least one metric for DSE.';
                status.classList.add('error');
                return;
            }

            runDseBtn.disabled = true;
            status.textContent = `Running DSE #1 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            dseResultsPrimary.innerHTML = '';

            try {
                const endpoint = '/api/dse';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: selectedMetrics,
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE error: ' + data.error;
                    status.classList.add('error');
                    dseResultsPrimary.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #1 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], selectedMetrics, dseResultsPrimary, 'DSE #1', 'd_variants', false);
            } catch (err) {
                status.textContent = 'DSE failed: ' + err.message;
                status.classList.add('error');
                dseResultsPrimary.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseBtn.disabled = false;
            }
        }

        async function runDsePodemVariants() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #2.';
                status.classList.add('error');
                return;
            }

            const selectedMetrics = getSelectedMetrics();
            if (selectedMetrics.length === 0) {
                status.textContent = 'Select at least one metric for DSE #2.';
                status.classList.add('error');
                return;
            }

            runDsePodemVariantsBtn.disabled = true;
            status.textContent = `Running DSE #2 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            dseResultsPodemVariants.innerHTML = '';

            try {
                const endpoint = '/api/dse-podem-variants';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: selectedMetrics,
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #2 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsPodemVariants.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #2 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], selectedMetrics, dseResultsPodemVariants, 'DSE #2', 'podem_variants', false);
            } catch (err) {
                status.textContent = 'DSE #2 failed: ' + err.message;
                status.classList.add('error');
                dseResultsPodemVariants.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDsePodemVariantsBtn.disabled = false;
            }
        }

        async function runDseDVariants() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #3.';
                status.classList.add('error');
                return;
            }

            const selectedMetrics = getSelectedMetrics();
            if (selectedMetrics.length === 0) {
                status.textContent = 'Select at least one metric for DSE #3.';
                status.classList.add('error');
                return;
            }

            runDseDVariantsBtn.disabled = true;
            status.textContent = `Running DSE #3 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            dseResultsDVariants.innerHTML = '';

            try {
                const endpoint = '/api/dse-d-variants';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: selectedMetrics,
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #3 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsDVariants.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #3 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], selectedMetrics, dseResultsDVariants, 'DSE #3', 'd_variants', false);
            } catch (err) {
                status.textContent = 'DSE #3 failed: ' + err.message;
                status.classList.add('error');
                dseResultsDVariants.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseDVariantsBtn.disabled = false;
            }
        }

        async function runDseSimKernels() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #4.';
                status.classList.add('error');
                return;
            }

            const selectedMetrics = getSelectedMetrics();
            const dse4Metrics = selectedMetrics.filter(m => m === 'time' || m === 'memory');
            if (dse4Metrics.length === 0) {
                status.textContent = 'DSE #4 supports Time and Peak Memory metrics only. Select at least one.';
                status.classList.add('error');
                return;
            }

            runDseSimKernelsBtn.disabled = true;
            status.textContent = `Running DSE #4 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            dseResultsSimKernels.innerHTML = '';

            try {
                const endpoint = '/api/dse-sim-kernels';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: dse4Metrics,
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #4 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsSimKernels.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #4 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], dse4Metrics, dseResultsSimKernels, 'DSE #4', 'sim_kernels', false);
            } catch (err) {
                status.textContent = 'DSE #4 failed: ' + err.message;
                status.classList.add('error');
                dseResultsSimKernels.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseSimKernelsBtn.disabled = false;
            }
        }

        async function runDseFillVariants() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #5.';
                status.classList.add('error');
                return;
            }

            const fillMetrics = ['test_vectors', 'toggle_count', 'peak_switching', 'runtime_overhead'];

            runDseFillVariantsBtn.disabled = true;
            status.textContent = `Running DSE #5 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            dseResultsFillVariants.innerHTML = '';

            try {
                const resp = await fetch('/api/dse-fill-variants', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        netlists: selectedNetlists,
                        metrics: fillMetrics,
                    })
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #5 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsFillVariants.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #5 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], fillMetrics, dseResultsFillVariants, 'DSE #5', 'fill_variants', false);
            } catch (err) {
                status.textContent = 'DSE #5 failed: ' + err.message;
                status.classList.add('error');
                dseResultsFillVariants.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseFillVariantsBtn.disabled = false;
            }
        }

        function formatVectorLine(vec, piOrder) {
            const order = (piOrder && piOrder.length) ? piOrder : Object.keys(vec || {}).sort();
            if (!order.length) return 'No vector values';
            return order.map(pi => `${pi}=${(vec || {})[pi] ?? 'X'}`).join(', ');
        }

        function renderVectorSummary(summary, title) {
            const s = summary || { vector_count: 0, pi_order: [], unique_vector_list: [] };
            const vectors = s.unique_vector_list || [];
            const lines = vectors.length
                ? vectors.map(v => `<div class="vector-item">${formatVectorLine(v, s.pi_order || [])}</div>`).join('')
                : '<div class="vector-item">No detected vectors.</div>';

            return `
                <div class="vector-summary">
                    <h4>${title}</h4>
                    <div style="margin-bottom: 8px; font-size: 13px; color: #365274;">Count: <strong>${s.vector_count || 0}</strong></div>
                    <div class="vector-list">${lines}</div>
                </div>
            `;
        }

        function renderDetectedFaultSummary(items, title) {
            const list = items || [];
            const inner = list.length
                ? list.map(item => `<div class="fault-item">${item}</div>`).join('')
                : '<div class="fault-item">No detected faults.</div>';

            return `
                <details style="padding: 0 14px 14px;">
                    <summary>${title} (${list.length})</summary>
                    <div class="faults">${inner}</div>
                </details>
            `;
        }

        function renderResults(resultList) {
            if (!resultList || resultList.length === 0) {
                results.innerHTML = '<div class="empty">No results to display.</div>';
                return;
            }

            const chunks = resultList.map(res => {
                const badgeClass = res.algorithm === 'D'
                    ? 'badge-d'
                    : (res.algorithm === 'PODEM' ? 'badge-podem' : 'badge-run');
                const statHtml = Object.entries(res.stats || {})
                    .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`)
                    .join('');
                const faults = res.faults || [];
                const faultsHtml = faults.length
                    ? faults.map(f => `<div class="fault-item">${f}</div>`).join('')
                    : '<div class="fault-item">No per-fault lines.</div>';
                const showAdvancedSections = !res.hide_vector_sections;
                const advancedSectionsHtml = showAdvancedSections
                    ? `${renderVectorSummary(res.final_vector_summary, 'Final Test Vector Set')}${renderDetectedFaultSummary(res.detected_faults || [], 'Detected Per-Fault List')}`
                    : '';
                const detailTitle = res.algorithm === 'BASIC' ? 'Simulation details' : 'Per-fault details';
                const basicImageHtml = (res.algorithm === 'BASIC' && res.basic_image_url)
                    ? `
                        <div class="basic-image-panel">
                            <h4 class="basic-image-title">Netlist Image</h4>
                            <img class="basic-image" src="${res.basic_image_url}" alt="${res.filename} diagram" loading="lazy" />
                        </div>
                    `
                    : '';

                return `
                    <article class="result-card">
                        <div class="result-head">
                            <strong>${res.filename}</strong>
                            <span class="badge ${badgeClass}">${res.algorithm}</span>
                        </div>
                        <div class="stats">${statHtml}</div>
                        ${basicImageHtml}
                        ${advancedSectionsHtml}
                        <details>
                            <summary>${detailTitle} (${faults.length})</summary>
                            <div class="faults">${faultsHtml}</div>
                        </details>
                    </article>
                `;
            });

            results.innerHTML = chunks.join('');
        }

        function renderDseResults(comparisons, selectedMetrics, targetElement, dseLabel, overlapMode, isIterative) {
            if (!comparisons || comparisons.length === 0) {
                targetElement.innerHTML = '<div class="empty">No DSE comparison data.</div>';
                return;
            }

            const metricLabels = {
                coverage: 'Coverage (%)',
                time: 'Time (ms)',
                backtracks: 'Total Backtracks',
                memory: 'Peak Memory (KB)',
                test_vectors: 'Final Pattern Count',
                toggle_count: 'Toggle Count',
                peak_switching: 'Peak Switching / Pattern',
                runtime_overhead: 'Fill Overhead (ms)',
            };

            const cards = comparisons.map((cmp, idx) => {
                const algos = cmp.algorithms || [];

                // Render results differently for iterative vs single runs
                if (isIterative) {
                    // For iterative results, display statistics table
                    const headers = algos.map(a => `<th>${a.label}</th>`).join('');
                    const rows = selectedMetrics.map(metric => {
                        const statCells = algos.map(a => {
                            const stats = a.metrics_stats && a.metrics_stats[metric];
                            if (!stats) return '<td>N/A</td>';
                            const avg = stats.avg || 0;
                            const decimals = (metric === 'coverage') ? 2 : (metric === 'test_vectors' || metric === 'backtracks') ? 0 : 1;
                            return `<td style="font-size: 13px; font-weight: 600;">${avg.toFixed(decimals)}</td>`;
                        }).join('');
                        return `<tr><td>${metricLabels[metric] || metric}</td>${statCells}</tr>`;
                    }).join('');

                    const overlap = cmp.fault_overlap || {};
                    let overlapText = `Both detected (avg): ${overlap.both_detected_avg || 0} (min: ${overlap.both_detected_min || 0}, max: ${overlap.both_detected_max || 0})`;
                    if (overlapMode === 'd_variants') {
                        overlapText += `, D-only (avg): ${overlap.d_only_avg || 0}, D_EXHAUSTIVE-only (avg): ${overlap.d_exhaustive_only_avg || 0}`;
                    } else if (overlapMode === 'podem_variants') {
                        overlapText += `, PODEM-only (avg): ${overlap.podem_only_avg || 0}, PODEM_NO_HEUR-only (avg): ${overlap.podem_no_heur_only_avg || 0}`;
                    } else if (overlapMode === 'sim_kernels') {
                        const matches = overlap.po_matches_avg || 0;
                        const total = overlap.po_total || 0;
                        const mismatches = overlap.po_mismatches_avg || 0;
                        overlapText = `PO matches (avg): ${matches.toFixed(1)}/${total}, mismatches (avg): ${mismatches.toFixed(1)}`;
                    } else if (overlapMode === 'fill_variants') {
                        overlapText = `Concrete pattern overlap: 0-fill ∩ 1-fill = ${overlap.zero_one_common || 0}, 0-fill ∩ random = ${overlap.zero_random_common || 0}, 1-fill ∩ random = ${overlap.one_random_common || 0}`;
                    } else {
                        overlapText += `, D-only (avg): ${overlap.d_only_avg || 0}, PODEM-only (avg): ${overlap.podem_only_avg || 0}`;
                    }

                    const chartCanvases = selectedMetrics.map(metric => {
                        const id = `${targetElement.id}_chart_${idx}_${metric}`;
                        return `<div class="dse-chart"><canvas id="${id}" height="120"></canvas></div>`;
                    }).join('');

                    return `
                        <article class="result-card">
                            <div class="result-head">
                                <strong>${cmp.netlist}</strong>
                                <span class="badge badge-run">${dseLabel} (Iterative)</span>
                            </div>
                            <div style="padding: 12px; color: #365274; font-size: 13px;">${overlapText}</div>
                            <div style="padding: 0 12px 12px 12px; overflow-x:auto;">
                                <table class="dse-table">
                                    <thead><tr><th>Metric</th>${headers}</tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>
                            </div>
                            <div class="dse-mini-charts" style="padding: 0 12px 12px 12px;">${chartCanvases}</div>
                        </article>
                    `;
                } else {
                    // Original single-run rendering
                    const headers = algos.map(a => `<th>${a.label}</th>`).join('');
                    const rows = selectedMetrics.map(metric => {
                        const vals = algos.map(a => {
                            const v = a.metrics[metric];
                            if (v === null || v === undefined) return 'N/A';
                            if (typeof v !== 'number') return String(v);
                            if (metric === 'coverage') return v.toFixed(2);
                            if (metric === 'test_vectors' || metric === 'backtracks') return String(Math.round(v));
                            return v.toFixed(3);
                        }).map(v => `<td>${v}</td>`).join('');
                        return `<tr><td>${metricLabels[metric] || metric}</td>${vals}</tr>`;
                    }).join('');

                    const overlap = cmp.fault_overlap || {};
                    let overlapText = `Both detected: ${overlap.both_detected || 0}`;
                    if (overlapMode === 'd_variants') {
                        overlapText = `${overlapText}, D-only: ${overlap.d_only || 0}, D_EXHAUSTIVE-only: ${overlap.d_exhaustive_only || 0}`;
                    } else if (overlapMode === 'podem_variants') {
                        overlapText = `${overlapText}, PODEM-only: ${overlap.podem_only || 0}, PODEM_NO_HEUR-only: ${overlap.podem_no_heur_only || 0}`;
                    } else if (overlapMode === 'sim_kernels') {
                        const matches = overlap.po_matches || 0;
                        const total = overlap.po_total || 0;
                        const mismatches = overlap.po_mismatches || 0;
                        overlapText = `PO matches: ${matches}/${total}, mismatches: ${mismatches}`;
                    } else if (overlapMode === 'fill_variants') {
                        overlapText = `Concrete pattern overlap: 0-fill ∩ 1-fill = ${overlap.zero_one_common || 0}, 0-fill ∩ random = ${overlap.zero_random_common || 0}, 1-fill ∩ random = ${overlap.one_random_common || 0}`;
                    } else {
                        overlapText = `${overlapText}, D-only: ${overlap.d_only || 0}, PODEM-only: ${overlap.podem_only || 0}`;
                    }

                    const vectorBlocks = algos.map(a => {
                        return `
                            ${renderVectorSummary(a.final_vector_summary, `${a.label} Final Vectors`)}
                            ${renderDetectedFaultSummary(a.detected_faults || [], `${a.label} Detected Per-Fault List`)}
                        `;
                    }).join('');

                    const chartCanvases = selectedMetrics.map(metric => {
                        const id = `${targetElement.id}_chart_${idx}_${metric}`;
                        return `<div class="dse-chart"><canvas id="${id}" height="120"></canvas></div>`;
                    }).join('');

                    return `
                        <article class="result-card">
                            <div class="result-head">
                                <strong>${cmp.netlist}</strong>
                                <span class="badge badge-run">${dseLabel}</span>
                            </div>
                            <div style="padding: 12px; color: #365274; font-size: 13px;">${overlapText}</div>
                            <div style="padding: 0 12px 12px 12px; overflow-x:auto;">
                                <table class="dse-table">
                                    <thead><tr><th>Metric</th>${headers}</tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>
                            </div>
                            <div class="dse-mini-charts" style="padding: 0 12px 12px 12px;">${chartCanvases}</div>
                            <div style="display:grid; gap:10px; padding-bottom: 8px;">${vectorBlocks}</div>
                        </article>
                    `;
                }
            });

            targetElement.innerHTML = cards.join('');

            comparisons.forEach((cmp, idx) => {
                selectedMetrics.forEach(metric => {
                    if (isIterative) {
                        drawDseIterativeChart(`${targetElement.id}_chart_${idx}_${metric}`, cmp, metric);
                    } else {
                        drawDseChart(`${targetElement.id}_chart_${idx}_${metric}`, cmp, metric);
                    }
                });
            });
        }

        function drawDseChart(canvasId, comparison, metric) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const width = canvas.width = canvas.clientWidth;
            const height = canvas.height;
            ctx.clearRect(0, 0, width, height);

            const algos = comparison.algorithms || [];
            if (!algos.length) return;

            const values = algos.map(a => Number(a.metrics[metric] || 0));
            const maxVal = Math.max(...values, 1);
            const barW = Math.max(26, Math.floor((width - 40) / Math.max(values.length, 1) - 10));
            const gap = 10;
            const colors = ['#0f766e', '#b91c1c', '#1d4ed8', '#7c3aed'];
            const metricTitle = {
                coverage: 'Coverage (%)',
                time: 'Time (ms)',
                backtracks: 'Backtracks',
                memory: 'Peak Memory (KB)',
                test_vectors: 'Final Pattern Count',
                toggle_count: 'Toggle Count',
                peak_switching: 'Peak Switching / Pattern',
                runtime_overhead: 'Fill Overhead (ms)',
            };

            ctx.font = '12px Space Grotesk';
            ctx.fillStyle = '#365274';
            ctx.fillText(`Metric: ${metricTitle[metric] || metric}`, 10, 16);

            values.forEach((v, i) => {
                const h = Math.round((v / maxVal) * (height - 58));
                const x = 20 + i * (barW + gap);
                const y = height - 28 - h;
                ctx.fillStyle = colors[i % colors.length];
                ctx.fillRect(x, y, barW, h);
                ctx.fillStyle = '#10243f';
                const valueText = (metric === 'backtracks' || metric === 'test_vectors' || metric === 'toggle_count' || metric === 'peak_switching')
                    ? String(Math.round(v))
                    : String(v.toFixed(metric === 'coverage' ? 2 : metric === 'runtime_overhead' ? 3 : 1));
                ctx.fillText(valueText, x, y - 5);
                ctx.fillText(algos[i].label, x, height - 8);
            });
        }

        function drawDseIterativeChart(canvasId, comparison, metric) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const width = canvas.width = canvas.clientWidth;
            const height = canvas.height;
            ctx.clearRect(0, 0, width, height);

            const algos = comparison.algorithms || [];
            if (!algos.length) return;

            // For iterative, draw avg/min/max for each algorithm
            const avgValues = algos.map(a => {
                const stats = a.metrics_stats && a.metrics_stats[metric];
                return stats ? stats.avg : 0;
            });
            const maxVal = Math.max(...avgValues, 1);
            const barW = Math.max(26, Math.floor((width - 40) / Math.max(algos.length, 1) - 10));
            const gap = 10;
            const colors = ['#0f766e', '#b91c1c', '#1d4ed8', '#7c3aed'];
            const metricTitle = {
                coverage: 'Coverage (%)',
                time: 'Time (ms)',
                backtracks: 'Backtracks',
                memory: 'Peak Memory (KB)',
                test_vectors: 'Final Pattern Count',
                toggle_count: 'Toggle Count',
                peak_switching: 'Peak Switching / Pattern',
                runtime_overhead: 'Fill Overhead (ms)',
            };

            ctx.font = '12px Space Grotesk';
            ctx.fillStyle = '#365274';
            ctx.fillText(`${metricTitle[metric] || metric} (Iterative Avg)`, 10, 16);

            avgValues.forEach((v, i) => {
                // Draw average bar only
                const h = Math.round((v / maxVal) * (height - 58));
                const x = 20 + i * (barW + gap);
                const y = height - 28 - h;
                ctx.fillStyle = colors[i % colors.length];
                ctx.fillRect(x, y, barW, h);

                ctx.fillStyle = '#10243f';
                const decimals = metric === 'coverage' ? 2 : (metric === 'test_vectors' || metric === 'backtracks') ? 0 : 1;
                ctx.fillText(v.toFixed(decimals), x, y - 5);
                ctx.fillText(algos[i].label, x, height - 8);
            });
        }

        loadNetlists();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/netlists', methods=['GET'])
def list_netlists():
    """List available netlists."""
    try:
        if not NETLISTS_FOLDER.exists():
            return jsonify({'netlists': []})
        
        netlists = sorted([f.name for f in NETLISTS_FOLDER.glob('*.txt')])
        return jsonify({'netlists': netlists})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/images/<path:filename>', methods=['GET'])
def serve_image(filename):
    """Serve netlist-related images from the images folder."""
    safe_name = Path(filename).name
    image_path = IMAGES_FOLDER / safe_name
    if not image_path.exists() or not image_path.is_file():
        return jsonify({'error': f'Image not found: {safe_name}'}), 404
    return send_from_directory(str(IMAGES_FOLDER), safe_name)

@app.route('/api/run', methods=['POST'])
def run_atpg():
    """Run ATPG on selected netlists and algorithms."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        algorithms = payload.get('algorithms', ['D'])

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400
        
        if not algorithms or not isinstance(algorithms, list):
            return jsonify({'error': 'algorithms array required'}), 400

        results = []

        for netlist_name in netlist_names:
            netlist_name = netlist_name.strip()
            netlist_path = NETLISTS_FOLDER / netlist_name

            if not netlist_path.exists():
                results.append({'error': f'Netlist not found: {netlist_name}'})
                continue

            for algo in algorithms:
                algo = algo.strip().upper()
                try:
                    circuit = parse_netlist(str(netlist_path))
                    levelize(circuit)

                    if algo == 'BASIC':
                        assign_default_inputs(circuit)
                        simulate_event_driven(circuit)
                        result_data = {
                            'status': 'ok',
                            'node_count': len(circuit.nodes),
                            'pi_count': len(circuit.PIs),
                            'po_count': len(circuit.POs),
                            'pi_values': {pi.name: pi.value for pi in circuit.PIs},
                            'po_values': {po.name: po.value for po in circuit.POs},
                            'fault_count': len(generate_faults(circuit)),
                        }
                        results.append(format_basic_result(result_data, netlist_name))
                    elif algo == 'D':
                        engine = DAlgorithmEngine(circuit)
                        result_data = engine.run()
                        results.append(format_result(result_data, 'D', netlist_name))
                    elif algo in ('D_EXHAUSTIVE', 'D2'):
                        engine = DExhaustiveAlgorithmEngine(circuit)
                        result_data = engine.run()
                        results.append(format_result(result_data, 'D_EXHAUSTIVE', netlist_name))
                    elif algo == 'PODEM':
                        engine = PODEMEngine(circuit)
                        result_data = engine.run()
                        results.append(format_result(result_data, 'PODEM', netlist_name))
                except Exception as e:
                    results.append({'error': f'{algo} failed on {netlist_name}: {str(e)}'})

        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


def _run_engine_with_memory(engine):
    """Run an ATPG engine and capture wall time plus peak traced memory."""
    tracemalloc.start()
    t0 = perf_counter()
    result = engine.run()
    wall_ms = (perf_counter() - t0) * 1000.0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result['_wall_time_ms'] = wall_ms
    result['_memory_peak_bytes'] = peak
    return result


def _image_url_for_netlist(netlist_name):
    stem = Path(netlist_name).stem
    if not IMAGES_FOLDER.exists():
        return None

    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
        candidate = IMAGES_FOLDER / f'{stem}{ext}'
        if candidate.exists() and candidate.is_file():
            return f"/api/images/{candidate.name}"
    return None


def _canonicalize_vector(vector, pi_order):
    return tuple(vector.get(pi, 'X') for pi in pi_order)


def _is_all_x_vector(vector):
    if not isinstance(vector, dict) or not vector:
        return False
    return all(v == 'X' for v in vector.values())


def _build_final_vector_summary(result_data):
    detected_vectors = []
    excluded_all_x_count = 0
    for row in result_data.get('results', []):
        if row.get('detected', False):
            vec = row.get('test_vector', {}) or {}
            if isinstance(vec, dict):
                if _is_all_x_vector(vec):
                    excluded_all_x_count += 1
                    continue
                detected_vectors.append(vec)

    if not detected_vectors:
        return {
            'vector_count': 0,
            'pi_order': [],
            'unique_vector_list': [],
            'excluded_all_x_count': excluded_all_x_count,
        }

    pi_order = sorted({pi for vec in detected_vectors for pi in vec.keys()})
    seen = set()
    unique = []

    for vec in detected_vectors:
        signature = _canonicalize_vector(vec, pi_order)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append({pi: vec.get(pi, 'X') for pi in pi_order})

    return {
        'vector_count': len(unique),
        'pi_order': pi_order,
        'unique_vector_list': unique,
        'excluded_all_x_count': excluded_all_x_count,
    }


def _vector_signature(vector, pi_order):
    return tuple((pi, vector.get(pi, 'X')) for pi in pi_order)


def _seed_from_parts(*parts):
    digest = hashlib.sha256('::'.join(str(part) for part in parts).encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def _fill_vector_x_bits(vector, policy, seed_parts=None):
    filled = {}
    x_bits_filled = 0
    rng = None

    if policy == 'random-fill':
        rng = random.Random(_seed_from_parts(*(seed_parts or [])))

    for name, value in vector.items():
        if value != 'X':
            filled[name] = value
            continue

        x_bits_filled += 1
        if policy == '0-fill':
            filled[name] = '0'
        elif policy == '1-fill':
            filled[name] = '1'
        elif policy == 'random-fill':
            filled[name] = rng.choice(['0', '1']) if rng is not None else '0'
        else:
            filled[name] = 'X'

    return filled, x_bits_filled


def _canonicalized_filled_vectors(vector_list, pi_order):
    seen = set()
    unique = []
    for vec in vector_list:
        signature = _vector_signature(vec, pi_order)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append({pi: vec.get(pi, 'X') for pi in pi_order})
    return unique


def _switching_metrics(vector_list, pi_order):
    if not vector_list or len(vector_list) < 2:
        return {
            'toggle_count': 0,
            'peak_switching': 0,
        }

    toggle_count = 0
    peak_switching = 0

    for left, right in zip(vector_list, vector_list[1:]):
        pair_toggles = 0
        for pi in pi_order:
            if left.get(pi, 'X') != right.get(pi, 'X'):
                pair_toggles += 1
        toggle_count += pair_toggles
        peak_switching = max(peak_switching, pair_toggles)

    return {
        'toggle_count': toggle_count,
        'peak_switching': peak_switching,
    }


def _policy_signature_set(summary):
    pi_order = summary.get('pi_order', []) or []
    vectors = summary.get('unique_vector_list', []) or []
    return {
        tuple((pi, vec.get(pi, 'X')) for pi in pi_order)
        for vec in vectors
    }


def _build_fill_policy_summary(result_data, netlist_name, policy):
    detected_rows = [
        row for row in result_data.get('results', [])
        if row.get('detected', False)
    ]

    concrete_vectors = []
    fill_bits_used = 0
    fill_start = perf_counter()

    for row in detected_rows:
        raw_vector = row.get('test_vector', {}) or {}
        if not isinstance(raw_vector, dict):
            continue

        filled_vector, filled_bits = _fill_vector_x_bits(
            raw_vector,
            policy,
            seed_parts=(netlist_name, policy, row.get('fault', ''), _vector_signature(raw_vector, sorted(raw_vector.keys()))),
        )
        fill_bits_used += filled_bits
        concrete_vectors.append(filled_vector)

    fill_runtime_ms = (perf_counter() - fill_start) * 1000.0
    pi_order = sorted({pi for vec in concrete_vectors for pi in vec.keys()})
    unique_vectors = _canonicalized_filled_vectors(concrete_vectors, pi_order)
    switching = _switching_metrics(unique_vectors, pi_order)
    pre_fill_count = len(concrete_vectors)
    post_fill_count = len(unique_vectors)

    return {
        'key': policy,
        'label': policy,
        'metrics': {
            'coverage': float(result_data.get('fault_coverage_pct', 0.0)),
            'time': float(result_data.get('total_time_ms', 0.0)),
            'backtracks': float(result_data.get('total_backtracks', 0)),
            'memory': float(result_data.get('_memory_peak_bytes', 0)) / 1024.0,
            'test_vectors': float(post_fill_count),
            'toggle_count': float(switching['toggle_count']),
            'peak_switching': float(switching['peak_switching']),
            'runtime_overhead': float(fill_runtime_ms),
        },
        'summary': {
            'status': result_data.get('status', 'ok'),
            'faults': result_data.get('fault_count', 0),
            'detected': result_data.get('detected_faults', 0),
            'undetected': result_data.get('undetected_faults', 0),
            'pre_fill_pattern_count': pre_fill_count,
            'post_fill_pattern_count': post_fill_count,
            'pattern_delta': pre_fill_count - post_fill_count,
            'fill_bits_used': fill_bits_used,
        },
        'final_vector_summary': {
            'vector_count': post_fill_count,
            'pi_order': pi_order,
            'unique_vector_list': unique_vectors,
            'excluded_all_x_count': 0,
        },
        'detected_faults': [
            _format_fault_line({
                **row,
                'test_vector': _fill_vector_x_bits(
                    row.get('test_vector', {}) or {},
                    policy,
                    seed_parts=(netlist_name, policy, row.get('fault', '')),
                )[0],
            })
            for row in detected_rows
        ],
    }


def _format_fault_line(entry):
    return (
        f"- Fault {entry.get('fault')} | vector={entry.get('test_vector', {})} "
        f"| detected={entry.get('detected', False)} "
        f"| po={entry.get('po_values', {})} "
        f"| backtracks={entry.get('backtracks', 0)} "
        f"| time_us={entry.get('elapsed_us', 0):.3f}"
    )


def _detected_fault_lines(result_data, concrete_only=False):
    return [
        _format_fault_line(row)
        for row in result_data.get('results', [])
        if row.get('detected', False)
        and (not concrete_only or not _is_all_x_vector(row.get('test_vector', {}) or {}))
    ]


def _dse_algo_metrics(label, result_data):
    final_vectors = _build_final_vector_summary(result_data)
    detected_faults = _detected_fault_lines(result_data, concrete_only=True)
    return {
        'key': label,
        'label': label,
        'metrics': {
            'coverage': float(result_data.get('fault_coverage_pct', 0.0)),
            'time': float(result_data.get('total_time_ms', result_data.get('_wall_time_ms', 0.0))),
            'backtracks': float(result_data.get('total_backtracks', 0)),
            'memory': float(result_data.get('_memory_peak_bytes', 0)) / 1024.0,
            'test_vectors': float(final_vectors.get('vector_count', 0)),
        },
        'summary': {
            'status': result_data.get('status', 'ok'),
            'faults': result_data.get('fault_count', 0),
            'detected': result_data.get('detected_faults', 0),
            'undetected': result_data.get('undetected_faults', 0),
        },
        'final_vector_summary': final_vectors,
        'detected_faults': detected_faults,
    }


def _detected_fault_set(result_data):
    return {
        row.get('fault')
        for row in result_data.get('results', [])
        if row.get('detected', False)
    }


@app.route('/api/dse-fill-variants', methods=['POST'])
def run_dse_fill_variants():
    """Run DSE #5: compare fill policies on detected vectors."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []
        policies = ['0-fill', '1-fill', 'random-fill']

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                comparisons.append({
                    'netlist': name,
                    'error': f'Netlist not found: {name}',
                })
                continue

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            base_result = _run_engine_with_memory(DAlgorithmEngine(circuit))

            algorithms = [
                _build_fill_policy_summary(base_result, name, policy)
                for policy in policies
            ]

            policy_sets = {algo['key']: _policy_signature_set(algo['final_vector_summary']) for algo in algorithms}

            comparisons.append({
                'netlist': name,
                'algorithms': algorithms,
                'fault_overlap': {
                    'zero_one_common': len(policy_sets['0-fill'] & policy_sets['1-fill']),
                    'zero_random_common': len(policy_sets['0-fill'] & policy_sets['random-fill']),
                    'one_random_common': len(policy_sets['1-fill'] & policy_sets['random-fill']),
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


def _run_simulation_kernel_with_memory(circuit, kernel):
    tracemalloc.start()
    t0 = perf_counter()
    if kernel == 'simulate':
        simulate(circuit)
    else:
        simulate_event_driven(circuit)
    wall_ms = (perf_counter() - t0) * 1000.0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    po_values = {po.name: po.value for po in circuit.POs}
    return {
        '_wall_time_ms': wall_ms,
        '_memory_peak_bytes': peak,
        'po_values': po_values,
    }


@app.route('/api/dse', methods=['POST'])
def run_dse():
    """Run DSE #1: compare D and heuristic-enabled PODEM."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                comparisons.append({
                    'netlist': name,
                    'error': f'Netlist not found: {name}',
                })
                continue

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            d_result = _run_engine_with_memory(DAlgorithmEngine(circuit))

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            podem_result = _run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))

            algo_rows = [
                _dse_algo_metrics('D', d_result),
                _dse_algo_metrics('PODEM', podem_result),
            ]

            # Compare D against original PODEM (heuristic-enabled).
            podem_ref = podem_result
            d_set = _detected_fault_set(d_result)
            p_set = _detected_fault_set(podem_ref)

            comparisons.append({
                'netlist': name,
                'algorithms': algo_rows,
                'fault_overlap': {
                    'both_detected': len(d_set & p_set),
                    'd_only': len(d_set - p_set),
                    'podem_only': len(p_set - d_set),
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/api/dse-podem-variants', methods=['POST'])
def run_dse_podem_variants():
    """Run DSE #2: compare PODEM and PODEM_NO_HEUR."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                comparisons.append({
                    'netlist': name,
                    'error': f'Netlist not found: {name}',
                })
                continue

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            podem_result = _run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            podem_no_heur_result = _run_engine_with_memory(PODEMEngine(circuit, use_heuristics=False))

            p_set = _detected_fault_set(podem_result)
            p0_set = _detected_fault_set(podem_no_heur_result)

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    _dse_algo_metrics('PODEM', podem_result),
                    _dse_algo_metrics('PODEM_NO_HEUR', podem_no_heur_result),
                ],
                'fault_overlap': {
                    'both_detected': len(p_set & p0_set),
                    'podem_only': len(p_set - p0_set),
                    'podem_no_heur_only': len(p0_set - p_set),
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/api/dse-d-variants', methods=['POST'])
def run_dse_d_variants():
    """Run Design Space Exploration comparing D and D_EXHAUSTIVE (d2.py)."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                comparisons.append({
                    'netlist': name,
                    'error': f'Netlist not found: {name}',
                })
                continue

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            d_result = _run_engine_with_memory(DAlgorithmEngine(circuit))

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            d_exhaustive_result = _run_engine_with_memory(DExhaustiveAlgorithmEngine(circuit))

            d_set = _detected_fault_set(d_result)
            d2_set = _detected_fault_set(d_exhaustive_result)

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    _dse_algo_metrics('D', d_result),
                    _dse_algo_metrics('D_EXHAUSTIVE', d_exhaustive_result),
                ],
                'fault_overlap': {
                    'both_detected': len(d_set & d2_set),
                    'd_only': len(d_set - d2_set),
                    'd_exhaustive_only': len(d2_set - d_set),
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/api/dse-sim-kernels', methods=['POST'])
def run_dse_sim_kernels():
    """Run DSE #4: compare simulate() and simulate_event_driven() for Basic flow."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                comparisons.append({
                    'netlist': name,
                    'error': f'Netlist not found: {name}',
                })
                continue

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            assign_default_inputs(circuit)
            sim_result = _run_simulation_kernel_with_memory(circuit, 'simulate')

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            assign_default_inputs(circuit)
            ev_result = _run_simulation_kernel_with_memory(circuit, 'event_driven')

            sim_po = sim_result.get('po_values', {})
            ev_po = ev_result.get('po_values', {})
            po_names = sorted(set(sim_po.keys()) | set(ev_po.keys()))
            po_matches = sum(1 for po in po_names if sim_po.get(po) == ev_po.get(po))
            po_total = len(po_names)
            po_mismatches = po_total - po_matches

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    {
                        'key': 'SIMULATE',
                        'label': 'SIMULATE',
                        'metrics': {
                            'coverage': None,
                            'time': float(sim_result.get('_wall_time_ms', 0.0)),
                            'backtracks': None,
                            'memory': float(sim_result.get('_memory_peak_bytes', 0)) / 1024.0,
                            'test_vectors': None,
                        },
                        'summary': {
                            'status': 'ok',
                        },
                        'final_vector_summary': {
                            'vector_count': 0,
                            'pi_order': [],
                            'unique_vector_list': [],
                            'excluded_all_x_count': 0,
                        },
                        'detected_faults': [
                            f"PO {po} => {sim_po.get(po)}"
                            for po in po_names
                        ],
                    },
                    {
                        'key': 'EVENT_DRIVEN',
                        'label': 'EVENT_DRIVEN',
                        'metrics': {
                            'coverage': None,
                            'time': float(ev_result.get('_wall_time_ms', 0.0)),
                            'backtracks': None,
                            'memory': float(ev_result.get('_memory_peak_bytes', 0)) / 1024.0,
                            'test_vectors': None,
                        },
                        'summary': {
                            'status': 'ok',
                        },
                        'final_vector_summary': {
                            'vector_count': 0,
                            'pi_order': [],
                            'unique_vector_list': [],
                            'excluded_all_x_count': 0,
                        },
                        'detected_faults': [
                            f"PO {po} => {ev_po.get(po)}"
                            for po in po_names
                        ],
                    },
                ],
                'fault_overlap': {
                    'po_matches': po_matches,
                    'po_total': po_total,
                    'po_mismatches': po_mismatches,
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


def _calculate_stats(values):
    """Calculate min, max, avg, std dev from a list of numbers."""
    if not values:
        return {'min': 0, 'max': 0, 'avg': 0, 'std': 0}
    
    import statistics
    min_v = min(values)
    max_v = max(values)
    avg_v = statistics.mean(values)
    std_v = statistics.stdev(values) if len(values) > 1 else 0
    
    return {
        'min': min_v,
        'max': max_v,
        'avg': avg_v,
        'std': std_v,
    }


def _aggregate_algo_metrics_iterative(label, results_list):
    """Aggregate metrics from multiple runs of an algorithm."""
    if not results_list:
        return {
            'key': label,
            'label': label,
            'metrics_stats': {
                'coverage': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                'time': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                'backtracks': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                'memory': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                'test_vectors': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
            },
        }
    
    metrics_data = {
        'coverage': [],
        'time': [],
        'backtracks': [],
        'memory': [],
        'test_vectors': [],
    }
    
    for result in results_list:
        final_vectors = _build_final_vector_summary(result)
        metrics_data['coverage'].append(float(result.get('fault_coverage_pct', 0.0)))
        metrics_data['time'].append(float(result.get('total_time_ms', result.get('_wall_time_ms', 0.0))))
        metrics_data['backtracks'].append(float(result.get('total_backtracks', 0)))
        metrics_data['memory'].append(float(result.get('_memory_peak_bytes', 0)) / 1024.0)
        metrics_data['test_vectors'].append(float(final_vectors.get('vector_count', 0)))
    
    return {
        'key': label,
        'label': label,
        'metrics_stats': {
            'coverage': _calculate_stats(metrics_data['coverage']),
            'time': _calculate_stats(metrics_data['time']),
            'backtracks': _calculate_stats(metrics_data['backtracks']),
            'memory': _calculate_stats(metrics_data['memory']),
            'test_vectors': _calculate_stats(metrics_data['test_vectors']),
        },
    }


@app.route('/api/dse-iterative', methods=['POST'])
def run_dse_iterative():
    """Run DSE #1 iteratively: D vs PODEM with multiple iterations."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        iterations = min(max(payload.get('iterations', 100), 1), 1000)

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                continue

            d_results = []
            podem_results = []

            for _ in range(iterations):
                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                d_result = _run_engine_with_memory(DAlgorithmEngine(circuit))
                d_results.append(d_result)

                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                podem_result = _run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))
                podem_results.append(podem_result)

            # Aggregate overlaps
            all_d_sets = [_detected_fault_set(r) for r in d_results]
            all_p_sets = [_detected_fault_set(r) for r in podem_results]
            
            both_detected_counts = [len(d_set & p_set) for d_set, p_set in zip(all_d_sets, all_p_sets)]
            d_only_counts = [len(d_set - p_set) for d_set, p_set in zip(all_d_sets, all_p_sets)]
            p_only_counts = [len(p_set - d_set) for d_set, p_set in zip(all_d_sets, all_p_sets)]

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    _aggregate_algo_metrics_iterative('D', d_results),
                    _aggregate_algo_metrics_iterative('PODEM', podem_results),
                ],
                'fault_overlap': {
                    'both_detected_avg': sum(both_detected_counts) / len(both_detected_counts) if both_detected_counts else 0,
                    'both_detected_min': min(both_detected_counts) if both_detected_counts else 0,
                    'both_detected_max': max(both_detected_counts) if both_detected_counts else 0,
                    'd_only_avg': sum(d_only_counts) / len(d_only_counts) if d_only_counts else 0,
                    'pode_only_avg': sum(p_only_counts) / len(p_only_counts) if p_only_counts else 0,
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/api/dse-podem-variants-iterative', methods=['POST'])
def run_dse_podem_variants_iterative():
    """Run DSE #2 iteratively: PODEM vs PODEM_NO_HEUR with multiple iterations."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        iterations = min(max(payload.get('iterations', 100), 1), 1000)

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                continue

            podem_results = []
            podem_no_heur_results = []

            for _ in range(iterations):
                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                podem_result = _run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))
                podem_results.append(podem_result)

                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                podem_no_heur_result = _run_engine_with_memory(PODEMEngine(circuit, use_heuristics=False))
                podem_no_heur_results.append(podem_no_heur_result)

            # Aggregate overlaps
            all_p_sets = [_detected_fault_set(r) for r in podem_results]
            all_p0_sets = [_detected_fault_set(r) for r in podem_no_heur_results]
            
            both_detected_counts = [len(p_set & p0_set) for p_set, p0_set in zip(all_p_sets, all_p0_sets)]
            p_only_counts = [len(p_set - p0_set) for p_set, p0_set in zip(all_p_sets, all_p0_sets)]
            p0_only_counts = [len(p0_set - p_set) for p_set, p0_set in zip(all_p_sets, all_p0_sets)]

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    _aggregate_algo_metrics_iterative('PODEM', podem_results),
                    _aggregate_algo_metrics_iterative('PODEM_NO_HEUR', podem_no_heur_results),
                ],
                'fault_overlap': {
                    'both_detected_avg': sum(both_detected_counts) / len(both_detected_counts) if both_detected_counts else 0,
                    'both_detected_min': min(both_detected_counts) if both_detected_counts else 0,
                    'both_detected_max': max(both_detected_counts) if both_detected_counts else 0,
                    'podem_only_avg': sum(p_only_counts) / len(p_only_counts) if p_only_counts else 0,
                    'podem_no_heur_only_avg': sum(p0_only_counts) / len(p0_only_counts) if p0_only_counts else 0,
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/api/dse-d-variants-iterative', methods=['POST'])
def run_dse_d_variants_iterative():
    """Run DSE #3 iteratively: D vs D_EXHAUSTIVE with multiple iterations."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        iterations = min(max(payload.get('iterations', 100), 1), 1000)

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                continue

            d_results = []
            d_exhaustive_results = []

            for _ in range(iterations):
                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                d_result = _run_engine_with_memory(DAlgorithmEngine(circuit))
                d_results.append(d_result)

                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                d_exhaustive_result = _run_engine_with_memory(DExhaustiveAlgorithmEngine(circuit))
                d_exhaustive_results.append(d_exhaustive_result)

            # Aggregate overlaps
            all_d_sets = [_detected_fault_set(r) for r in d_results]
            all_d2_sets = [_detected_fault_set(r) for r in d_exhaustive_results]
            
            both_detected_counts = [len(d_set & d2_set) for d_set, d2_set in zip(all_d_sets, all_d2_sets)]
            d_only_counts = [len(d_set - d2_set) for d_set, d2_set in zip(all_d_sets, all_d2_sets)]
            d2_only_counts = [len(d2_set - d_set) for d_set, d2_set in zip(all_d_sets, all_d2_sets)]

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    _aggregate_algo_metrics_iterative('D', d_results),
                    _aggregate_algo_metrics_iterative('D_EXHAUSTIVE', d_exhaustive_results),
                ],
                'fault_overlap': {
                    'both_detected_avg': sum(both_detected_counts) / len(both_detected_counts) if both_detected_counts else 0,
                    'both_detected_min': min(both_detected_counts) if both_detected_counts else 0,
                    'both_detected_max': max(both_detected_counts) if both_detected_counts else 0,
                    'd_only_avg': sum(d_only_counts) / len(d_only_counts) if d_only_counts else 0,
                    'd_exhaustive_only_avg': sum(d2_only_counts) / len(d2_only_counts) if d2_only_counts else 0,
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/api/dse-sim-kernels-iterative', methods=['POST'])
def run_dse_sim_kernels_iterative():
    """Run DSE #4 iteratively: SIMULATE vs EVENT_DRIVEN with multiple iterations."""
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        iterations = min(max(payload.get('iterations', 100), 1), 1000)

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                continue

            sim_times = []
            ev_times = []
            sim_memories = []
            ev_memories = []
            po_matches_list = []

            for _ in range(iterations):
                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                assign_default_inputs(circuit)
                sim_result = _run_simulation_kernel_with_memory(circuit, 'simulate')
                
                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                assign_default_inputs(circuit)
                ev_result = _run_simulation_kernel_with_memory(circuit, 'event_driven')

                sim_times.append(float(sim_result.get('_wall_time_ms', 0.0)))
                ev_times.append(float(ev_result.get('_wall_time_ms', 0.0)))
                sim_memories.append(float(sim_result.get('_memory_peak_bytes', 0)) / 1024.0)
                ev_memories.append(float(ev_result.get('_memory_peak_bytes', 0)) / 1024.0)

                sim_po = sim_result.get('po_values', {})
                ev_po = ev_result.get('po_values', {})
                po_names = sorted(set(sim_po.keys()) | set(ev_po.keys()))
                po_matches = sum(1 for po in po_names if sim_po.get(po) == ev_po.get(po))
                po_matches_list.append(po_matches)

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    {
                        'key': 'SIMULATE',
                        'label': 'SIMULATE',
                        'metrics_stats': {
                            'coverage': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'time': _calculate_stats(sim_times),
                            'backtracks': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'memory': _calculate_stats(sim_memories),
                            'test_vectors': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        },
                    },
                    {
                        'key': 'EVENT_DRIVEN',
                        'label': 'EVENT_DRIVEN',
                        'metrics_stats': {
                            'coverage': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'time': _calculate_stats(ev_times),
                            'backtracks': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'memory': _calculate_stats(ev_memories),
                            'test_vectors': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        },
                    },
                ],
                'fault_overlap': {
                    'po_matches_avg': sum(po_matches_list) / len(po_matches_list) if po_matches_list else 0,
                    'po_total': len(po_names) if 'po_names' in locals() else 0,
                    'po_mismatches_avg': len(po_names) - (sum(po_matches_list) / len(po_matches_list)) if po_matches_list and 'po_names' in locals() else 0,
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


def format_result(result_data, algo, filename):
    """Format ATPG result data for frontend display."""
    final_vectors = _build_final_vector_summary(result_data)

    # Mirror the CLI summary fields so web output matches terminal output.
    stats = {
        'Status': result_data.get('status', 'ok'),
        'Faults simulated': result_data.get('fault_count', 0),
        'Detected faults': result_data.get('detected_faults', 0),
        'Undetected faults': result_data.get('undetected_faults', 0),
        'Fault coverage (%)': f"{result_data.get('fault_coverage_pct', 0):.2f}",
        'Final test vectors': final_vectors.get('vector_count', 0),
        'Total backtracks': result_data.get('total_backtracks', 0),
        'Average backtracks per fault': f"{result_data.get('avg_backtracks_per_fault', 0):.2f}",
        'Total time (ms)': f"{result_data.get('total_time_ms', 0):.3f}",
        'Average per fault (us)': f"{result_data.get('avg_time_per_fault_us', 0):.3f}",
    }

    # Keep per-fault lines in the same style as CLI output.
    faults = [_format_fault_line(entry) for entry in result_data.get('results', [])]
    detected_faults = _detected_fault_lines(result_data, concrete_only=True)

    return {
        'algorithm': algo,
        'filename': filename,
        'stats': stats,
        'faults': faults,
        'final_vector_summary': final_vectors,
        'detected_faults': detected_faults,
    }


def format_basic_result(result_data, filename):
    """Format old main.py option 1 (basic flow) data for frontend display."""
    stats = {
        'Status': result_data.get('status', 'ok'),
        'Nodes': result_data.get('node_count', 0),
        'PIs': result_data.get('pi_count', 0),
        'POs': result_data.get('po_count', 0),
        'Total faults generated': result_data.get('fault_count', 0),
    }

    faults = []
    pi_values = result_data.get('pi_values', {})
    po_values = result_data.get('po_values', {})

    faults.append('[Inputs]')
    faults.extend(
        f"{pi_name} = {pi_val}"
        for pi_name, pi_val in sorted(pi_values.items())
    )

    faults.append('[Outputs]')
    faults.extend(
        f"{po_name} = {po_val}"
        for po_name, po_val in sorted(po_values.items())
    )

    return {
        'algorithm': 'BASIC',
        'filename': filename,
        'stats': stats,
        'faults': faults,
        'hide_vector_sections': True,
        'basic_image_url': _image_url_for_netlist(filename),
    }

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
