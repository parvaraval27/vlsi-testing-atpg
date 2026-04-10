from time import perf_counter
from collections import deque
from itertools import product

from netlist_graph import (
    generate_faults,
    levelize,
    parse_netlist,
)

D_ALGEBRA = {
    '0': {'0': '0',     '1': 'D_bar', 'X': '0'},
    '1': {'0': 'D',     '1': '1',     'X': '1'},
    'X': {'0': '0',     '1': '1',     'X': 'X'},
}


def _d_algebra_intersect(good_val, faulty_val):
    row = D_ALGEBRA.get(good_val)
    if row is None:
        return None
    return row.get(faulty_val)


D_INTERSECTION = {
    '0':     {'0': '0',     '1': None,    'X': '0',     'D': None,    'D_bar': None    },
    '1':     {'0': None,    '1': '1',     'X': '1',     'D': None,    'D_bar': None    },
    'X':     {'0': '0',     '1': '1',     'X': 'X',     'D': 'D',     'D_bar': 'D_bar' },
    'D':     {'0': None,    '1': None,    'X': 'D',     'D': 'D',     'D_bar': None    },
    'D_bar': {'0': None,    '1': None,    'X': 'D_bar', 'D': None,    'D_bar': 'D_bar' },
}


def _d_intersect(v1, v2):
    return D_INTERSECTION[v1][v2]


def _intersect_cubes(cube_a, cube_b):
    result = {}
    all_keys = set(cube_a) | set(cube_b)
    for k in all_keys:
        if k in cube_a and k in cube_b:
            merged = _d_intersect(cube_a[k], cube_b[k])
            if merged is None:
                return None
            result[k] = merged
        elif k in cube_a:
            result[k] = cube_a[k]
        else:
            result[k] = cube_b[k]
    return result


SINGULAR_COVER = {
    'AND': [
        {'inputs': ['0', 'X'], 'output': '0'},
        {'inputs': ['X', '0'], 'output': '0'},
        {'inputs': ['1', '1'], 'output': '1'},
    ],
    'OR': [
        {'inputs': ['1', 'X'], 'output': '1'},
        {'inputs': ['X', '1'], 'output': '1'},
        {'inputs': ['0', '0'], 'output': '0'},
    ],
    'NAND': [
        {'inputs': ['0', 'X'], 'output': '1'},
        {'inputs': ['X', '0'], 'output': '1'},
        {'inputs': ['1', '1'], 'output': '0'},
    ],
    'NOR': [
        {'inputs': ['1', 'X'], 'output': '0'},
        {'inputs': ['X', '1'], 'output': '0'},
        {'inputs': ['0', '0'], 'output': '1'},
    ],
    'NOT': [
        {'inputs': ['0'], 'output': '1'},
        {'inputs': ['1'], 'output': '0'},
    ],
    'BUF': [
        {'inputs': ['0'], 'output': '0'},
        {'inputs': ['1'], 'output': '1'},
    ],
    'WIRE': [
        {'inputs': ['0'], 'output': '0'},
        {'inputs': ['1'], 'output': '1'},
    ],
    'XOR': [
        {'inputs': ['0', '0'], 'output': '0'},
        {'inputs': ['1', '1'], 'output': '0'},
        {'inputs': ['0', '1'], 'output': '1'},
        {'inputs': ['1', '0'], 'output': '1'},
    ],
    'XNOR': [
        {'inputs': ['0', '0'], 'output': '1'},
        {'inputs': ['1', '1'], 'output': '1'},
        {'inputs': ['0', '1'], 'output': '0'},
        {'inputs': ['1', '0'], 'output': '0'},
    ],
}

_CONTROLLING_VAL = {
    'AND': '0', 'NAND': '0',
    'OR':  '1', 'NOR':  '1',
}

_NON_CONTROLLING_VAL = {
    'AND': '1', 'NAND': '1',
    'OR':  '0', 'NOR':  '0',
    'XOR': '0', 'XNOR': '0', 
}


