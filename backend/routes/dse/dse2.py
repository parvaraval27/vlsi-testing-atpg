from flask import Blueprint, jsonify, request
from podem import PODEMEngine
from netlist_graph import levelize, parse_netlist

from backend.config import NETLISTS_FOLDER
from backend.utils.dse_helpers import (
    aggregate_algo_metrics_iterative,
    detected_fault_set,
    dse_algo_metrics,
    run_engine_with_memory,
)

bp = Blueprint('dse2', __name__)


@bp.route('/api/dse-podem-variants', methods=['POST'])
def run_dse_podem_variants():
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
            podem_result = run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))

            circuit = parse_netlist(str(netlist_path))
            levelize(circuit)
            podem_no_heur_result = run_engine_with_memory(PODEMEngine(circuit, use_heuristics=False))

            p_set = detected_fault_set(podem_result)
            p0_set = detected_fault_set(podem_no_heur_result)

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    dse_algo_metrics('PODEM', podem_result),
                    dse_algo_metrics('PODEM_NO_HEUR', podem_no_heur_result),
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


@bp.route('/api/dse-podem-variants-iterative', methods=['POST'])
def run_dse_podem_variants_iterative():
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
                podem_result = run_engine_with_memory(PODEMEngine(circuit, use_heuristics=True))
                podem_results.append(podem_result)

                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                podem_no_heur_result = run_engine_with_memory(PODEMEngine(circuit, use_heuristics=False))
                podem_no_heur_results.append(podem_no_heur_result)

            all_p_sets = [detected_fault_set(r) for r in podem_results]
            all_p0_sets = [detected_fault_set(r) for r in podem_no_heur_results]

            both_detected_counts = [len(p_set & p0_set) for p_set, p0_set in zip(all_p_sets, all_p0_sets)]
            p_only_counts = [len(p_set - p0_set) for p_set, p0_set in zip(all_p_sets, all_p0_sets)]
            p0_only_counts = [len(p0_set - p_set) for p_set, p0_set in zip(all_p_sets, all_p0_sets)]

            comparisons.append({
                'netlist': name,
                'algorithms': [
                    aggregate_algo_metrics_iterative('PODEM', podem_results),
                    aggregate_algo_metrics_iterative('PODEM_NO_HEUR', podem_no_heur_results),
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
