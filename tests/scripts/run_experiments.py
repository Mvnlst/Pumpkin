from generate import generate_and_save
import random
import sys
import subprocess
import csv
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

if len(sys.argv) < 2:
    raise ValueError("Usage: python run_experiments.py <seed>")
GLOBAL_SEED = int(sys.argv[1])

OUTPUT_DIR = f"../experiments/experiment{GLOBAL_SEED}"
os.makedirs(OUTPUT_DIR, exist_ok=True)


EXECUTABLE = os.path.join("..", "..", "target", "release", "pumpkin-solver.exe")
MAX_WORKERS = 10 # for parallel running of instances


def run_experiment(solve_type, n_values, k_values, instance_amount, model_file, timeout):
    global N_VALUES, K_VALUES, INSTANCE_AMOUNT, MODEL_FILE, TIMEOUT, SOLVE_TYPE

    print(f"\nRunning {solve_type} experiments")

    N_VALUES = n_values
    K_VALUES = k_values
    INSTANCE_AMOUNT = instance_amount
    MODEL_FILE = model_file
    TIMEOUT = timeout
    SOLVE_TYPE = solve_type

    os.makedirs(f"{OUTPUT_DIR}/{SOLVE_TYPE}", exist_ok=True)

    # output files
    output_base = f"{OUTPUT_DIR}/{SOLVE_TYPE}/results_base_seed{GLOBAL_SEED}.csv"
    output_sb   = f"{OUTPUT_DIR}/{SOLVE_TYPE}/results_sb_seed{GLOBAL_SEED}.csv"

    if not os.path.exists(output_base):
        init_output_file(output_base)
    if not os.path.exists(output_sb):
        init_output_file(output_sb)

    generate_instances()

    print(f"\nRunning BASE ({SOLVE_TYPE}) experiments...")
    run_instances(EXECUTABLE, "base", output_base)
    

    print(f"\nRunning STRONG BRIDGE ({SOLVE_TYPE}) experiments...")
    run_instances(EXECUTABLE, "strong-bridges", output_sb)

    run_analysis(output_base, output_sb)



def get_seeds_for_pair(n, k, amount):
    pair_rng = random.Random(GLOBAL_SEED + n * 10000 + k)
    return [pair_rng.randint(0, 10**9) for _ in range(amount)]


def init_output_file(path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "n", "k", "seed",
            "nodes", "restarts", "peak depth", "solving time",
            "conflicts", "propagations",
            "sb propagations", "sb prop / all prop",
            "scc propagations", "scc prop / all prop",
            "average conflict size", "unit nogoods learned",
            "average nogood length", "average backtrack amount",
            "average lbd"
        ])



# Generation
def generate_instances():
    for n in N_VALUES:
        for k in K_VALUES:
            print(f"generating {INSTANCE_AMOUNT} instances for n = {n} and k = {k}...")
            seeds_for_pair = get_seeds_for_pair(n, k, INSTANCE_AMOUNT)

            for seed in seeds_for_pair:
                folder = f"{OUTPUT_DIR}/{SOLVE_TYPE}/instances/n{n}_k{k}/seed{seed}"
                fzn_file = os.path.join(folder, "instance.fzn")

                # only build instance if it is not here yet
                if os.path.exists(fzn_file):
                    continue

                generate_and_save(n, k, seed, model_file=MODEL_FILE, experiment_seed=GLOBAL_SEED, solve_type=SOLVE_TYPE)

def ensure_binary_exists():
    print("Building with cargo...")
    subprocess.run(
        ["cargo", "build", "--release", "-p", "pumpkin-solver"],
        check=True
    )


