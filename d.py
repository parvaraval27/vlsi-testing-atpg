from time import perf_counter

from collections import deque
from netlist_graph import (
    generate_faults,
    levelize,
    parse_netlist,
)


class DAlgorithmEngine:
    def __init__(self, circuit):
        self.circuit = circuit
        self.active_fault = None
        self.backtrack_count = 0

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
        if v == 'D': return '1'
        if v == 'D_bar': return '0'
        return v

    @staticmethod
    def _eval_and(vals):
        if 0 in vals: return 0
        if None in vals: return None
        return 1

    @staticmethod
    def _eval_or(vals):
        if 1 in vals: return 1
        if None in vals: return None
        return 0

    @staticmethod
    def _eval_xor(vals):
        if None in vals: return None
        ones = sum(vals)
        return 1 if (ones % 2) else 0

    def _eval_binary_gate(self, gate_type, vals):
        handlers = {
            'AND': self._eval_and,
            'OR': self._eval_or,
            'NOT': lambda v: None if not v or v[0] is None else 1 - v[0],
            'BUF': lambda v: None if not v else v[0],
            'WIRE': lambda v: None if not v else v[0],
            'XOR': self._eval_xor,
            'XNOR': lambda v: None if self._eval_xor(v) is None else 1 - self._eval_xor(v),
            'NAND': lambda v: None if self._eval_and(v) is None else 1 - self._eval_and(v),
            'NOR': lambda v: None if self._eval_or(v) is None else 1 - self._eval_or(v),
        }
        handler = handlers.get(gate_type)
        if handler is not None:
            return handler(vals)
        if len(vals) == 1:
            return vals
        return None

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

        good_vals = []
        faulty_vals = []
        for v in vals:
            g, f = self._logic_to_pair(v)
            good_vals.append(g)
            faulty_vals.append(f)

        good_out = self._eval_binary_gate(node.type, good_vals)
        faulty_out = self._eval_binary_gate(node.type, faulty_vals)
        logic_out = self._pair_to_logic(good_out, faulty_out)
        return self._inject_fault_effect(node, logic_out)

    def _non_controlling_value(self, gate_type):
        if gate_type in ('AND', 'NAND'): return '1'
        if gate_type in ('OR', 'NOR'): return '0'
        return 'X'  # XOR/XNOR lack absolute non-controlling definitions

    def _get_d_frontier(self):
        frontier = []
        for node in self.circuit.nodes.values():
            if node.role == 'CONST' or node.type in ('PI', 'WIRE'):
                continue
            if node.value == 'X':
                in_vals = [inp.value for inp in node.fanins]
                if any(v in ('D', 'D_bar') for v in in_vals):
                    frontier.append(node)
        # Sort by level (highest first) to accelerate fault delivery to POs
        return sorted(frontier, key=lambda n: n.level, reverse=True)

    def _is_justified(self, node):
        if node.value in ('X', 'D', 'D_bar'):
            return True # Fault injection naturally forces D states
            
        in_vals = [inp.value for inp in node.fanins]
        if 'X' not in in_vals:
            return True # Fully specified inputs are self-justifying

        # Simulate worst-case scenario: map all unknowns to non-controlling values
        simulated_vals = [v if v != 'X' else self._non_controlling_value(node.type) for v in in_vals]
        if 'X' in simulated_vals:
            return False # XOR/XNOR gates with unknowns cannot be guaranteed
            
        sim_good = []
        for v in simulated_vals:
            g, _ = self._logic_to_pair(v)
            sim_good.append(g)
            
        sim_out = self._eval_binary_gate(node.type, sim_good)
        logic_out = self._pair_to_logic(sim_out, sim_out)
        
        return logic_out == node.value

    def _get_j_frontier(self):
        frontier = []
        for node in self.circuit.nodes.values():
            if node.type in ('PI', 'WIRE', 'CONST'):
                continue
            if node.value in ('0', '1'):
                if not self._is_justified(node):
                    frontier.append(node)
        # Sort by level (lowest first) to force justification towards Primary Inputs
        return sorted(frontier, key=lambda n: n.level)

    def _imply(self):
        changed = True
        while changed:
            changed = False
            for node in sorted(self.circuit.nodes.values(), key=lambda n: n.level):
                # Phase 1: Forward Implication
                if node.role not in ('PI', 'CONST'):
                    new_val = self._eval_gate_5val(node)
                    if new_val != 'X':
                        if node.value == 'X':
                            node.value = new_val
                            changed = True
                        elif node.value != new_val:
                            return False # Structural D-intersection conflict

                # Phase 2: Deterministic Backward Implication
                if node.value != 'X' and node.type not in ('PI', 'WIRE', 'CONST'):
                    target = node.value
                    if node.type == 'NOT':
                        req = self._invert_logic(target)
                        if node.fanins[0].value == 'X':
                            node.fanins[0].value = req
                            changed = True
                        elif node.fanins[0].value != req:
                            return False
                    elif node.type == 'BUF':
                        if node.fanins[0].value == 'X':
                            node.fanins[0].value = target
                            changed = True
                        elif node.fanins[0].value != target:
                            return False
                    elif self._gate_req_all_inputs(node.type, target):
                        req_val = '1' if node.type in ('AND', 'NAND') else '0'
                        if target in ('0', 'D_bar') and node.type in ('NAND', 'NOR'):
                            req_val = '1' if node.type == 'NAND' else '0'
                        for inp in node.fanins:
                            if inp.value == 'X':
                                inp.value = req_val
                                changed = True
                            elif inp.value != req_val and inp.value not in ('D', 'D_bar'):
                                return False
        return True

    def _gate_req_all_inputs(self, gate_type, target_val):
        if gate_type == 'AND' and target_val == '1': return True
        if gate_type == 'NAND' and target_val == '0': return True
        if gate_type == 'OR' and target_val == '0': return True
        if gate_type == 'NOR' and target_val == '1': return True
        return False

    def _save_state(self):
        return {n.name: n.value for n in self.circuit.nodes.values()}

    def _restore_state(self, state):
        for n in self.circuit.nodes.values():
            n.value = state[n.name]

    def _get_all_justification_choices(self, gate):
        x_inputs = [inp for inp in gate.fanins if inp.value == 'X']

        if not x_inputs:
            return []

        if len(x_inputs) > 2:
            return [
                {inp: '0' for inp in x_inputs},
                {inp: '1' for inp in x_inputs}
            ]

        from itertools import product

        choices = []
        for comb in product(['0', '1'], repeat=len(x_inputs)):
            assignment = {}
            for i, inp in enumerate(x_inputs):
                assignment[inp] = comb[i]
            choices.append(assignment)

        return choices

    def _propagate_through_gate(self, gate):
        nc_val = self._non_controlling_value(gate.type)

        if nc_val != 'X':
            for inp in gate.fanins:
                if inp.value == 'X':
                    inp.value = nc_val
            return [{}]

        x_inputs = [inp for inp in gate.fanins if inp.value == 'X']

        branches = []
        for v in ('0', '1'):
            assignment = {}
            for inp in x_inputs:
                assignment[inp] = v
            branches.append(assignment)

        return branches

    def _d_alg_recur(self):
        if not self._imply():
            return False

        if any(po.value in ('D', 'D_bar') for po in self.circuit.POs):

            j_front = self._get_j_frontier()

            if not j_front:
                return True

            gate = j_front[0]
            choices = self._get_all_justification_choices(gate)

            for choice in choices:
                state = self._save_state()
                self.backtrack_count += 1

                for node, val in choice.items():
                    node.value = val

                if self._d_alg_recur():
                    return True

                self._restore_state(state)

            return False

        d_front = self._get_d_frontier()

        if not d_front:
            return False
        gate = d_front[0]

        branches = self._propagate_through_gate(gate)

        for branch in branches:
            state = self._save_state()
            self.backtrack_count += 1

            if isinstance(branch, dict):
                for node, val in branch.items():
                    node.value = val

            if self._d_alg_recur():
                return True

            self._restore_state(state)

        return False

    def solve_fault(self, fault):
    
        self.active_fault = fault
        self.backtrack_count = 0

        for node in self.circuit.nodes.values():
            if node.role == 'CONST':
                node.value = '1' if node.name.strip().lower() == "1'b1" else '0'
            else:
                node.value = 'X'

        pdcf_val = 'D' if fault.stuck_at == 0 else 'D_bar'
        fault.node.value = pdcf_val

        detected = self._d_alg_recur()

        test_vector = {pi.name: self._to_good_logic(pi.value) for pi in self.circuit.PIs}
        po_values = {po.name: po.value for po in self.circuit.POs}

        return {
            "fault": f"{fault.node.name}/SA{fault.stuck_at}",
            "detected": detected,
            "test_vector": test_vector if detected else {},
            "po_values": po_values if detected else {},
            "backtracks": self.backtrack_count,
        }

    def run(self):
        all_faults = generate_faults(self.circuit)
        results = []
        total_us = 0.0

        for fault in all_faults:
            t0 = perf_counter()
            row = self.solve_fault(fault)
            elapsed_us = (perf_counter() - t0) * 1_000_000
            total_us += elapsed_us
            row["elapsed_us"] = elapsed_us
            results.append(row)

        fault_count = len(all_faults)
        avg_us = (total_us / fault_count) if fault_count else 0.0
        detected_faults = sum(1 for row in results if row.get("detected", False))
        coverage_pct = (detected_faults * 100.0 / fault_count) if fault_count else 0.0
        total_backtracks = sum(row.get("backtracks", 0) for row in results)
        avg_backtracks = (total_backtracks / fault_count) if fault_count else 0.0

        return {
            "algorithm": "D",
            "status": "ok",
            "fault_count": fault_count,
            "detected_faults": detected_faults,
            "undetected_faults": fault_count - detected_faults,
            "fault_coverage_pct": coverage_pct,
            "total_backtracks": total_backtracks,
            "avg_backtracks_per_fault": avg_backtracks,
            "total_time_ms": total_us / 1000.0,
            "avg_time_per_fault_us": avg_us,
            "results": results,
        }


def run_d_algorithm_on_file(netlist_path):
    circuit = parse_netlist(netlist_path)
    levelize(circuit)
    engine = DAlgorithmEngine(circuit)
    return engine.run()
