from time import perf_counter
from collections import deque
from itertools import product

from netlist_graph import (
    generate_faults,
    levelize,
    parse_netlist,
)

# ═══════════════════════════════════════════════════════════════════
# PART 1 — 5-VALUED LOGIC: TWO DISTINCT INTERSECTION OPERATIONS
# ═══════════════════════════════════════════════════════════════════

# ── Table 1: D-Algebra Intersection ─────────────────────────────────
# Non-commutative.  Left = good-circuit value, Right = faulty-circuit value.
# Produces D / D_bar symbols when the two circuits disagree.
# Used ONLY during PDCF and PDC construction from SC rows.
#
#   good \ faulty |  '0'     '1'     'X'
#   ──────────────┼───────────────────────
#       '0'       |  '0'    'D_bar'  '0'
#       '1'       |  'D'    '1'      '1'
#       'X'       |  '0'    '1'      'X'
#
D_ALGEBRA = {
    '0': {'0': '0',     '1': 'D_bar', 'X': '0'},
    '1': {'0': 'D',     '1': '1',     'X': '1'},
    'X': {'0': '0',     '1': '1',     'X': 'X'},
}


def _d_algebra_intersect(good_val, faulty_val):
    """
    D-Algebra intersection (TABLE 1).
    Left operand  = good-circuit SC value.
    Right operand = faulty-circuit SC value.
    Returns the 5-valued symbol, or None if undefined for those inputs.
    Non-commutative: _d_algebra_intersect('1','0') = 'D'
                     _d_algebra_intersect('0','1') = 'D_bar'
    """
    row = D_ALGEBRA.get(good_val)
    if row is None:
        return None
    return row.get(faulty_val)


# ── Table 2: Test-Cube Intersection ─────────────────────────────────
# Commutative.  φ (conflict) represented as None.
# Used to merge successive test cubes during D-drive and justification.
#
#         |  '0'    '1'    'X'    'D'    'D_bar'
#   ──────┼──────────────────────────────────────
#   '0'   |  '0'     φ     '0'    φ       φ
#   '1'   |   φ     '1'    '1'    φ       φ
#   'X'   |  '0'    '1'    'X'   'D'    'D_bar'
#   'D'   |   φ      φ     'D'   'D'      φ
#  'D_bar'|   φ      φ   'D_bar'  φ    'D_bar'
#
D_INTERSECTION = {
    '0':     {'0': '0',     '1': None,    'X': '0',     'D': None,    'D_bar': None    },
    '1':     {'0': None,    '1': '1',     'X': '1',     'D': None,    'D_bar': None    },
    'X':     {'0': '0',     '1': '1',     'X': 'X',     'D': 'D',     'D_bar': 'D_bar' },
    'D':     {'0': None,    '1': None,    'X': 'D',     'D': 'D',     'D_bar': None    },
    'D_bar': {'0': None,    '1': None,    'X': 'D_bar', 'D': None,    'D_bar': 'D_bar' },
}


def _d_intersect(v1, v2):
    """
    Test-Cube intersection (TABLE 2).
    Commutative. Returns None on conflict (φ).
    Used to merge test cubes: TC(n) ∩ new_cube → TC(n+1).
    """
    return D_INTERSECTION[v1][v2]


def _intersect_cubes(cube_a, cube_b):
    """
    Intersect two cubes entry by entry using _d_intersect.
    Return None if any position produces φ.
    Positions present in one cube but not the other take the value
    from the cube that specifies them (X is identity element).
    """
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


# ═══════════════════════════════════════════════════════════════════
# PART 2 — SINGULAR COVER (SC) TABLES
# ═══════════════════════════════════════════════════════════════════

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

# Controlling values for each gate type (input side)
_CONTROLLING_VAL = {
    'AND': '0', 'NAND': '0',
    'OR':  '1', 'NOR':  '1',
}
# Non-controlling values for each gate type (input side)
_NON_CONTROLLING_VAL = {
    'AND': '1', 'NAND': '1',
    'OR':  '0', 'NOR':  '0',
    'XOR': '0', 'XNOR': '0',  # '0' = transparent for XOR/XNOR
}


