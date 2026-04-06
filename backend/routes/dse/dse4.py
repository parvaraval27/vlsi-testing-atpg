from flask import Blueprint, jsonify, request
from netlist_graph import assign_default_inputs, levelize, parse_netlist

from backend.config import NETLISTS_FOLDER
from backend.utils.dse_helpers import calculate_stats, run_simulation_kernel_with_memory

bp = Blueprint('dse4', __name__)


@bp.route('/api/dse-sim-kernels', methods=['POST'])
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
            sim_result = run_simulation_kernel_with_memory(circuit, 'simulate')

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            assign_default_inputs(circuit)
            ev_result = run_simulation_kernel_with_memory(circuit, 'event_driven')

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
                        'summary': {'status': 'ok'},
                        'final_vector_summary': {
                            'vector_count': 0,
                            'pi_order': [],
                            'unique_vector_list': [],
                            'excluded_all_x_count': 0,
                        },
                        'detected_faults': [f"PO {po} => {sim_po.get(po)}" for po in po_names],
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
                        'summary': {'status': 'ok'},
                        'final_vector_summary': {
                            'vector_count': 0,
                            'pi_order': [],
                            'unique_vector_list': [],
                            'excluded_all_x_count': 0,
                        },
                        'detected_faults': [f"PO {po} => {ev_po.get(po)}" for po in po_names],
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


@bp.route('/api/dse-sim-kernels-iterative', methods=['POST'])
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
                sim_result = run_simulation_kernel_with_memory(circuit, 'simulate')

                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                assign_default_inputs(circuit)
                ev_result = run_simulation_kernel_with_memory(circuit, 'event_driven')

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
                            'time': calculate_stats(sim_times),
                            'backtracks': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'memory': calculate_stats(sim_memories),
                            'test_vectors': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        },
                    },
                    {
                        'key': 'EVENT_DRIVEN',
                        'label': 'EVENT_DRIVEN',
                        'metrics_stats': {
                            'coverage': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'time': calculate_stats(ev_times),
                            'backtracks': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                            'memory': calculate_stats(ev_memories),
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
