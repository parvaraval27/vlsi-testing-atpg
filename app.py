from flask import Flask, render_template, jsonify, request, send_from_directory
from pathlib import Path
from collections import defaultdict
from html import escape
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from d import DAlgorithmEngine
from d2 import DAlgorithmEngine as DQuickAlgorithmEngine
from podem import PODEMEngine
from netlist_graph import (
    assign_default_inputs,
    generate_faults,
    levelize,
    parse_netlist,
    simulate_event_driven,
)
from backend.config import NETLISTS_FOLDER, IMAGES_FOLDER
from backend.routes.dse import dse1, dse2, dse3, dse4, dse5
from backend.utils.dse_helpers import (
    build_final_vector_summary as _build_final_vector_summary,
    detected_fault_lines as _detected_fault_lines,
    format_fault_line as _format_fault_line,
    undetected_fault_lines as _undetected_fault_lines,
)

app = Flask(__name__)
app.register_blueprint(dse1.bp)
app.register_blueprint(dse2.bp)
app.register_blueprint(dse3.bp)
app.register_blueprint(dse4.bp)
app.register_blueprint(dse5.bp)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/explainer')
def info_page():
    return render_template('explainer.html')

@app.route('/api/netlists', methods=['GET'])
def list_netlists():
    try:
        if not NETLISTS_FOLDER.exists():
            return jsonify({'netlists': []})
        
        netlists = sorted([f.name for f in NETLISTS_FOLDER.glob('*.txt')])
        return jsonify({'netlists': netlists})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/images/<path:filename>', methods=['GET'])
def serve_image(filename):
    safe_name = Path(filename).name
    image_path = IMAGES_FOLDER / safe_name
    if not image_path.exists() or not image_path.is_file():
        return jsonify({'error': f'Image not found: {safe_name}'}), 404
    return send_from_directory(str(IMAGES_FOLDER), safe_name)

@app.route('/api/run', methods=['POST'])
def run_atpg():
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
                    elif algo in ('D_QUICK', 'D2'):
                        engine = DQuickAlgorithmEngine(circuit)
                        result_data = engine.run()
                        results.append(format_result(result_data, 'D_QUICK', netlist_name))
                    elif algo == 'PODEM':
                        engine = PODEMEngine(circuit)
                        result_data = engine.run()
                        results.append(format_result(result_data, 'PODEM', netlist_name))
                except Exception as e:
                    results.append({'error': f'{algo} failed on {netlist_name}: {str(e)}'})

        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500





def _image_url_for_netlist(netlist_name):
    options = _basic_image_options_for_netlist(netlist_name)
    return options[0]['url'] if options else None


def _basic_image_options_for_netlist(netlist_name):
    options = []
    seen_urls = set()

    generated_url = _generate_basic_flow_netlist_svg(netlist_name)
    if generated_url:
        options.append({
            'label': 'Generated Graph (Netlist Parsing + Levelization)',
            'url': generated_url,
        })
        seen_urls.add(generated_url)

    stem = Path(netlist_name).stem
    if not IMAGES_FOLDER.exists():
        return options

    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
        candidate = IMAGES_FOLDER / f'{stem}{ext}'
        if not candidate.exists() or not candidate.is_file():
            continue

        url = f"/api/images/{candidate.name}"
        if url in seen_urls:
            continue

        options.append({
            'label': f"External {ext.upper()} ({candidate.name})",
            'url': url,
        })
        seen_urls.add(url)

    return options


