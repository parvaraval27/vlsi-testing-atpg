import os
import sys
from time import perf_counter

from d import run_d_algorithm_on_file
from netlist_graph import run_folder_demo
from podem import run_podem_on_file


def _iter_netlist_files(netlist_folder):
    if not os.path.isdir(netlist_folder):
        return []
    files = []
    for entry in sorted(os.listdir(netlist_folder)):
        full_path = os.path.join(netlist_folder, entry)
        if os.path.isfile(full_path) and entry.lower().endswith(".txt"):
            files.append(full_path)
    return files


def _print_analysis_result(result, label, netlist_name):
    print(f"\n[{label} RESULT] {netlist_name}")
    print(f"Status: {result['status']}")
    print(f"Faults simulated: {result['fault_count']}")
    print(f"Detected faults: {result['detected_faults']}")
    print(f"Undetected faults: {result['undetected_faults']}")
    print(f"Fault coverage (%): {result['fault_coverage_pct']:.2f}")
    print(f"Total backtracks: {result.get('total_backtracks', 0)}")
    print(f"Average backtracks per fault: {result.get('avg_backtracks_per_fault', 0):.2f}")
    print(f"Total time (ms): {result['total_time_ms']:.3f}")
    print(f"Average per fault (us): {result['avg_time_per_fault_us']:.3f}")
    print("Per-fault results:")

    for entry in result["results"]:
        backtracks = entry.get('backtracks', 'N/A')
        print(
            f"- Fault {entry['fault']} | vector={entry['test_vector']} "
            f"| detected={entry.get('detected', False)} "
            f"| po={entry['po_values']} | backtracks={backtracks} | time_us={entry['elapsed_us']:.3f}"
        )


def _run_algorithm_on_all_netlists(netlist_folder, label, runner):
    netlist_files = _iter_netlist_files(netlist_folder)
    if not netlist_files:
        print(f"No netlist files found in folder: {netlist_folder}")
        return

    print(f"\nRunning {label} on all netlists in: {netlist_folder}")
    grand_total_ms = 0.0
    grand_faults = 0
    grand_detected = 0
    grand_backtracks = 0
    run_start = perf_counter()

    for netlist_path in netlist_files:
        result = runner(netlist_path)
        _print_analysis_result(result, label, os.path.basename(netlist_path))
        grand_total_ms += result["total_time_ms"]
        grand_faults += result["fault_count"]
        grand_detected += result["detected_faults"]
        grand_backtracks += result.get("total_backtracks", 0)

    wall_ms = (perf_counter() - run_start) * 1000.0
    grand_coverage = (grand_detected * 100.0 / grand_faults) if grand_faults else 0.0
    grand_avg_backtracks = (grand_backtracks / grand_faults) if grand_faults else 0.0
    print(
        f"\n[{label} SUMMARY] Files: {len(netlist_files)} | Faults: {grand_faults} | "
        f"Detected: {grand_detected} | Coverage (%): {grand_coverage:.2f} | "
        f"Total backtracks: {grand_backtracks} | Avg backtracks/fault: {grand_avg_backtracks:.2f} | "
        f"Fault-sim time (ms): {grand_total_ms:.3f} | Wall time (ms): {wall_ms:.3f}"
    )

def main():
    while True:
        print("\n===== ATPG MENU =====")
        print("1. Run basic flow")
        print("2. Run D Algorithm")
        print("3. Run PODEM")
        print("4. Exit")

        choice = input("Enter choice: ")

        if choice == '1':
            netlist_folder = "netlists"
            if len(sys.argv) > 1:
                netlist_folder = sys.argv[1]
            run_folder_demo(netlist_folder)

        elif choice == '2':
            netlist_folder = "netlists"
            if len(sys.argv) > 1:
                netlist_folder = sys.argv[1]
            _run_algorithm_on_all_netlists(netlist_folder, "D", run_d_algorithm_on_file)

        elif choice == '3':
            netlist_folder = "netlists"
            if len(sys.argv) > 1:
                netlist_folder = sys.argv[1]
            _run_algorithm_on_all_netlists(netlist_folder, "PODEM", run_podem_on_file)

        elif choice == '4':
            break   


if __name__ == "__main__":
    main()
