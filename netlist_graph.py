import os

class Node:
    def __init__(self, name, gate_type):
        self.name = name
        self.type = gate_type
        self.role = "INTERNAL"  # PI, PO, INTERNAL, CONST
        self.fanins = []
        self.fanouts = []
        self.value = 'X'  # 0, 1, X
        self.level = -1

class Circuit:
    def __init__(self):
        self.nodes = {}  # name -> Node
        self.PIs = []
        self.POs = []

class Fault:
    def __init__(self, node, stuck_at):
        self.node = node
        self.stuck_at = stuck_at  # 0 or 1

def get_or_create_node(circuit, name, gate_type="WIRE"):
    if name not in circuit.nodes:
        circuit.nodes[name] = Node(name, gate_type)
        if gate_type == "PI":
            circuit.nodes[name].role = "PI"
        elif gate_type == "PO":
            circuit.nodes[name].role = "PO"
            circuit.nodes[name].type = "WIRE"
    else:
        node = circuit.nodes[name]
        existing_type = node.type

        if gate_type == "PI":
            node.role = "PI"
            node.type = "PI"
        elif gate_type == "PO":
            node.role = "PO"
        elif gate_type not in ["WIRE", "PI", "PO"]:
            if existing_type == "WIRE":
                node.type = gate_type
    return circuit.nodes[name]


def apply_constant_literal(node):
    token = node.name.strip().lower()
    if token == "1'b0":
        node.role = "CONST"
        node.type = "CONST"
        node.value = '0'
        node.level = 0
    elif token == "1'b1":
        node.role = "CONST"
        node.type = "CONST"
        node.value = '1'
        node.level = 0