def _get_sc(gate_type, fanin_count):
    if gate_type in ('NOT', 'BUF', 'WIRE'):
        return SINGULAR_COVER[gate_type]

    if fanin_count == 2:
        return SINGULAR_COVER.get(gate_type, [])

    if gate_type in ('AND', 'NAND', 'OR', 'NOR'):
        ctrl = _CONTROLLING_VAL[gate_type]
        nc   = _NON_CONTROLLING_VAL[gate_type]

        if gate_type == 'AND':
            ctrl_out, nc_out = '0', '1'
        elif gate_type == 'OR':
            ctrl_out, nc_out = '1', '0'
        elif gate_type == 'NAND':
            ctrl_out, nc_out = '1', '0'
        else:
            ctrl_out, nc_out = '0', '1'

        rows = []
        for i in range(fanin_count):
            inp = ['X'] * fanin_count
            inp[i] = ctrl
            rows.append({'inputs': inp, 'output': ctrl_out})
        rows.append({'inputs': [nc] * fanin_count, 'output': nc_out})
        return rows

    if gate_type in ('XOR', 'XNOR'):
        rows = []
        for combo in product(['0', '1'], repeat=fanin_count):
            ones = sum(int(v) for v in combo)
            xor_out = '1' if (ones % 2 == 1) else '0'
            out = xor_out if gate_type == 'XOR' else ('0' if xor_out == '1' else '1')
            rows.append({'inputs': list(combo), 'output': out})
        return rows

    return []


