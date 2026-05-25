import pandas as pd
import matplotlib.pyplot as plt
import os
import sys

# ===============================
# CONFIGURATION
# ===============================


if len(sys.argv) < 2:
    raise ValueError("Usage: python analyze.py <csv file>")

SB_FILE = str(sys.argv[1])     # strong bridge results
BASE_FILE = None  # set to "results_base_seed12345.csv" if you have baseline

OUTPUT_DIR = "plots_exp_1"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ===============================
# LOAD DATA
# ===============================

df_sb = pd.read_csv(SB_FILE)


# ===============================
# GROUP DATA (AVERAGE PER n,k)
# ===============================

grouped_sb = df_sb.groupby(["n", "k"]).mean().reset_index()

grouped_sb["n"] = grouped_sb["n"].astype(int)
grouped_sb["k"] = grouped_sb["k"].astype(int)


# ===============================
# HELPER: PLOT FUNCTION
# ===============================

def plot_metric(grouped, metric, ylabel, filename):
    plt.figure()

    for k in sorted(grouped["k"].unique()):
        subset = grouped[grouped["k"] == k]
        plt.plot(
            subset["n"],
            subset[metric],
            marker='o',
            label=f"k={k}"
        )

    plt.xlabel("n (number of nodes)")
    plt.ylabel(ylabel)
    plt.title(f"{ylabel} vs n")
    plt.legend()
    plt.grid(True)

    plt.savefig(os.path.join(OUTPUT_DIR, filename))
    plt.close()

    print(f"Saved plot: {filename}")


# ===============================
# PLOTS: STRONG BRIDGE ONLY
# ===============================

plot_metric(grouped_sb, "conflicts", "Average Conflicts", "conflicts_sb.png")
plot_metric(grouped_sb, "propagations", "Average Propagations", "propagations_sb.png")
plot_metric(grouped_sb, "solving time", "Average Runtime (s)", "runtime_sb.png")
plot_metric(grouped_sb, "average lbd", "Average LBD", "lbd_sb.png")


# ===============================
# OPTIONAL: BASELINE COMPARISON
# ===============================

if BASE_FILE is not None:
    df_base = pd.read_csv(BASE_FILE)

    # Merge on SAME instances
    merged = df_base.merge(
        df_sb,
        on=["n", "k", "seed"],
        suffixes=("_base", "_sb")
    )

    # ===============================
    # Compute improvements
    # ===============================

    merged["conflict_reduction_pct"] = (
        (merged["conflicts_base"] - merged["conflicts_sb"])
        / merged["conflicts_base"].replace(0, 1)  # avoid division by zero
    ) * 100

    merged["propagation_diff"] = (
        merged["propagations_sb"] - merged["propagations_base"]
    )

    # Average improvements per (n,k)
    grouped_compare = merged.groupby(["n", "k"]).mean().reset_index()

    print("\nComparison (baseline vs strong bridge):")
    print(grouped_compare[["n", "k", "conflict_reduction_pct", "propagation_diff"]])

    # ===============================
    # Plot conflict reduction
    # ===============================

    plt.figure()

    for k in sorted(grouped_compare["k"].unique()):
        subset = grouped_compare[grouped_compare["k"] == k]
        plt.plot(
            subset["n"],
            subset["conflict_reduction_pct"],
            marker='o',
            label=f"k={k}"
        )

    plt.xlabel("n")
    plt.ylabel("Conflict reduction (%)")
    plt.title("Conflict Reduction vs n")
    plt.legend()
    plt.grid(True)

    plt.savefig(os.path.join(OUTPUT_DIR, "conflict_reduction.png"))
    plt.close()

    print("Saved plot: conflict_reduction.png")

    # ===============================
    # Scatter: strong bridges vs propagations
    # ===============================

    if "strong_bridge_propagations" in merged.columns:

        plt.figure()
        plt.scatter(
            merged["strong_bridge_propagations"],
            merged["propagations_sb"],
            alpha=0.6
        )

        plt.xlabel("Strong bridge propagations")
        plt.ylabel("Total propagations")
        plt.title("Correlation SB propagations vs total propagations")

        plt.grid(True)

        plt.savefig(os.path.join(OUTPUT_DIR, "sb_vs_total_propagations.png"))
        plt.close()

        print("Saved plot: sb_vs_total_propagations.png")


# ===============================
# DONE
# ===============================

print("\nAnalysis complete")