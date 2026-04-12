import random

from flask import Blueprint, jsonify, request
from netlist_graph import assign_default_inputs, levelize, parse_netlist

from backend.config import NETLISTS_FOLDER
from backend.utils.dse_helpers import calculate_stats, run_simulation_kernel_with_memory

bp = Blueprint('dse4', __name__)


def _apply_vector(circuit, vector):
    for pi in circuit.PIs:
        pi.value = vector.get(pi.name, '0')


def _set_changed_inputs(circuit, previous_vector, next_vector):
    changed = []
    for pi in circuit.PIs:
        if previous_vector.get(pi.name, 'X') != next_vector.get(pi.name, 'X'):
            changed.append(pi)
    return changed


def _build_sparse_vector_sequence(circuit, count, toggle_density, seed):
    assign_default_inputs(circuit)
    current = {pi.name: pi.value for pi in circuit.PIs}
    vectors = [dict(current)]

    if count <= 1:
        return vectors

    pi_names = [pi.name for pi in circuit.PIs]
    if not pi_names:
        return vectors

    rng = random.Random(seed)
    toggle_count = max(1, int(round(len(pi_names) * toggle_density)))
    toggle_count = min(toggle_count, len(pi_names))

    for _ in range(count - 1):
        nxt = dict(current)
        for name in rng.sample(pi_names, toggle_count):
            nxt[name] = '0' if nxt[name] == '1' else '1'
        vectors.append(nxt)
        current = nxt

    return vectors


@bp.route('/api/dse-sim-kernels', methods=['POST'])
def run_dse_sim_kernels():
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
                'benchmark_mode': 'cold-start-single-vector',
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
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        iterations = min(max(payload.get('iterations', 100), 1), 1000)
        toggle_density = float(payload.get('toggle_density', 0.05))
        toggle_density = min(max(toggle_density, 0.01), 0.5)

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
            sim_gate_evals = []
            ev_gate_evals = []
            ev_duplicate_filters = []

            sim_circuit = parse_netlist(str(netlist_path))
            ev_circuit = parse_netlist(str(netlist_path))
            levelize(sim_circuit)
            levelize(ev_circuit)

            vectors = _build_sparse_vector_sequence(
                sim_circuit,
                iterations,
                toggle_density,
                seed=f"dse4::{name}::{iterations}::{toggle_density}",
            )

            previous_vector = None

            for index, vector in enumerate(vectors):
                _apply_vector(sim_circuit, vector)
                sim_result = run_simulation_kernel_with_memory(sim_circuit, 'simulate')

                if index == 0:
                    _apply_vector(ev_circuit, vector)
                    ev_result = run_simulation_kernel_with_memory(ev_circuit, 'event_driven')
                else:
                    changed_inputs = _set_changed_inputs(ev_circuit, previous_vector, vector)
                    _apply_vector(ev_circuit, vector)
                    ev_result = run_simulation_kernel_with_memory(ev_circuit, 'event_driven', changed_inputs=changed_inputs)

                previous_vector = vector

                sim_times.append(float(sim_result.get('_wall_time_ms', 0.0)))
                ev_times.append(float(ev_result.get('_wall_time_ms', 0.0)))
                sim_memories.append(float(sim_result.get('_memory_peak_bytes', 0)) / 1024.0)
                ev_memories.append(float(ev_result.get('_memory_peak_bytes', 0)) / 1024.0)

                sim_stats = sim_result.get('_kernel_stats', {}) or {}
                ev_stats = ev_result.get('_kernel_stats', {}) or {}
                sim_gate_evals.append(float(sim_stats.get('gate_evaluations', 0)))
                ev_gate_evals.append(float(ev_stats.get('gate_evaluations', 0)))
                ev_duplicate_filters.append(float(ev_stats.get('duplicate_enqueues_filtered', 0)))

                sim_po = sim_result.get('po_values', {})
                ev_po = ev_result.get('po_values', {})
                po_names = sorted(set(sim_po.keys()) | set(ev_po.keys()))
                po_matches = sum(1 for po in po_names if sim_po.get(po) == ev_po.get(po))
                po_matches_list.append(po_matches)

            avg_sim_time = sum(sim_times) / len(sim_times) if sim_times else 0.0
            avg_ev_time = sum(ev_times) / len(ev_times) if ev_times else 0.0
            speedup = (avg_sim_time / avg_ev_time) if avg_ev_time > 0 else 0.0

            comparisons.append({
                'netlist': name,
                'benchmark_mode': 'sparse-multivector-incremental',
                'toggle_density': toggle_density,
                'vector_count': len(vectors),
                'speedup_sim_over_event': speedup,
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
                            'gate_evaluations': calculate_stats(sim_gate_evals),
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
                            'gate_evaluations': calculate_stats(ev_gate_evals),
                            'duplicates_filtered': calculate_stats(ev_duplicate_filters),
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
