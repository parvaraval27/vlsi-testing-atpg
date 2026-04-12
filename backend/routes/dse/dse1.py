from flask import Blueprint, jsonify, request
from d import DAlgorithmEngine
from podem import PODEMEngine
from netlist_graph import levelize, parse_netlist

from backend.config import NETLISTS_FOLDER
from backend.utils.dse_helpers import (
    aggregate_algo_metrics_iterative,
    detected_fault_set,
    dse_algo_metrics,
    run_engine_with_memory,
)

bp = Blueprint('dse1', __name__)


@bp.route('/api/dse', methods=['POST'])
def run_dse():
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
            d_result = run_engine_with_memory(DAlgorithmEngine(circuit))

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            podem_result = run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))

            algo_rows = [
                dse_algo_metrics('D', d_result),
                dse_algo_metrics('PODEM', podem_result),
            ]

            podem_ref = podem_result
            d_set = detected_fault_set(d_result)
            p_set = detected_fault_set(podem_ref)

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


@bp.route('/api/dse-iterative', methods=['POST'])
def run_dse_iterative():
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
                d_result = run_engine_with_memory(DAlgorithmEngine(circuit))
                d_results.append(d_result)

                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                podem_result = run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))
                podem_results.append(podem_result)

            all_d_sets = [detected_fault_set(r) for r in d_results]
            all_p_sets = [detected_fault_set(r) for r in podem_results]

            both_detected_counts = [len(d_set & p_set) for d_set, p_set in zip(all_d_sets, all_p_sets)]
            d_only_counts = [len(d_set - p_set) for d_set, p_set in zip(all_d_sets, all_p_sets)]
            p_only_counts = [len(p_set - d_set) for d_set, p_set in zip(all_d_sets, all_p_sets)]

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    aggregate_algo_metrics_iterative('D', d_results),
                    aggregate_algo_metrics_iterative('PODEM', podem_results),
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