# check which instances are already run and written to csv
def load_completed(output_file):
    completed = set()

    # csv file does not exist yet
    if not os.path.exists(output_file):
        return completed

    with open(output_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (int(row["n"]), int(row["k"]), int(row["seed"]))
            completed.add(key)

    return completed


def run_analysis(base_file, sb_file):
    print(f"\nRunning analysis for:\n  {base_file}\n  {sb_file}")

    try:
        subprocess.run(
            ["python", "analyze.py", base_file, sb_file],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Analysis script failed: {e}")


# Execution
def run_instances(executable, mode, output_file):
    completed_set = load_completed(output_file)

    tasks = []

    for n in N_VALUES:
        for k in K_VALUES:
            seeds_for_pair = get_seeds_for_pair(n, k, INSTANCE_AMOUNT)

            for seed in seeds_for_pair:
                key = (n, k, seed)
                if key in completed_set:
                    continue # we already have the stats of this instance

                tasks.append((n, k, seed))
    
    total = len(N_VALUES) * len(K_VALUES) * INSTANCE_AMOUNT
    print(f"Running {len(tasks)} instances in parellel, as we already have {total - len(tasks)} written in csv")
    completed = 0
    results = []

    # Parellel execution
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [
                executor.submit(run_and_parse_instance, n, k, seed, executable, mode, TIMEOUT, SOLVE_TYPE)
                for (n, k, seed) in tasks
            ]

            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as e:
                    print(f"Worker crashed: {e}")
                    continue

                if result is None:
                    print("Warning: got None result")
                    continue

                n, k, seed, stats = result
                write_to_output(n, k, seed, stats, output_file)

                completed += 1
                print(f"{completed}/{total} done (n={n}, k={k}). Solving time: {stats.get('solving time', -1)}")



    

def write_to_output(n, k, seed, stats, output_file):
    # Sequential writing
    with open(output_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            n, k, seed,
            stats.get("nodes", 0),
            stats.get("restarts", 0),
            stats.get("peak depth", 0),
            stats.get("solving time", 0),
            stats.get("conflicts", 0),
            stats.get("propagations", 0),
            stats.get("sb propagations", 0),
            stats.get("sb prop / all prop", 0),
            stats.get("scc propagations", 0),
            stats.get("scc prop / all prop", 0),
            stats.get("average conflict size", 0),
            stats.get("unit nogoods learned", 0),
            stats.get("average nogood length", 0),
            stats.get("average backtrack amount", 0),
            stats.get("average lbd", 0),
        ])

# Core logic
def run_and_parse_instance(n, k, seed, executable, mode, timeout, solve_type):
    folder = f"{OUTPUT_DIR}/{solve_type}/instances/n{n}_k{k}/seed{seed}"
    fzn_file = os.path.join(folder, "instance.fzn")
    fzn_file = fzn_file.replace("\\", "/")
    
    
    cmd = [
        executable,
        fzn_file,
        "-s",
        "-v",
        "--circuit-propagation",
        mode   # "base" or "strong-bridges"
    ]

    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        stats = parse_stats(result.stdout)

    except subprocess.TimeoutExpired:
        print(f"Timeout for n={n}, k={k}, seed={seed}")
        stats = {
            "nodes": -1, 
            "restarts": -1, 
            "peak depth": -1, 
            "solving time": -1, 
            "conflicts": -1, 
            "propagations": -1, 
            "sb propagations": -1, 
            "sb prop / all prop": -1, 
            "scc propagations": -1, 
            "scc prop / all prop": -1, 
            "average conflict size": -1, 
            "unit nogoods learned": -1, 
            "average nogood length": -1, 
            "average backtrack amount": -1, 
            "average lbd": -1
        }
    
    
    return (n, k, seed, stats)


def parse_stats(output: str):
    stats = {}

    # split into stat blocks
    blocks = output.split("%%%mzn-stat-end")

    # take last non-empty block
    stat_block = None
    for block in reversed(blocks):
        if "%%%mzn-stat:" in block:
            stat_block = block
            break
    
    if stat_block is None:
            return stats  # no stats found

    for line in stat_block.splitlines():
        if "nodes" in line:
            stats["nodes"] = int(line.split("=")[1])
        elif "restarts" in line:
            stats["restarts"] = int(line.split("=")[1])
        elif "peakDepth" in line:
            stats["peak depth"] = int(line.split("=")[1])
        elif "solveTime" in line:
            stats["solving time"] = float(line.split("=")[1])
        elif "failures" in line:
            stats["conflicts"] = int(line.split("=")[1])
        elif "propagations" in line:
            stats["propagations"] = int(line.split("=")[1])
        elif "NumberOfSbPropagations" in line:
            stats["sb propagations"] = int(line.split("=")[1])
            stats["sb prop / all prop"] = round(stats["sb propagations"] / float(stats["propagations"]), 2)
        elif "NumberOfSccPropagations" in line:
            stats["scc propagations"] = int(line.split("=")[1])
            stats["scc prop / all prop"] = round(stats["scc propagations"] / float(stats["propagations"]), 2)
        elif "AverageConflictSize" in line:
            stats["average conflict size"] = float(line.split("=")[1])
        elif "NumUnit" in line:
            stats["unit nogoods learned"] = int(line.split("=")[1])
        elif "AverageLearnedNogoodLength" in line:
            stats["average nogood length"] = float(line.split("=")[1])
        elif "AverageBacktrackAmount" in line:
            stats["average backtrack amount"] = float(line.split("=")[1])
        elif "AverageLbd" in line:
            stats["average lbd"] = float(line.split("=")[1])
    
    return stats


if __name__ == "__main__":
    ensure_binary_exists()

    run_experiment(
        solve_type="sat",
        n_values=[10, 20],
        k_values=[2, 3, 4],
        instance_amount=20,
        model_file="../models/circuit_model_satisfy.mzn",
        timeout=15 * 60
    )

    run_experiment(
        solve_type="opt",
        n_values=[15, 20],
        k_values=[2, 3],
        instance_amount=10,
        model_file="../models/circuit_model_minimize.mzn",
        timeout=60 * 60
    )

