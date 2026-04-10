from time import perf_counter
from collections import deque

from netlist_graph import (
    generate_faults,
    levelize,
    parse_netlist,
)


class PODEMEngine:
    def __init__(self, circuit, use_heuristics=True):
        self.circuit = circuit
        self.use_heuristics = use_heuristics
        self.active_fault = None
        self.v_fault = None
        self.d_frontier = []
        self._cc_cache = {}
        self._dist_to_po = self._compute_dist_to_po()
        self._visited_states = set()
        self.backtrack_count = 0

    @staticmethod
    def _invert_logic(v):
        inv = {
            '0': '1',
            '1': '0',
            'D': 'D_bar',
            'D_bar': 'D',
            'X': 'X',
        }
        return inv.get(v, 'X')

    @staticmethod
    def _logic_to_pair(v):
        mapping = {
            '0': (0, 0),
            '1': (1, 1),
            'D': (1, 0),
            'D_bar': (0, 1),
            'X': (None, None),
        }
        return mapping.get(v, (None, None))

    @staticmethod
    def _pair_to_logic(good, faulty):
        if good is None or faulty is None:
            return 'X'
        if good == 0 and faulty == 0:
            return '0'
        if good == 1 and faulty == 1:
            return '1'
        if good == 1 and faulty == 0:
            return 'D'
        if good == 0 and faulty == 1:
            return 'D_bar'
        return 'X'

    @staticmethod
    def _to_good_logic(v):
        if v == 'D':
            return '1'
        if v == 'D_bar':
            return '0'
        return v

    @staticmethod
    def _inv_binary(v):
        return None if v is None else 1 - v

    @staticmethod
    def _eval_and(vals):
        if 0 in vals:
            return 0
        if None in vals:
            return None
        return 1

    @staticmethod
    def _eval_or(vals):
        if 1 in vals:
            return 1
        if None in vals:
            return None
        return 0

    @staticmethod
    def _eval_not(vals):
        if not vals or vals[0] is None:
            return None
        return 1 - vals[0]

    @staticmethod
    def _eval_buf(vals):
        if not vals:
            return None
        return vals[0]

    @staticmethod
    def _eval_xor(vals):
        if None in vals:
            return None
        ones = sum(vals)
        return 1 if (ones % 2) else 0

    @staticmethod
    def _eval_binary_gate(gate_type, vals):
        handlers = {
            'AND': PODEMEngine._eval_and,
            'OR': PODEMEngine._eval_or,
            'NOT': PODEMEngine._eval_not,
            'BUF': PODEMEngine._eval_buf,
            'WIRE': PODEMEngine._eval_buf,
            'XOR': PODEMEngine._eval_xor,
            'XNOR': lambda v: PODEMEngine._inv_binary(PODEMEngine._eval_xor(v)),
            'NAND': lambda v: PODEMEngine._inv_binary(PODEMEngine._eval_and(v)),
            'NOR': lambda v: PODEMEngine._inv_binary(PODEMEngine._eval_or(v)),
        }
        handler = handlers.get(gate_type)
        if handler is not None:
            return handler(vals)
        if len(vals) == 1:
            return vals[0]
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

    def _refresh_d_frontier(self):
        frontier = []
        for node in self.circuit.nodes.values():
            if node.role == 'CONST' or node.type in ('PI', 'WIRE'):
                continue
            if node.value != 'X':
                continue
            in_vals = [inp.value for inp in node.fanins]
            if any(v in ('D', 'D_bar') for v in in_vals):
                frontier.append(node)
        self.d_frontier = frontier

    def _imply(self, pi_node, pi_val):
        activity_queue = deque()

        if pi_node.role == 'CONST':
            return

        assigned_value = self._inject_fault_effect(pi_node, pi_val)
        if pi_node.value != assigned_value:
            pi_node.value = assigned_value

        activity_queue.append(pi_node)

        while activity_queue:
            node = activity_queue.popleft()

            if node.role in ('PI', 'CONST'):
                for fanout in node.fanouts:
                    activity_queue.append(fanout)
                continue

            old_value = node.value
            new_value = self._eval_gate_5val(node)

            if new_value != old_value:
                node.value = new_value
                for fanout in node.fanouts:
                    activity_queue.append(fanout)

        self._refresh_d_frontier()

    def _compute_dist_to_po(self):
        dist = {node: float('inf') for node in self.circuit.nodes.values()}
        q = deque()

        for po in self.circuit.POs:
            dist[po] = 0
            q.append(po)

        while q:
            cur = q.popleft()
            for fin in cur.fanins:
                cand = dist[cur] + 1
                if cand < dist[fin]:
                    dist[fin] = cand
                    q.append(fin)

        return dist

    def _cc(self, node, val):
        key = (node, val)
        if key in self._cc_cache:
            return self._cc_cache[key]

        if node.role == 'PI':
            out = 1
        elif node.role == 'CONST':
            out = 0 if node.value == val else 10**6
        elif not node.fanins:
            out = 1
        else:
            c0 = [self._cc(inp, '0') for inp in node.fanins]
            c1 = [self._cc(inp, '1') for inp in node.fanins]
            cc0, cc1 = self._cc_for_gate_type(node.type, c0, c1)
            out = cc1 if val == '1' else cc0

        self._cc_cache[key] = out
        return out

    @staticmethod
    def _cc_for_gate_type(gate_type, c0, c1):
        if gate_type == 'AND':
            return 1 + min(c0), 1 + sum(c1)
        if gate_type == 'NAND':
            return 1 + sum(c1), 1 + min(c0)
        if gate_type == 'OR':
            return 1 + sum(c0), 1 + min(c1)
        if gate_type == 'NOR':
            return 1 + min(c1), 1 + sum(c0)
        if gate_type == 'NOT':
            return 1 + c1[0], 1 + c0[0]
        if gate_type in ('BUF', 'WIRE'):
            return 1 + c0[0], 1 + c1[0]
        if gate_type in ('XOR', 'XNOR'):
            base = 1 + sum(min(a, b) for a, b in zip(c0, c1))
            return base, base
        return 1 + min(c0), 1 + min(c1)

    @staticmethod
    def _non_controlling_value(gate_type):
        if gate_type in ('AND', 'NAND'):
            return '1'
        if gate_type in ('OR', 'NOR'):
            return '0'
        return 'X'

    def _objective(self, fault, v_fault):
        fval = fault.node.value
        if fval not in ('D', 'D_bar'):
            return (fault.node, v_fault)

        if not self.d_frontier:
            return None

        if self.use_heuristics:
            gate = min(self.d_frontier, key=lambda n: self._dist_to_po.get(n, float('inf')))
        else:
            gate = self.d_frontier[0]
        x_fanins = [n for n in gate.fanins if n.value == 'X']
        if not x_fanins:
            return None

        req = self._non_controlling_value(gate.type)
        if req == 'X':
            if self.use_heuristics:
                # XOR/XNOR has no strict non-controlling value; choose easier assignment.
                candidate = min(
                    x_fanins,
                    key=lambda n: min(self._cc(n, '0'), self._cc(n, '1')),
                )
                val = '0' if self._cc(candidate, '0') <= self._cc(candidate, '1') else '1'
            else:
                candidate = x_fanins[0]
                val = '0'
            return (candidate, val)

        if self.use_heuristics:
            target_input = min(x_fanins, key=lambda n: self._cc(n, req))
        else:
            target_input = x_fanins[0]
        return (target_input, req)

    def _choose_fanin_for_gate(self, node, internal_target):
        x_inputs = [fin for fin in node.fanins if fin.value == 'X']
        candidates = x_inputs if x_inputs else list(node.fanins)
        if not candidates:
            return None, internal_target

        if not self.use_heuristics:
            fin = candidates[0]
            g = node.type
            if g in ('AND', 'NAND'):
                return fin, '0' if internal_target == '0' else '1'
            if g in ('OR', 'NOR'):
                return fin, '1' if internal_target == '1' else '0'
            if g == 'NOT':
                return fin, self._invert_logic(internal_target)
            if g in ('BUF', 'WIRE'):
                return fin, internal_target
            if g in ('XOR', 'XNOR'):
                return fin, '0'
            return fin, internal_target

        g = node.type

        if g in ('AND', 'NAND'):
            if internal_target == '0':
                fin = min(candidates, key=lambda n: self._cc(n, '0'))
                return fin, '0'
            fin = max(candidates, key=lambda n: self._cc(n, '1'))
            return fin, '1'

        if g in ('OR', 'NOR'):
            if internal_target == '1':
                fin = min(candidates, key=lambda n: self._cc(n, '1'))
                return fin, '1'
            fin = max(candidates, key=lambda n: self._cc(n, '0'))
            return fin, '0'

        if g == 'NOT':
            return candidates[0], self._invert_logic(internal_target)

        if g in ('BUF', 'WIRE'):
            return candidates[0], internal_target

        if g in ('XOR', 'XNOR'):
            fin = min(candidates, key=lambda n: min(self._cc(n, '0'), self._cc(n, '1')))
            preferred = '0' if self._cc(fin, '0') <= self._cc(fin, '1') else '1'
            if g == 'XNOR':
                preferred = self._invert_logic(preferred)
            return fin, preferred

        fin = min(candidates, key=lambda n: self._cc(n, internal_target))
        return fin, internal_target

    def _backtrace(self, target_node, target_value):
        node = target_node
        val = target_value

        while node.role != 'PI':
            if not node.fanins:
                break

            internal_target = val
            if node.type in ('NAND', 'NOR', 'NOT'):
                internal_target = self._invert_logic(internal_target)

            next_node, next_val = self._choose_fanin_for_gate(node, internal_target)
            if next_node is None:
                break

            node = next_node
            val = next_val

        return node, val

    def _po_has_fault_effect(self):
        return any(po.value in ('D', 'D_bar') for po in self.circuit.POs)

    def _state_signature(self):
        # Include all node values to avoid revisiting identical logic states.
        return tuple(
            (node.name, node.value)
            for node in sorted(self.circuit.nodes.values(), key=lambda n: n.name)
        )

    def _podem_recur(self, fault, v_fault):
        sig = self._state_signature()
        if sig in self._visited_states:
            return False
        self._visited_states.add(sig)

        if self._po_has_fault_effect():
            return True

        if fault.node.value in ('D', 'D_bar') and not self.d_frontier:
            return False

        objective = self._objective(fault, v_fault)
        if objective is None:
            return False

        n, v = objective
        pi, pi_v = self._backtrace(n, v)
        if pi.role != 'PI':
            return False

        old_pi = pi.value

        # Try preferred assignment first, but skip if it cannot change state.
        if old_pi == 'X' or old_pi != pi_v:
            self._imply(pi, pi_v)
            if self._podem_recur(fault, v_fault):
                return True

        inv = self._invert_logic(pi_v)
        if old_pi == 'X' or old_pi != inv:
            self.backtrack_count += 1
            self._imply(pi, inv)
            if self._podem_recur(fault, v_fault):
                return True

        self._imply(pi, 'X')
        return False

    def solve_fault(self, fault):
        self.active_fault = fault
        self.v_fault = '1' if fault.stuck_at == 0 else '0'
        self._cc_cache = {}
        self._visited_states = set()
        self.backtrack_count = 0

        for node in self.circuit.nodes.values():
            if node.role == 'CONST':
                node.value = '1' if node.name.strip().lower() == "1'b1" else '0'
            else:
                node.value = 'X'

        self._refresh_d_frontier()
        detected = self._podem_recur(fault, self.v_fault)

        test_vector = {pi.name: self._to_good_logic(pi.value) for pi in self.circuit.PIs}
        po_values = {po.name: po.value for po in self.circuit.POs}

        return {
            "fault": f"{fault.node.name}/SA{fault.stuck_at}",
            "detected": detected,
            "test_vector": test_vector,
            "po_values": po_values,
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
            "algorithm": "PODEM",
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


def run_podem_on_file(netlist_path):
    circuit = parse_netlist(netlist_path)
    levelize(circuit)
    engine = PODEMEngine(circuit)
    return engine.run()