def _get_sc(gate_type, fanin_count):
    """
    Return the Singular Cover for a gate of the given type and fanin count.
    Each row: {'inputs': [...], 'output': '0'|'1'}
    For 2-input gates the canonical table is used directly.
    For n>2 input AND/NAND/OR/NOR, rows are generated programmatically.
    For n-input XOR/XNOR, all 2^n input combinations are enumerated.
    """
    # 1-input gates: NOT, BUF, WIRE
    if gate_type in ('NOT', 'BUF', 'WIRE'):
        return SINGULAR_COVER[gate_type]

    # 2-input: return canonical table directly
    if fanin_count == 2:
        return SINGULAR_COVER.get(gate_type, [])

    # n-input AND / NAND / OR / NOR
    if gate_type in ('AND', 'NAND', 'OR', 'NOR'):
        ctrl = _CONTROLLING_VAL[gate_type]
        nc   = _NON_CONTROLLING_VAL[gate_type]

        # Output values: AND ctrl-output='0' nc-output='1';
        #                OR  ctrl-output='1' nc-output='0';
        #                NAND ctrl-output='1' nc-output='0';
        #                NOR  ctrl-output='0' nc-output='1'
        if gate_type == 'AND':
            ctrl_out, nc_out = '0', '1'
        elif gate_type == 'OR':
            ctrl_out, nc_out = '1', '0'
        elif gate_type == 'NAND':
            ctrl_out, nc_out = '1', '0'
        else:  # NOR
            ctrl_out, nc_out = '0', '1'

        rows = []
        # Controlling rows: one per input position
        for i in range(fanin_count):
            inp = ['X'] * fanin_count
            inp[i] = ctrl
            rows.append({'inputs': inp, 'output': ctrl_out})
        # Non-controlling row: all inputs at nc value
        rows.append({'inputs': [nc] * fanin_count, 'output': nc_out})
        return rows

    # n-input XOR / XNOR: enumerate all binary combinations
    if gate_type in ('XOR', 'XNOR'):
        rows = []
        for combo in product(['0', '1'], repeat=fanin_count):
            ones = sum(int(v) for v in combo)
            xor_out = '1' if (ones % 2 == 1) else '0'
            out = xor_out if gate_type == 'XOR' else ('0' if xor_out == '1' else '1')
            rows.append({'inputs': list(combo), 'output': out})
        return rows

    return []


# ═══════════════════════════════════════════════════════════════════
# MAIN ENGINE CLASS
# ═══════════════════════════════════════════════════════════════════