def parse_netlist(filename):
    circuit = Circuit()

    with open(filename, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()

            if "//" in line:
                line = line.split("//", 1)[0].strip()

            if not line or line.startswith("#"):
                continue

            if line.lower().startswith("input "):
                names = line[5:].strip().rstrip(";")
                for name in [n.strip() for n in names.split(",") if n.strip()]:
                    node = get_or_create_node(circuit, name, "PI")
                    if node not in circuit.PIs:
                        circuit.PIs.append(node)

            elif line.lower().startswith("output "):
                names = line[6:].strip().rstrip(";")
                for name in [n.strip() for n in names.split(",") if n.strip()]:
                    node = get_or_create_node(circuit, name, "PO")
                    if node not in circuit.POs:
                        circuit.POs.append(node)

            elif line.lower().startswith(("module", "wire", "endmodule")):
                continue

            else:
                stmt = line.rstrip(";")
                if "(" not in stmt or ")" not in stmt:
                    continue

                header = stmt[:stmt.find("(")].strip()
                body = stmt[stmt.find("(") + 1:stmt.rfind(")")]
                if not header:
                    continue

                gate_type = header.split()[0].upper()
                pins = [p.strip() for p in body.split(",") if p.strip()]
                if len(pins) < 2:
                    continue

                if gate_type in ["NOT", "BUF"] and len(pins) != 2:
                    continue

                out_name = pins[0]
                in_names = pins[1:]

                node = get_or_create_node(circuit, out_name, gate_type)

                for inp in in_names:
                    in_node = get_or_create_node(circuit, inp)
                    apply_constant_literal(in_node)
                    if in_node not in node.fanins:
                        node.fanins.append(in_node)
                    if node not in in_node.fanouts:
                        in_node.fanouts.append(node)
    
    return circuit


def parse_netlist_folder(folder_path):
    circuits = {}

    if not os.path.isdir(folder_path):
        return circuits

    for entry in sorted(os.listdir(folder_path)):
        full_path = os.path.join(folder_path, entry)
        if not os.path.isfile(full_path):
            continue

        if entry.lower().endswith((".txt")):
            circuits[entry] = parse_netlist(full_path)

    return circuits


def levelize(circuit):
    from collections import deque

    queue = deque()

    for node in circuit.nodes.values():
        node.level = -1

    for pi in circuit.PIs:
        pi.level = 0
        queue.append(pi)

    for node in circuit.nodes.values():
        if node.role == "CONST":
            node.level = 0
            queue.append(node)

    while queue:
        node = queue.popleft()

        for out in node.fanouts:
            if all(inp.level != -1 for inp in out.fanins):
                candidate_level = max(inp.level for inp in out.fanins) + 1
                if out.level == -1 or candidate_level > out.level:
                    out.level = candidate_level
                    queue.append(out)


def eval_gate_helper_AND(vals):
    if '0' in vals:
        return '0'
    if 'X' in vals:
        return 'X'
    return '1'


def eval_gate_helper_OR(vals):
    if '1' in vals:
        return '1'
    if 'X' in vals:
        return 'X'
    return '0'


def eval_gate(node):
    vals = [inp.value for inp in node.fanins]

    if node.type == "AND":
        if '0' in vals:
            return '0'
        if 'X' in vals:
            return 'X'
        return '1'

    elif node.type == "OR":
        if '1' in vals:
            return '1'
        if 'X' in vals:
            return 'X'
        return '0'

    elif node.type == "NOT":
        if not vals or vals[0] == 'X':
            return 'X'
        return '1' if vals[0] == '0' else '0'

    elif node.type == "NAND":
        and_val = eval_gate_helper_AND(vals)
        if and_val == 'X':
            return 'X'
        return '1' if and_val == '0' else '0'

    elif node.type == "NOR":
        or_val = eval_gate_helper_OR(vals)
        if or_val == 'X':
            return 'X'
        return '1' if or_val == '0' else '0'

    elif node.type == "BUF":
        if not vals:
            return 'X'
        return vals[0]

    elif node.type == "XOR":
        if 'X' in vals:
            return 'X'
        ones = sum(1 for v in vals if v == '1')
        return '1' if ones % 2 == 1 else '0'

    elif node.type == "XNOR":
        if 'X' in vals:
            return 'X'
        ones = sum(1 for v in vals if v == '1')
        return '0' if ones % 2 == 1 else '1'

    if len(vals) == 1:
        return vals[0]

    return 'X'


def simulate_event_driven(circuit, changed_inputs=None):
    from collections import deque
    
    activity_queue = deque()
    queued = set()
    gate_evaluations = 0
    enqueue_attempts = 0
    unique_enqueues = 0

    def schedule(node):
        nonlocal enqueue_attempts, unique_enqueues
        enqueue_attempts += 1
        if node not in queued:
            queued.add(node)
            unique_enqueues += 1
            activity_queue.append(node)

    if changed_inputs is None:
        seed_nodes = list(circuit.PIs)
    else:
        seed_nodes = list(changed_inputs)

    for node in seed_nodes:
        for fanout_gate in node.fanouts:
            schedule(fanout_gate)

    if changed_inputs is None:
        for node in circuit.nodes.values():
            if node.role == "CONST":
                for fanout_gate in node.fanouts:
                    schedule(fanout_gate)
    
    while activity_queue:
        node = activity_queue.popleft()
        queued.discard(node)

        if node.level == -1:
            continue
        
        old_value = node.value
        new_value = eval_gate(node)
        gate_evaluations += 1
        node.value = new_value
        
        if new_value != old_value:
            for fanout_gate in node.fanouts:
                schedule(fanout_gate)

    return {
        'gate_evaluations': gate_evaluations,
        'enqueue_attempts': enqueue_attempts,
        'unique_enqueues': unique_enqueues,
        'duplicate_enqueues_filtered': enqueue_attempts - unique_enqueues,
    }


def simulate(circuit):
    nodes_sorted = sorted(circuit.nodes.values(), key=lambda n: n.level)
    gate_evaluations = 0

    for node in nodes_sorted:
        if node.role in ["PI", "CONST"]:
            continue
        if node.level == -1:
            continue
        node.value = eval_gate(node)
        gate_evaluations += 1

    return {
        'gate_evaluations': gate_evaluations,
    }


def generate_faults(circuit):
    faults = []
    for node in circuit.nodes.values():
        faults.append(Fault(node, 0))
        faults.append(Fault(node, 1))
    return faults


def assign_default_inputs(circuit):
    for i, pi in enumerate(circuit.PIs):
        pi.value = '1' if i % 2 == 0 else '0'


def run_folder_demo(netlist_folder="netlists"):
    circuits = parse_netlist_folder(netlist_folder)

    if not circuits:
        print(f"No netlist files found in folder: {netlist_folder}")
        return

    for name, circuit in circuits.items():
        levelize(circuit)
        assign_default_inputs(circuit)
        simulate_event_driven(circuit)
        faults = generate_faults(circuit)

        print(f"\n=== {name} ===")
        print(f"Nodes: {len(circuit.nodes)} | PIs: {len(circuit.PIs)} | POs: {len(circuit.POs)}")
        for po in circuit.POs:
            print(f"{po.name} = {po.value}")
        print(f"Total faults generated: {len(faults)}")
