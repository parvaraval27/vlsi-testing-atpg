from flask import Blueprint, jsonify, request
from d import DAlgorithmEngine
from netlist_graph import levelize, parse_netlist

from backend.config import NETLISTS_FOLDER
from backend.utils.dse_helpers import (
    build_fill_policy_summary,
    calculate_stats,
    policy_signature_set,
    run_engine_with_memory,
)

bp = Blueprint('dse5', __name__)


@bp.route('/api/dse-fill-variants', methods=['POST'])
def run_dse_fill_variants():
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
            base_result = run_engine_with_memory(DAlgorithmEngine(circuit))

            algorithms = [
                build_fill_policy_summary(base_result, name, policy)
                for policy in policies
            ]

            policy_sets = {algo['key']: policy_signature_set(algo['final_vector_summary']) for algo in algorithms}

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


@bp.route('/api/dse-fill-variants-iterative', methods=['POST'])
def run_dse_fill_variants_iterative():
    try:
        payload = request.json or {}
        netlist_names = payload.get('netlists', [])
        iterations = min(max(payload.get('iterations', 100), 1), 1000)

        if not netlist_names or not isinstance(netlist_names, list):
            return jsonify({'error': 'netlists array required'}), 400

        comparisons = []
        policies = ['0-fill', '1-fill', 'random-fill']

        for netlist_name in netlist_names:
            name = str(netlist_name).strip()
            netlist_path = NETLISTS_FOLDER / name
            if not netlist_path.exists():
                continue

            per_policy_metrics = {
                policy: {
                    'test_vectors': [],
                    'toggle_count': [],
                    'peak_switching': [],
                    'runtime_overhead': [],
                }
                for policy in policies
            }
            zero_one_common = []
            zero_random_common = []
            one_random_common = []

            for _ in range(iterations):
                circuit = parse_netlist(str(netlist_path))
                levelize(circuit)
                base_result = run_engine_with_memory(DAlgorithmEngine(circuit))

                policy_rows = {
                    policy: build_fill_policy_summary(base_result, name, policy)
                    for policy in policies
                }

                for policy in policies:
                    metrics = policy_rows[policy].get('metrics', {})
                    per_policy_metrics[policy]['test_vectors'].append(float(metrics.get('test_vectors', 0.0)))
                    per_policy_metrics[policy]['toggle_count'].append(float(metrics.get('toggle_count', 0.0)))
                    per_policy_metrics[policy]['peak_switching'].append(float(metrics.get('peak_switching', 0.0)))
                    per_policy_metrics[policy]['runtime_overhead'].append(float(metrics.get('runtime_overhead', 0.0)))

                policy_sets = {
                    policy: policy_signature_set(policy_rows[policy].get('final_vector_summary', {}))
                    for policy in policies
                }
                zero_one_common.append(len(policy_sets['0-fill'] & policy_sets['1-fill']))
                zero_random_common.append(len(policy_sets['0-fill'] & policy_sets['random-fill']))
                one_random_common.append(len(policy_sets['1-fill'] & policy_sets['random-fill']))

            algorithms = []
            for policy in policies:
                metrics = per_policy_metrics[policy]
                algorithms.append({
                    'key': policy,
                    'label': policy,
                    'metrics_stats': {
                        'coverage': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        'time': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        'backtracks': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        'memory': {'min': 0, 'max': 0, 'avg': 0, 'std': 0},
                        'test_vectors': calculate_stats(metrics['test_vectors']),
                        'toggle_count': calculate_stats(metrics['toggle_count']),
                        'peak_switching': calculate_stats(metrics['peak_switching']),
                        'runtime_overhead': calculate_stats(metrics['runtime_overhead']),
                    },
                })

            comparisons.append({
                'netlist': name,
                'algorithms': algorithms,
                'fault_overlap': {
                    'zero_one_common': round(sum(zero_one_common) / len(zero_one_common), 2) if zero_one_common else 0,
                    'zero_random_common': round(sum(zero_random_common) / len(zero_random_common), 2) if zero_random_common else 0,
                    'one_random_common': round(sum(one_random_common) / len(one_random_common), 2) if one_random_common else 0,
                },
            })

        return jsonify({
            'status': 'ok',
            'comparisons': comparisons,
        })
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500