class DAlgorithmEngine:
    def __init__(self, circuit):
        self.circuit = circuit
        self.active_fault = None
        self.backtrack_count = 0
        # Perf: compute PO distances once — circuit topology never changes.
        self._po_distances = self._compute_all_po_distances()
        # Perf: cache level-order node list once — levels are fixed after levelize().
        # _imply() is called thousands of times across all faults; rebuilding
        # sorted() each call wastes O(n log n) work on an unchanging ordering.
        self._sorted_nodes = sorted(circuit.nodes.values(), key=lambda n: n.level)

    # ── Preserved static helpers ────────────────────────────────────

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
        return 'X'  # XOR/XNOR lack absolute non-controlling definitions


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

    # ── State save / restore ─────────────────────────────────────────

    def _save_state(self):
        return {n.name: n.value for n in self.circuit.nodes.values()}

    def _restore_state(self, state):
        for n in self.circuit.nodes.values():
            n.value = state[n.name]

    # ═══════════════════════════════════════════════════════════════
    # PART 3 — PDCF (PRIMITIVE D-CUBE OF FAULT)
    # ═══════════════════════════════════════════════════════════════

    def _compute_pdcf_candidates(self, fault):
        """
        Derive PDCF cubes using the D-Algebra Intersection (TABLE 1).

        Method (Roth 1966):
          1. SC of good circuit  -> keep rows where output = good_output (1-stuck_at)
          2. SC of faulty circuit -> one row: inputs all X, output = stuck_at value
          3. For each good-SC row, D-Algebra intersect position by position:
               D_ALGEBRA[good_val][faulty_val]  ->  5-valued symbol
             NON-COMMUTATIVE: good on left, faulty on right.
               1 intersect 0 = D      (good=1, faulty=0)
               0 intersect 1 = D_bar  (good=0, faulty=1)
               X intersect v = v,  v intersect X = v
          The D/D_bar at the output emerges from the intersection itself,
          not from a hard-coded assignment.
        """
        stuck_val   = str(fault.stuck_at)
        good_output = str(1 - fault.stuck_at)

        # Faulty-circuit SC: one row, inputs all X, output = stuck value
        faulty_inputs = ['X'] * max(1, len(fault.node.fanins))

        # Primary-input fault: no gate SC, return trivial cube directly
        if fault.node.role == 'PI' or not fault.node.fanins:
            out_sym = _d_algebra_intersect(good_output, stuck_val)
            return [{fault.node: out_sym}]

        gate_type   = fault.node.type
        fanin_count = len(fault.node.fanins)
        sc_rows     = _get_sc(gate_type, fanin_count)

        # Good-circuit SC rows producing the non-stuck output
        good_rows = [r for r in sc_rows if r['output'] == good_output]

        pdcf_list = []
        for good_row in good_rows:
            cube     = {}
            conflict = False

            # D-Algebra intersect at each input position (good intersect faulty)
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

            # D-Algebra intersect at output position -> produces D or D_bar
            out_sym = _d_algebra_intersect(good_output, stuck_val)
            if out_sym is None:
                continue
            cube[fault.node] = out_sym
            pdcf_list.append(cube)

        # Fallback: SC produced nothing, inject symbol directly
        if not pdcf_list:
            out_sym = _d_algebra_intersect(good_output, stuck_val)
            pdcf_list = [{fault.node: out_sym}]

        return pdcf_list

    # ═══════════════════════════════════════════════════════════════
    # PART 4 — PDC (PROPAGATION D-CUBE)
    # ═══════════════════════════════════════════════════════════════

    def _compute_pdc(self, gate, d_input_node, d_val):
        """
        Compute the PDC cube using D-Algebra Intersection (TABLE 1).

        Conceptually this intersects two SC rows of the same gate:
          - Row A (good circuit):   sensitized input = good_val,  others = nc_val
          - Row B (faulty circuit): sensitized input = faulty_val, others = nc_val
        D-Algebra intersect A ∩ B position by position:
          sensitized input  -> D or D_bar  (good != faulty)
          non-sensitized    -> nc_val ∩ nc_val = nc_val  (unchanged)
          output            -> D or D_bar  (if gate propagates the discrepancy)

        Returns a cube dict {node: value} for all fanin nodes + gate output,
        or None if propagation is impossible (output does not become D/D_bar).
        """
        gate_type = gate.type
        good   = 1 if d_val == 'D' else 0
        faulty = 1 - good

        # 1-input gates (NOT, BUF, WIRE) — only one fanin, which IS d_input_node
        if gate_type in ('NOT', 'BUF', 'WIRE'):
            good_out   = self._eval_binary_gate(gate_type, [good])
            faulty_out = self._eval_binary_gate(gate_type, [faulty])
            if good_out is None or faulty_out is None:
                return None
            out_sym = self._pair_to_logic(good_out, faulty_out)
            if out_sym not in ('D', 'D_bar'):
                return None
            return {d_input_node: d_val, gate: out_sym}

        # Multi-input gates
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
            return None  # no error signal at output — propagation blocked

        # Build PDC cube
        cube = {}
        for inp in gate.fanins:
            if inp is d_input_node:
                cube[inp] = d_val
            else:
                cube[inp] = nc_val
        cube[gate] = out_sym
        return cube

    # ═══════════════════════════════════════════════════════════════
    # PART 5 — SHORTEST-PATH PO SELECTION
    # ═══════════════════════════════════════════════════════════════

    def _compute_path_lengths(self, start_node):
        """
        BFS from start_node forward through fanouts.
        Returns {po_node: hop_count} for all reachable POs.
        """
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


    # ═══════════════════════════════════════════════════════════════
    # PART 6 — SC-GUIDED JUSTIFICATION CHOICES
    # ═══════════════════════════════════════════════════════════════

    def _get_sc_justification_choices(self, gate):
        """
        Use the gate's SC table to generate minimal input assignments
        that justify gate.value.

        For gate.value == '0':
          - AND/NAND/OR/NOR controlling case: one choice per X-fanin
            setting just THAT fanin to the controlling value.
          - AND/NAND/OR/NOR non-controlling case: one choice sets ALL
            X fanins to the non-controlling value.
          - XOR/XNOR: enumerate matching SC rows.

        For gate.value == '1': symmetric, derived from SC.

        Never enumerate 2^n combinations — always derive from SC rows.
        Returns a list of partial assignment dicts {node: value}.
        """
        target  = gate.value  # '0' or '1'
        fanins  = gate.fanins
        n       = len(fanins)
        x_fanins = [fanins[i] for i in range(n) if fanins[i].value == 'X']

        if not x_fanins:
            return [{}]

        sc_rows      = _get_sc(gate.type, n)
        matching     = [r for r in sc_rows if r['output'] == target]

        if not matching:
            return []  # no SC row produces this output — hard conflict, let caller backtrack

        choices = []

        if gate.type in ('AND', 'NAND', 'OR', 'NOR'):
            # Identify whether we're in the controlling or non-controlling case
            # Controlling rows have exactly one non-X input position
            ctrl_rows = [r for r in matching
                         if sum(1 for v in r['inputs'] if v != 'X') == 1]

            if ctrl_rows:
                # Bug 1 fix: Remove the already_controlled guard entirely.
                # It incorrectly suppresses ALL controlling choices when ANY
                # D/D_bar fanin happens to match ctrl_val in the good circuit.
                # Each X-fanin must be tried independently as a justification choice.
                ctrl_val = next(v for v in ctrl_rows[0]['inputs'] if v != 'X')
                for fi in x_fanins:
                    choices.append({fi: ctrl_val})

            # Bug 2 fix: Use a separate 'if', not 'else', so the non-controlling
            # case is checked independently even when controlling rows also exist.
            nc_row = next(
                (r for r in matching if all(v != 'X' for v in r['inputs'])),
                None
            )
            if nc_row:
                nc_val = nc_row['inputs'][0]  # all positions hold the same nc value
                # Verify every D/D_bar fanin is compatible with nc_val
                # by checking its good-circuit component.
                # 'D' → good='1', 'D_bar' → good='0'
                d_good = {'D': '1', 'D_bar': '0'}
                d_bar_compatible = all(
                    d_good[fi.value] == nc_val
                    for fi in fanins if fi.value in ('D', 'D_bar')
                )
                if d_bar_compatible:
                    choices.append({fi: nc_val for fi in x_fanins})
                # If any D/D_bar fanin is incompatible with nc_val in the good
                # circuit, this non-controlling choice is logically invalid —
                # suppress it so _imply never wastes a recursive call on it.

        else:
            # XOR / XNOR: enumerate every matching SC row
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
                        # Check good-circuit component compatibility
                        good_component = '1' if fi.value == 'D' else '0'
                        if good_component != v:
                            valid = False
                            break
                if valid:  # Bug 3 fix: don't require choice to be non-empty.
                    # An empty dict {} means all fanins already satisfy this SC row —
                    # "no new assignments needed" is a valid justification.
                    choices.append(choice)

        return choices  # empty list = no valid SC choice = caller must backtrack

    # ── Frontier helpers ─────────────────────────────────────────────

    def _get_d_frontier(self):
        """
        D-frontier: gates with output='X' and ≥1 input in {D, D_bar}.
        Sorted: ascending _po_distances[gate], break ties by descending level.
        """
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
        """
        A gate is 'justified' if its output value is already guaranteed by the
        current (possibly partial) fanin assignments.

        The key heuristic from d.py: substitute all X fanins with the gate's
        non-controlling value. If the simulated output still matches the required
        output, the gate is self-justified — no further implication needed.
        This prevents over-populating the J-frontier with gates that are actually
        already satisfied, which was causing incorrect conflict returns and missed
        fault detections.
        """
        if node.value in ('X', 'D', 'D_bar'):
            return True  # dynamically determined value — not a justification target

        in_vals = [inp.value for inp in node.fanins]
        if 'X' not in in_vals:
            return True  # fully specified — trivially justified

        # Substitute X fanins with the non-controlling value and simulate
        nc = self._non_controlling_value(node.type)
        simulated = [v if v != 'X' else nc for v in in_vals]
        if 'X' in simulated:
            return False  # XOR/XNOR has no meaningful non-controlling value

        sim_good = []
        for v in simulated:
            g, _ = self._logic_to_pair(v)
            sim_good.append(g)

        sim_out   = self._eval_binary_gate(node.type, sim_good)
        logic_out = self._pair_to_logic(sim_out, sim_out)
        return logic_out == node.value

    def _get_j_frontier(self):
        """
        J-frontier: gates with output in {'0','1'} that are NOT already justified.
        Uses _is_justified to exclude self-justified gates (gates whose output is
        guaranteed even with remaining X fanins). Sorted by ascending level
        (justify closest to PIs first).
        """
        frontier = []
        for node in self.circuit.nodes.values():
            if node.type in ('PI', 'WIRE', 'CONST') or node.role in ('PI', 'CONST'):
                continue
            if node.value in ('0', '1'):
                if not self._is_justified(node):
                    frontier.append(node)
        frontier.sort(key=lambda g: g.level)
        return frontier


    # ===============================================================
    # PART 7 -- REVISED _imply
    # ===============================================================

    def _imply(self):
        """
        Iterative forward + SC-guided backward implication.
        Returns False on any conflict, True otherwise.
        """
        # Use the engine-level cached sorted list -- node levels are fixed after
        # levelize(), so there is no need to rebuild this per _imply() call.
        sorted_nodes = self._sorted_nodes
        changed = True
        while changed:
            changed = False
            for node in sorted_nodes:

                # -- Phase 1: Forward Implication ----------------------
                if node.role not in ('PI', 'CONST'):
                    new_val = self._eval_gate_5val(node)
                    if new_val != 'X':
                        if node.value == 'X':
                            node.value = new_val
                            changed = True
                        elif node.value != new_val:
                            return False  # structural conflict

                # -- Phase 2: SC-Guided Backward Implication -----------
                # Only applies when the node has a concrete binary output
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
                    # SC-guided: find positions with a unique concrete value
                    # across ALL SC rows that match node.value
                    sc_rows     = _get_sc(node.type, n_fanins)
                    match_rows  = [r for r in sc_rows if r['output'] == target]

                    if not match_rows:
                        # No SC row can produce this output — hard conflict
                        return False

                    for i, fi in enumerate(node.fanins):
                        if fi.value != 'X':
                            continue
                        # Collect all values prescribed at position i
                        vals_i = set()
                        for row in match_rows:
                            if i < len(row['inputs']):
                                vals_i.add(row['inputs'][i])

                        # Deterministically implied only when ALL rows agree
                        # on a single concrete value (not 'X')
                        if len(vals_i) == 1 and 'X' not in vals_i:
                            implied = vals_i.pop()
                            fi.value = implied
                            changed = True

                    # Conflict check: if all current (non-X) fanin values are
                    # inconsistent with every matching SC row → conflict
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

    # ═══════════════════════════════════════════════════════════════
    # PART 6 — REVISED RECURSIVE SEARCH (_d_alg_recur)
    # ═══════════════════════════════════════════════════════════════

    def _d_alg_recur(self):
        """
        Recursive D-algorithm procedure (canonical Roth ordering):
          A — Implication (forward + SC-guided backward)
          B — Compute both frontiers and PO status
          C — PO reached: justify immediately (D-frontier state irrelevant)
          D — PO not yet reached: propagate through D-frontier
        """
        # Step A — Implication
        if not self._imply():
            return False

        # Step B — Compute both frontiers and PO status
        d_front      = self._get_d_frontier()
        j_front      = self._get_j_frontier()
        po_has_fault = any(po.value in ('D', 'D_bar') for po in self.circuit.POs)

        # Step C — If D is already observable at a PO, justify immediately.
        # This MUST come before the D-frontier check. When the fault signal
        # reaches a PO via one path, the fault IS detectable regardless of
        # whether other D-frontier gates exist on parallel paths. Trying to
        # propagate through those extra D-frontier gates first risks returning
        # False when propagation fails — even though the fault was already
        # detectable. This was the primary source of missed detections vs d.py,
        # which also checks PO reachability before the D-frontier.
        if po_has_fault:
            if not j_front:
                return True  # Fully justified — test found!

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

        # Step D — D not yet at any PO: propagate through the D-frontier.
        # We commit to the single best gate (d_front[0], sorted ascending by
        # PO distance so the closest-to-output gate is tried first).
        # Trying ALL gates in a flat loop causes N!-factorial branching across
        # recursion levels — for undetectable faults this turns ms into minutes.
        if d_front:
            gate = d_front[0]

            # Try each D/D_bar input of this gate as the sensitized input
            for inp in gate.fanins:
                if inp.value not in ('D', 'D_bar'):
                    continue
                d_val = inp.value
                pdc   = self._compute_pdc(gate, inp, d_val)
                if pdc is None:
                    continue

                state = self._save_state()
                self.backtrack_count += 1
                # Apply PDC cube with D-intersection conflict check
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

            return False  # no D-input of the chosen gate can propagate — dead end

        # D-frontier empty AND D not at any PO — dead end
        return False


    # ═══════════════════════════════════════════════════════════════
    # PART 8 — REVISED solve_fault
    # ═══════════════════════════════════════════════════════════════

    def solve_fault(self, fault):
        self.active_fault   = fault
        self.backtrack_count = 0

        # Reset all nodes to X (except constants)
        for node in self.circuit.nodes.values():
            if node.role == 'CONST':
                node.value = ('1' if "1'b1" in node.name.lower() else '0')
            else:
                node.value = 'X'

        # Compute PDCF candidates
        pdcf_list = self._compute_pdcf_candidates(fault)

        detected = False
        for pdcf_cube in pdcf_list:
            # Full state reset before each PDCF attempt
            for node in self.circuit.nodes.values():
                if node.role != 'CONST':
                    node.value = 'X'

            # Apply the PDCF cube using D-intersection for consistency with the
            # PDC apply loop. Skip 'X' entries — in a Roth cube 'X' means
            # don't-care (no constraint), so it must never be actively assigned.
            # The reset above already guarantees every node is 'X', so skipping
            # these entries is semantically correct and slightly faster.
            conflict = False
            for node, val in pdcf_cube.items():
                if val == 'X':
                    continue  # don't-care — leave node at its current 'X'
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
                continue  # this PDCF cube conflicts — try the next candidate

            if self._d_alg_recur():
                detected = True
                break
            self.backtrack_count += 1  # count PDCF-level backtrack

        test_vector = {pi.name: self._to_good_logic(pi.value) for pi in self.circuit.PIs}
        po_values   = {po.name: po.value                       for po in self.circuit.POs}

        return {
            "fault":       f"{fault.node.name}/SA{fault.stuck_at}",
            "detected":    detected,
            "test_vector": test_vector if detected else {},
            "po_values":   po_values   if detected else {},
            "backtracks":  self.backtrack_count,
        }

    def _compute_all_po_distances(self):
        """
        BFS backwards from each PO. For every node, compute the minimum
        number of gate hops to reach any PO through its fanout cone.
        Returns {node: min_hops}.
        Nodes with no path to any PO get distance = float('inf').
        """
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

    # ═══════════════════════════════════════════════════════════════
    # PART 8 — run() (unchanged interface)
    # ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
# MODULE-LEVEL ENTRY POINT (unchanged interface)
# ═══════════════════════════════════════════════════════════════════

def run_d_algorithm_on_file(netlist_path):
    circuit = parse_netlist(netlist_path)
    levelize(circuit)
    engine  = DAlgorithmEngine(circuit)
    return engine.run()