class DAlgorithmEngine:
    def __init__(self, circuit):
        self.circuit = circuit
        self.active_fault = None
        self.backtrack_count = 0
        self._po_distances = self._compute_all_po_distances()
        self._sorted_nodes = sorted(circuit.nodes.values(), key=lambda n: n.level)

    @staticmethod
    def _invert_logic(v):
        inv = {'0': '1', '1': '0', 'D': 'D_bar', 'D_bar': 'D', 'X': 'X'}
        return inv.get(v, 'X')

    @staticmethod
    def _logic_to_pair(v):
        mapping = {'0': (0, 0), '1': (1, 1), 'D': (1, 0), 'D_bar': (0, 1), 'X': (None, None)}
        return mapping.get(v, (None, None))

    @staticmethod
    def _pair_to_logic(good, faulty):
        if good is None or faulty is None: return 'X'
        if good == 0 and faulty == 0: return '0'
        if good == 1 and faulty == 1: return '1'
        if good == 1 and faulty == 0: return 'D'
        if good == 0 and faulty == 1: return 'D_bar'
        return 'X'

    @staticmethod
    def _to_good_logic(v):
        if v == 'D':     return '1'
        if v == 'D_bar': return '0'
        return v

    @staticmethod
    def _eval_and(vals):
        if 0 in vals:    return 0
        if None in vals: return None
        return 1

    @staticmethod
    def _eval_or(vals):
        if 1 in vals:    return 1
        if None in vals: return None
        return 0

    @staticmethod
    def _eval_xor(vals):
        if None in vals: return None
        return 1 if (sum(vals) % 2) else 0

    def _eval_binary_gate(self, gate_type, vals):
        handlers = {
            'AND':  self._eval_and,
            'OR':   self._eval_or,
            'NOT':  lambda v: None if not v or v[0] is None else 1 - v[0],
            'BUF':  lambda v: None if not v else v[0],
            'WIRE': lambda v: None if not v else v[0],
            'XOR':  self._eval_xor,
            'XNOR': lambda v: None if self._eval_xor(v) is None else 1 - self._eval_xor(v),
            'NAND': lambda v: None if self._eval_and(v) is None else 1 - self._eval_and(v),
            'NOR':  lambda v: None if self._eval_or(v)  is None else 1 - self._eval_or(v),
        }
        handler = handlers.get(gate_type)
        if handler is not None:
            return handler(vals)
        if len(vals) == 1:
            return vals[0]
        return None

    def _non_controlling_value(self, gate_type):
        if gate_type in ('AND', 'NAND'): return '1'
        if gate_type in ('OR', 'NOR'): return '0'
        return 'X'  

    def _inject_fault_effect(self, node, logic_value):
        if self.active_fault is None or node is not self.active_fault.node:
            return logic_value
        good, _faulty = self._logic_to_pair(logic_value)
        if good is None:
            return 'X'
        forced_faulty = self.active_fault.stuck_at
        return self._pair_to_logic(good, forced_faulty)

    def _eval_gate_5val(self, node):
        vals = [inp.value for inp in node.fanins]
        if not vals and node.role == 'CONST':
            return node.value
        good_vals   = []
        faulty_vals = []
        for v in vals:
            g, f = self._logic_to_pair(v)
            good_vals.append(g)
            faulty_vals.append(f)
        good_out   = self._eval_binary_gate(node.type, good_vals)
        faulty_out = self._eval_binary_gate(node.type, faulty_vals)
        logic_out  = self._pair_to_logic(good_out, faulty_out)
        return self._inject_fault_effect(node, logic_out)

    def _save_state(self):
        return {n.name: n.value for n in self.circuit.nodes.values()}

    def _restore_state(self, state):
        for n in self.circuit.nodes.values():
            n.value = state[n.name]

    def _compute_pdcf_candidates(self, fault):
        stuck_val   = str(fault.stuck_at)
        good_output = str(1 - fault.stuck_at)

        faulty_inputs = ['X'] * max(1, len(fault.node.fanins))

        if fault.node.role == 'PI' or not fault.node.fanins:
            out_sym = _d_algebra_intersect(good_output, stuck_val)
            return [{fault.node: out_sym}]

        gate_type   = fault.node.type
        fanin_count = len(fault.node.fanins)
        sc_rows     = _get_sc(gate_type, fanin_count)

        good_rows = [r for r in sc_rows if r['output'] == good_output]

        pdcf_list = []
        for good_row in good_rows:
            cube     = {}
            conflict = False

            for i, fi in enumerate(fault.node.fanins):
                g_val = good_row['inputs'][i] if i < len(good_row['inputs']) else 'X'
                f_val = faulty_inputs[i]        if i < len(faulty_inputs)       else 'X'
                sym   = _d_algebra_intersect(g_val, f_val)
                if sym is None:
                    conflict = True
                    break
                cube[fi] = sym

            if conflict:
                continue

            out_sym = _d_algebra_intersect(good_output, stuck_val)
            if out_sym is None:
                continue
            cube[fault.node] = out_sym
            pdcf_list.append(cube)

        if not pdcf_list:
            out_sym = _d_algebra_intersect(good_output, stuck_val)
            pdcf_list = [{fault.node: out_sym}]

        return pdcf_list

    def _compute_pdc(self, gate, d_input_node, d_val):
        gate_type = gate.type
        good   = 1 if d_val == 'D' else 0
        faulty = 1 - good

        if gate_type in ('NOT', 'BUF', 'WIRE'):
            good_out   = self._eval_binary_gate(gate_type, [good])
            faulty_out = self._eval_binary_gate(gate_type, [faulty])
            if good_out is None or faulty_out is None:
                return None
            out_sym = self._pair_to_logic(good_out, faulty_out)
            if out_sym not in ('D', 'D_bar'):
                return None
            return {d_input_node: d_val, gate: out_sym}

        nc_val = _NON_CONTROLLING_VAL.get(gate_type)
        if nc_val is None:
            return None
        nc_num = int(nc_val)

        good_inputs   = []
        faulty_inputs = []
        for inp in gate.fanins:
            if inp is d_input_node:
                good_inputs.append(good)
                faulty_inputs.append(faulty)
            else:
                good_inputs.append(nc_num)
                faulty_inputs.append(nc_num)

        good_out   = self._eval_binary_gate(gate_type, good_inputs)
        faulty_out = self._eval_binary_gate(gate_type, faulty_inputs)
        if good_out is None or faulty_out is None:
            return None
        out_sym = self._pair_to_logic(good_out, faulty_out)
        if out_sym not in ('D', 'D_bar'):
            return None 

        cube = {}
        for inp in gate.fanins:
            if inp is d_input_node:
                cube[inp] = d_val
            else:
                cube[inp] = nc_val
        cube[gate] = out_sym
        return cube

    def _compute_path_lengths(self, start_node):
        distances = {}
        queue = deque()
        queue.append((start_node, 0))
        visited = set()
        while queue:
            node, hops = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            if node.role == 'PO' or node in self.circuit.POs:
                distances[node] = hops
            for fo in getattr(node, 'fanouts', []):
                if fo not in visited:
                    queue.append((fo, hops + 1))
        return distances

    def _get_sc_justification_choices(self, gate):
        target  = gate.value 
        fanins  = gate.fanins
        n       = len(fanins)
        x_fanins = [fanins[i] for i in range(n) if fanins[i].value == 'X']

        if not x_fanins:
            return [{}]

        sc_rows      = _get_sc(gate.type, n)
        matching     = [r for r in sc_rows if r['output'] == target]

        if not matching:
            return [] 

        choices = []

        if gate.type in ('AND', 'NAND', 'OR', 'NOR'):
            ctrl_rows = [r for r in matching
                         if sum(1 for v in r['inputs'] if v != 'X') == 1]

            if ctrl_rows:
                ctrl_val = next(v for v in ctrl_rows[0]['inputs'] if v != 'X')
                for fi in x_fanins:
                    choices.append({fi: ctrl_val})

            nc_row = next(
                (r for r in matching if all(v != 'X' for v in r['inputs'])),
                None
            )
            if nc_row:
                nc_val = nc_row['inputs'][0] 
                d_good = {'D': '1', 'D_bar': '0'}
                d_bar_compatible = all(
                    d_good[fi.value] == nc_val
                    for fi in fanins if fi.value in ('D', 'D_bar')
                )
                if d_bar_compatible:
                    choices.append({fi: nc_val for fi in x_fanins})

        else:
            for row in matching:
                choice = {}
                valid  = True
                for fi, v in zip(fanins, row['inputs']):
                    if fi.value == 'X':
                        choice[fi] = v
                    elif fi.value not in ('D', 'D_bar') and fi.value != v:
                        valid = False
                        break
                    elif fi.value in ('D', 'D_bar'):
                        good_component = '1' if fi.value == 'D' else '0'
                        if good_component != v:
                            valid = False
                            break
                if valid:  
                    choices.append(choice)

        return choices  

    def _get_d_frontier(self):
        frontier = []
        for node in self.circuit.nodes.values():
            if node.role in ('PI', 'CONST') or node.type in ('PI', 'WIRE', 'CONST'):
                continue
            if node.value == 'X':
                if any(inp.value in ('D', 'D_bar') for inp in node.fanins):
                    frontier.append(node)
        frontier.sort(
            key=lambda g: (self._po_distances.get(g, float('inf')), -g.level)
        )
        return frontier

    def _is_justified(self, node):
        if node.value in ('X', 'D', 'D_bar'):
            return True 

        in_vals = [inp.value for inp in node.fanins]
        if 'X' not in in_vals:
            return True 

        nc = self._non_controlling_value(node.type)
        simulated = [v if v != 'X' else nc for v in in_vals]
        if 'X' in simulated:
            return False 

        sim_good = []
        for v in simulated:
            g, _ = self._logic_to_pair(v)
            sim_good.append(g)

        sim_out   = self._eval_binary_gate(node.type, sim_good)
        logic_out = self._pair_to_logic(sim_out, sim_out)
        return logic_out == node.value

    def _get_j_frontier(self):
        frontier = []
        for node in self.circuit.nodes.values():
            if node.type in ('PI', 'WIRE', 'CONST') or node.role in ('PI', 'CONST'):
                continue
            if node.value in ('0', '1'):
                if not self._is_justified(node):
                    frontier.append(node)
        frontier.sort(key=lambda g: g.level)
        return frontier

    def _imply(self):
        sorted_nodes = self._sorted_nodes
        changed = True
        while changed:
            changed = False
            for node in sorted_nodes:

                if node.role not in ('PI', 'CONST'):
                    new_val = self._eval_gate_5val(node)
                    if new_val != 'X':
                        if node.value == 'X':
                            node.value = new_val
                            changed = True
                        elif node.value != new_val:
                            return False  

                if node.value not in ('0', '1'):
                    continue
                if node.type in ('PI', 'WIRE', 'CONST') or node.role in ('PI', 'CONST'):
                    continue

                target   = node.value
                n_fanins = len(node.fanins)

                if node.type == 'NOT':
                    req = self._invert_logic(target)
                    fi  = node.fanins[0]
                    if fi.value == 'X':
                        fi.value = req
                        changed = True
                    elif fi.value != req:
                        return False

                elif node.type in ('BUF', 'WIRE'):
                    fi = node.fanins[0]
                    if fi.value == 'X':
                        fi.value = target
                        changed = True
                    elif fi.value != target:
                        return False

                else:
                    sc_rows     = _get_sc(node.type, n_fanins)
                    match_rows  = [r for r in sc_rows if r['output'] == target]

                    if not match_rows:
                        return False

                    for i, fi in enumerate(node.fanins):
                        if fi.value != 'X':
                            continue
                        vals_i = set()
                        for row in match_rows:
                            if i < len(row['inputs']):
                                vals_i.add(row['inputs'][i])

                        if len(vals_i) == 1 and 'X' not in vals_i:
                            implied = vals_i.pop()
                            fi.value = implied
                            changed = True

                    any_consistent = False
                    for row in match_rows:
                        row_ok = True
                        for i, fi in enumerate(node.fanins):
                            if fi.value == 'X':
                                continue
                            row_val = row['inputs'][i] if i < len(row['inputs']) else 'X'
                            if row_val == 'X':
                                continue
                            if fi.value not in ('D', 'D_bar') and fi.value != row_val:
                                row_ok = False
                                break
                        if row_ok:
                            any_consistent = True
                            break
                    if not any_consistent:
                        return False

        return True

    def _d_alg_recur(self):
        if not self._imply():
            return False

        d_front      = self._get_d_frontier()
        j_front      = self._get_j_frontier()
        po_has_fault = any(po.value in ('D', 'D_bar') for po in self.circuit.POs)

        if po_has_fault:
            if not j_front:
                return True 

            gate    = j_front[0]
            choices = self._get_sc_justification_choices(gate)

            for choice in choices:
                state = self._save_state()
                self.backtrack_count += 1
                for node, val in choice.items():
                    node.value = val
                if self._d_alg_recur():
                    return True
                self._restore_state(state)
            return False

        if d_front:
            gate = d_front[0]

            for inp in gate.fanins:
                if inp.value not in ('D', 'D_bar'):
                    continue
                d_val = inp.value
                pdc   = self._compute_pdc(gate, inp, d_val)
                if pdc is None:
                    continue

                state = self._save_state()
                self.backtrack_count += 1
                conflict = False
                for node, val in pdc.items():
                    existing = node.value
                    if existing == 'X' or existing == val:
                        node.value = val
                    else:
                        merged = _d_intersect(existing, val)
                        if merged is None:
                            conflict = True
                            break
                        node.value = merged
                if not conflict and self._d_alg_recur():
                    return True
                self._restore_state(state)

            return False 

        return False

    def solve_fault(self, fault):
        self.active_fault   = fault
        self.backtrack_count = 0

        for node in self.circuit.nodes.values():
            if node.role == 'CONST':
                node.value = ('1' if "1'b1" in node.name.lower() else '0')
            else:
                node.value = 'X'

        pdcf_list = self._compute_pdcf_candidates(fault)

        detected = False
        for pdcf_cube in pdcf_list:
            for node in self.circuit.nodes.values():
                if node.role != 'CONST':
                    node.value = 'X'

            conflict = False
            for node, val in pdcf_cube.items():
                if val == 'X':
                    continue 
                existing = node.value
                if existing == 'X' or existing == val:
                    node.value = val
                else:
                    merged = _d_intersect(existing, val)
                    if merged is None:
                        conflict = True
                        break
                    node.value = merged
            if conflict:
                self.backtrack_count += 1
                continue 

            if self._d_alg_recur():
                detected = True
                break
            self.backtrack_count += 1 

        test_vector = {pi.name: self._to_good_logic(pi.value) for pi in self.circuit.PIs}
        po_values   = {po.name: po.value                      for po in self.circuit.POs}

        return {
            "fault":       f"{fault.node.name}/SA{fault.stuck_at}",
            "detected":    detected,
            "test_vector": test_vector if detected else {},
            "po_values":   po_values   if detected else {},
            "backtracks":  self.backtrack_count,
        }

    def _compute_all_po_distances(self):
        distances = {node: float('inf') for node in self.circuit.nodes.values()}
        queue     = deque()

        for po in self.circuit.POs:
            distances[po] = 0
            queue.append(po)

        while queue:
            node      = queue.popleft()
            next_dist = distances[node] + 1
            for fi in node.fanins:
                if next_dist < distances[fi]:
                    distances[fi] = next_dist
                    queue.append(fi)

        return distances

    def run(self):
        all_faults = generate_faults(self.circuit)
        results    = []
        total_us   = 0.0

        for fault in all_faults:
            t0          = perf_counter()
            row         = self.solve_fault(fault)
            elapsed_us  = (perf_counter() - t0) * 1_000_000
            total_us   += elapsed_us
            row["elapsed_us"] = elapsed_us
            results.append(row)

        fault_count      = len(all_faults)
        avg_us           = (total_us / fault_count) if fault_count else 0.0
        detected_faults  = sum(1 for r in results if r.get("detected", False))
        coverage_pct     = (detected_faults * 100.0 / fault_count) if fault_count else 0.0
        total_backtracks = sum(r.get("backtracks", 0) for r in results)
        avg_backtracks   = (total_backtracks / fault_count) if fault_count else 0.0

        return {
            "algorithm":              "D",
            "status":                 "ok",
            "fault_count":            fault_count,
            "detected_faults":        detected_faults,
            "undetected_faults":      fault_count - detected_faults,
            "fault_coverage_pct":     coverage_pct,
            "total_backtracks":       total_backtracks,
            "avg_backtracks_per_fault": avg_backtracks,
            "total_time_ms":          total_us / 1000.0,
            "avg_time_per_fault_us":  avg_us,
            "results":                results,
        }


def run_d_algorithm_on_file(netlist_path):
    circuit = parse_netlist(netlist_path)
    levelize(circuit)
    engine  = DAlgorithmEngine(circuit)
    return engine.run()