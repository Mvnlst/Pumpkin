from generate import generate_and_save
import random
import sys
import subprocess
import csv
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Lock

N_VALUES = [20, 40] # which different n's we explore
K_VALUES = [2, 4] # which different k's we explore
INSTANCE_AMOUNT = 2 # how many times we generate an instance for each (n, k) combination to average over afterwards
TIMEOUT = 15 * 60 # 15 minutes
if len(sys.argv) < 2:
    raise ValueError("Usage: python run_experiments.py <seed>")

GLOBAL_SEED = int(sys.argv[1])

write_lock = Lock() # lock for parallelization

rng = random.Random(GLOBAL_SEED)
ALL_SEEDS = [rng.randint(0, 10**9) for _ in range(len(N_VALUES) * len(K_VALUES) * INSTANCE_AMOUNT)] # all seeds used for generation

OUTPUT_DIR = f"experiment{GLOBAL_SEED}"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = f"{OUTPUT_DIR}/results_sb_seed{GLOBAL_SEED}.csv"

EXECUTABLE = os.path.join("..", "target", "release", "pumpkin-solver.exe")


with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "n", "k", "seed",
        "nodes", "restarts", "peak depth", "solving time", "conflicts", "propagations", "average conflict size", "unit nogoods learned", "average nogood length", "average backtrack amount", "average lbd"
    ])


MODEL_FILE = "models/circuit_model.mzn"

# Generation
def generate_instances():
    index = 0 # index keeping track of used seeds
    for n in N_VALUES:
        for k in K_VALUES:
            seeds_for_pair = ALL_SEEDS[index:index+INSTANCE_AMOUNT]
            index += INSTANCE_AMOUNT

            for seed in seeds_for_pair:
                generate_and_save(n, k, seed, model_file=MODEL_FILE, experiment_seed=GLOBAL_SEED)

def ensure_binary_exists():

    if not os.path.exists(EXECUTABLE):
        print("Release binary not found. Building with cargo...")
        subprocess.run(
            ["cargo", "build", "--release", "-p", "pumpkin-solver"],
            check=True
        )
    else:
        print("Using existing release build.")


# Execution
def run_instances():
    tasks = []

    index = 0 # index keeping track of used seeds
    for n in N_VALUES:
        for k in K_VALUES:
            seeds_for_pair = ALL_SEEDS[index:index+INSTANCE_AMOUNT]
            index += INSTANCE_AMOUNT

            for seed in seeds_for_pair:
                tasks.append((n, k, seed))
    
    print(f"Running {len(tasks)} instances in parellel...")

    
    with ProcessPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(run_and_parse_instance, n, k, seed, EXECUTABLE)
                for (n, k, seed) in tasks
            ]

            for future in as_completed(futures):
                future.result()  # raises exceptions if any

    print(f"Analyze the results by running python analyze.py {OUTPUT_FILE}")
    print(f"Compare base vs extension by running python analyze.py {OUTPUT_FILE} [base version]")

# Core logic
def run_and_parse_instance(n, k, seed, executable):
    folder = f"experiment{GLOBAL_SEED}/instances/n{n}_k{k}/seed{seed}"
    fzn_file = os.path.join(folder, "instance.fzn")
    fzn_file = fzn_file.replace("\\", "/")
    
    cmd = [
        executable,
        fzn_file,
        "-s"
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT  # 12 minutes
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
            "average conflict size": -1, 
            "unit nogoods learned": -1, 
            "average nogood length": -1, 
            "average backtrack amount": -1, 
            "average lbd": -1
        }

    print(f"ran n={n} k={k} and took {stats.get('solving time', -1)} seconds")

    write_instance_result(n, k, seed, stats)


def parse_stats(output: str):
    stats = {}
    for line in output.splitlines():
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


def write_instance_result(n, k, seed, stats):
    with write_lock:
        with open(OUTPUT_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                n, k, seed,
                stats.get("nodes", 0),
                stats.get("restarts", 0),
                stats.get("peak depth", 0),
                stats.get("solving time", 0),
                stats.get("conflicts", 0),
                stats.get("propagations", 0),
                stats.get("average conflict size", 0),
                stats.get("unit nogoods learned", 0),
                stats.get("average nogood length", 0),
                stats.get("average backtrack amount", 0),
                stats.get("average lbd", 0),
            ])

# main
if __name__ == "__main__":
    ensure_binary_exists()
    generate_instances() # generate all instances with correct folder structure
    run_instances() # run all instances, collect statistics and write the data to the output file