def _generate_basic_flow_netlist_svg(netlist_name):
    try:
        stem = Path(netlist_name).stem
        netlist_path = NETLISTS_FOLDER / netlist_name
        if not netlist_path.exists():
            return None

        svg_path = IMAGES_FOLDER / f"{stem}.svg"

        if svg_path.exists() and svg_path.is_file():
            return f"/api/images/{svg_path.name}"

        if os.getenv('VERCEL') == '1':
            return None

        IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)

        circuit = parse_netlist(str(netlist_path))
        levelize(circuit)
        assign_default_inputs(circuit)
        simulate_event_driven(circuit)

        level_groups = defaultdict(list)
        for node in sorted(circuit.nodes.values(), key=lambda n: (n.level, n.name)):
            level = node.level if node.level >= 0 else 0
            level_groups[level].append(node)

        if not level_groups:
            return None

        x_spacing = 190
        y_spacing = 76
        margin_x = 64
        margin_y = 52
        node_w = 122
        node_h = 42

        positions = {}
        max_level = max(level_groups.keys())
        max_rows = max(len(nodes) for nodes in level_groups.values())

        for level in sorted(level_groups.keys()):
            for row, node in enumerate(level_groups[level]):
                x = margin_x + level * x_spacing
                y = margin_y + row * y_spacing
                positions[node.name] = (x, y)

        width = margin_x * 2 + (max_level + 1) * x_spacing + node_w
        height = margin_y * 2 + max_rows * y_spacing + node_h

        edge_lines = []
        for node in circuit.nodes.values():
            dst = positions.get(node.name)
            if not dst:
                continue
            dst_x = dst[0]
            dst_y = dst[1] + node_h / 2
            for src_node in node.fanins:
                src = positions.get(src_node.name)
                if not src:
                    continue
                src_x = src[0] + node_w
                src_y = src[1] + node_h / 2
                edge_lines.append(
                    f'<line x1="{src_x:.1f}" y1="{src_y:.1f}" x2="{dst_x:.1f}" y2="{dst_y:.1f}" '
                    f'stroke="#7a8ca3" stroke-width="1.2" marker-end="url(#arrow)" />'
                )

        node_boxes = []
        for node in circuit.nodes.values():
            pos = positions.get(node.name)
            if not pos:
                continue
            x, y = pos

            if node.role == 'PI':
                fill = '#d8f3dc'
            elif node.role == 'PO':
                fill = '#ffe8cc'
            elif node.role == 'CONST':
                fill = '#f1f3f5'
            else:
                fill = '#e7f5ff'

            label_main = escape(node.name)
            label_sub = escape(f"{node.type} | {node.value}")
            node_boxes.append(
                f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" rx="9" ry="9" '
                f'fill="{fill}" stroke="#3d4f65" stroke-width="1.1" />'
            )
            node_boxes.append(
                f'<text x="{x + 8}" y="{y + 17}" font-family="Segoe UI, Arial, sans-serif" '
                f'font-size="11" fill="#10243f">{label_main}</text>'
            )
            node_boxes.append(
                f'<text x="{x + 8}" y="{y + 32}" font-family="Segoe UI, Arial, sans-serif" '
                f'font-size="10" fill="#4b647f">{label_sub}</text>'
            )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width)}" height="{int(height)}" '
            f'viewBox="0 0 {int(width)} {int(height)}">'
            '<defs>'
            '<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="#7a8ca3" />'
            '</marker>'
            '</defs>'
            '<rect x="0" y="0" width="100%" height="100%" fill="#fbfcff" />'
            + ''.join(edge_lines)
            + ''.join(node_boxes)
            + '</svg>'
        )

        svg_path.write_text(svg, encoding='utf-8')
        return f"/api/images/{svg_path.name}"
    except Exception:
        return None

def format_result(result_data, algo, filename):
    final_vectors = _build_final_vector_summary(result_data)

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

    faults = [_format_fault_line(entry) for entry in result_data.get('results', [])]
    detected_faults = _detected_fault_lines(result_data, concrete_only=True)
    undetected_faults = _undetected_fault_lines(result_data)

    return {
        'algorithm': algo,
        'filename': filename,
        'stats': stats,
        'faults': faults,
        'final_vector_summary': final_vectors,
        'detected_faults': detected_faults,
        'undetected_faults': undetected_faults,
    }


def format_basic_result(result_data, filename):
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

    image_options = _basic_image_options_for_netlist(filename)

    return {
        'algorithm': 'BASIC',
        'filename': filename,
        'stats': stats,
        'faults': faults,
        'hide_vector_sections': True,
        'basic_image_url': image_options[0]['url'] if image_options else None,
        'basic_image_options': image_options,
    }

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
