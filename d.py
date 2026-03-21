from time import perf_counter

from netlist_graph import (
    generate_faults,
    levelize,
    parse_netlist,
)


class DAlgorithmEngine:
    def __init__(self, circuit):
        self.circuit = circuit
        self.backtrack_count = 0

    def solve_fault(self, fault):
        # TODO: Real D implementation should fill vector/PO values.
        #Implement the function here and if needed more functions, define and use them below this one, output format for D and PODEM is pre-written for final consistency
        self.backtrack_count = 0
        return {
            "fault": f"{fault.node.name}/SA{fault.stuck_at}",
            "detected": False,
            "test_vector": {},
            "po_values": {},
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
            "status": "pending-implementation",
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
