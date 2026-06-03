import subprocess
import os

MODEL_SB = "models/circuit_model_satisfy.mzn"
MODEL_REF = "models/circuit_model_satisfy_decomposed.mzn"
SOLVER_SB = "pumpkin-strong-bridge"
SOLVER_REF = "gecode"
INSTANCE_DIR = "instances_for_validation"


def run_minizinc(model, solver, dzn_file):
    cmd = [
        "minizinc",
        "--solver", solver,
        model,
        dzn_file,
        "-a"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error running {solver} on {dzn_file}")
        print(result.stderr)
        return None

    return result.stdout


def normalize_output(output):
    lines = output.splitlines()

    # Remove MiniZinc separators
    cleaned = [
        line.strip()
        for line in lines
        if line.strip() and not set(line.strip()) <= set("-=")
    ]

    # Sort solutions
    cleaned.sort()

    return cleaned


def compare_outputs(out1, out2):
    return out1 == out2


def validate_instance(dzn_file):
    print(f"Checking {dzn_file}...")

    sb_output = run_minizinc(MODEL_SB, SOLVER_SB, dzn_file)
    ref_output = run_minizinc(MODEL_REF, SOLVER_REF, dzn_file)

    if sb_output is None or ref_output is None:
        return False

    sb_norm = normalize_output(sb_output)
    ref_norm = normalize_output(ref_output)
    print(len(sb_norm), len(ref_norm))

    if sb_norm == ref_norm:
        print(f"MATCH: {dzn_file}")
        return True
    else:
        print(f"MISMATCH: {dzn_file}")
        print(f"SB solutions:  {len(sb_norm)}")
        print(f"REF solutions: {len(ref_norm)}")
        return False


def main():
    files = [
        os.path.join(INSTANCE_DIR, f)
        for f in os.listdir(INSTANCE_DIR)
        if f.endswith(".dzn")
    ]

    total = len(files)
    correct = 0

    for dzn in files:
        if validate_instance(dzn):
            correct += 1

    print("\n============================")
    print(f"{correct}/{total} instances match")
    print("============================")


if __name__ == "__main__":
    main()



