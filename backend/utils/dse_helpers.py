import hashlib
import random
import statistics
import tracemalloc
from time import perf_counter

from netlist_graph import simulate, simulate_event_driven


def run_engine_with_memory(engine):
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


def canonicalize_vector(vector, pi_order):
    return tuple(vector.get(pi, 'X') for pi in pi_order)


def is_all_x_vector(vector):
    if not isinstance(vector, dict) or not vector:
        return False
    return all(v == 'X' for v in vector.values())


def build_final_vector_summary(result_data):
    detected_vectors = []
    excluded_all_x_count = 0
    for row in result_data.get('results', []):
        if row.get('detected', False):
            vec = row.get('test_vector', {}) or {}
            if isinstance(vec, dict):
                if is_all_x_vector(vec):
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
        signature = canonicalize_vector(vec, pi_order)
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


def vector_signature(vector, pi_order):
    return tuple((pi, vector.get(pi, 'X')) for pi in pi_order)


def seed_from_parts(*parts):
    digest = hashlib.sha256('::'.join(str(part) for part in parts).encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def fill_vector_x_bits(vector, policy, seed_parts=None):
    filled = {}
    x_bits_filled = 0
    rng = None

    if policy == 'random-fill':
        rng = random.Random(seed_from_parts(*(seed_parts or [])))

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


def canonicalized_filled_vectors(vector_list, pi_order):
    seen = set()
    unique = []
    for vec in vector_list:
        signature = vector_signature(vec, pi_order)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append({pi: vec.get(pi, 'X') for pi in pi_order})
    return unique


def switching_metrics(vector_list, pi_order):
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


def policy_signature_set(summary):
    pi_order = summary.get('pi_order', []) or []
    vectors = summary.get('unique_vector_list', []) or []
    return {
        tuple((pi, vec.get(pi, 'X')) for pi in pi_order)
        for vec in vectors
    }


def format_fault_line(entry):
    return (
        f"- Fault {entry.get('fault')} | vector={entry.get('test_vector', {})} "
        f"| detected={entry.get('detected', False)} "
        f"| po={entry.get('po_values', {})} "
        f"| backtracks={entry.get('backtracks', 0)} "
        f"| time_us={entry.get('elapsed_us', 0):.3f}"
    )


def detected_fault_lines(result_data, concrete_only=False):
    return [
        format_fault_line(row)
        for row in result_data.get('results', [])
        if row.get('detected', False)
        and (not concrete_only or not is_all_x_vector(row.get('test_vector', {}) or {}))
    ]


def dse_algo_metrics(label, result_data):
    final_vectors = build_final_vector_summary(result_data)
    detected_faults = detected_fault_lines(result_data, concrete_only=True)
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


def detected_fault_set(result_data):
    return {
        row.get('fault')
        for row in result_data.get('results', [])
        if row.get('detected', False)
    }


def build_fill_policy_summary(result_data, netlist_name, policy):
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

        filled_vector, filled_bits = fill_vector_x_bits(
            raw_vector,
            policy,
            seed_parts=(netlist_name, policy, row.get('fault', ''), vector_signature(raw_vector, sorted(raw_vector.keys()))),
        )
        fill_bits_used += filled_bits
        concrete_vectors.append(filled_vector)

    fill_runtime_ms = (perf_counter() - fill_start) * 1000.0
    pi_order = sorted({pi for vec in concrete_vectors for pi in vec.keys()})
    unique_vectors = canonicalized_filled_vectors(concrete_vectors, pi_order)
    switching = switching_metrics(unique_vectors, pi_order)
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
            format_fault_line({
                **row,
                'test_vector': fill_vector_x_bits(
                    row.get('test_vector', {}) or {},
                    policy,
                    seed_parts=(netlist_name, policy, row.get('fault', '')),
                )[0],
            })
            for row in detected_rows
        ],
    }


def run_simulation_kernel_with_memory(circuit, kernel):
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


def calculate_stats(values):
    """Calculate min, max, avg, std dev from a list of numbers."""
    if not values:
        return {'min': 0, 'max': 0, 'avg': 0, 'std': 0}

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


def aggregate_algo_metrics_iterative(label, results_list):
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
        final_vectors = build_final_vector_summary(result)
        metrics_data['coverage'].append(float(result.get('fault_coverage_pct', 0.0)))
        metrics_data['time'].append(float(result.get('total_time_ms', result.get('_wall_time_ms', 0.0))))
        metrics_data['backtracks'].append(float(result.get('total_backtracks', 0)))
        metrics_data['memory'].append(float(result.get('_memory_peak_bytes', 0)) / 1024.0)
        metrics_data['test_vectors'].append(float(final_vectors.get('vector_count', 0)))

    return {
        'key': label,
        'label': label,
        'metrics_stats': {
            'coverage': calculate_stats(metrics_data['coverage']),
            'time': calculate_stats(metrics_data['time']),
            'backtracks': calculate_stats(metrics_data['backtracks']),
            'memory': calculate_stats(metrics_data['memory']),
            'test_vectors': calculate_stats(metrics_data['test_vectors']),
        },
    }
