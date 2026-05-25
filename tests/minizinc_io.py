import subprocess
import os

# Create a folder to group the .dzn and .fzn file. Used for manual generation through generate.py
def create_manual_instance_folder(n, k, seed):
    folder = f"manual_instances/n{n}_k{k}_seed{seed}"
    os.makedirs(folder, exist_ok=True)
    return folder

# Create an overarching experiment folder and subfolders for structuring the experiments
def create_experiment_instance_folder(experiment_seed, instance_n, instance_k, instance_seed):
    folder = f"experiment{experiment_seed}/n{instance_n}_k{instance_k}/seed{instance_seed}"
    os.makedirs(folder, exist_ok=True)
    return folder

# Write the dzn file to the correct location
def write_dzn(edges, n, k, seed, folder, strong_bridges):
    filename = f"{folder}/instance.dzn"

    with open(filename, "w") as f:
        # info about the problem
        f.write(f"% n = {n}\n") 
        f.write(f"% k = {k}\n")
        f.write(f"% seed = {seed}\n")
        if strong_bridges is not None:
            f.write(f"% strong bridges = {strong_bridges}\n")
        f.write("\n")

        # actual problem instance
        f.write(f"n = {n};\n")

        f.write("allowed = [\n")
        for i in range(n):
            row = sorted(edges[i])
            # Convert to 1-based indexing
            row_str = ", ".join(str(j+1) for j in row)

            f.write(f"    {{{row_str}}}")
            if i < n - 1:
                f.write(",\n")
            else:
                f.write("\n")
        f.write("];\n")

    return filename

# Compile the fzn file and put it in the right location with the -o flag
# Prevent ozn file from generating
def compile_fzn(model_file, dzn_file, folder: str, solver: str, manual_instance=False):
    fzn_file = os.path.join(folder, "instance.fzn")

    cmd = [
        "minizinc",
        "--solver", solver,
        "--compile",
        "--no-output-ozn",
        "-o", fzn_file,
        model_file,
        dzn_file
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)


    if result.returncode != 0:
        print("Error compiling")
        print(result.stderr)
    elif manual_instance:
        correctString = folder.replace("\\", "/")
        print(f"cargo run -p pumpkin-solver --features=debug-checks {correctString}" + "/instance.fzn -s")
        print(f"cargo run -p pumpkin-solver --conflict-resolver=no-learning {correctString}" + "/instance.fzn -s")

    return fzn_file