import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import os
import sys


# Usage:
# python analyze.py results_base.csv results_sb.csv
# or:
# python analyze.py results_sb.csv
# or:
# python analyze.py results_base.csv

if len(sys.argv) < 2:
    raise ValueError("Usage: python analyze.py <file1> [file2]")

file1 = sys.argv[1]
file2 = sys.argv[2] if len(sys.argv) > 2 else None

# Detect roles based on filename
df_base = None
df_sb = None

def remove_timeouts(df):
    return df[df["solving time"] != -1]

if "sb" in file1:
    df_sb = remove_timeouts(pd.read_csv(file1))
else:
    df_base = remove_timeouts(pd.read_csv(file1))

if file2:
    if "sb" in file2:
        df_sb = remove_timeouts(pd.read_csv(file2))
    else:
        df_base = remove_timeouts(pd.read_csv(file2))

OUTPUT_DIR = file1.split('/')[0] + "/analysis"
PLOTS_DIR = OUTPUT_DIR + "/plots"
TABLES_DIR = OUTPUT_DIR + "/tables"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)



# Preprocess
def preprocess(df):
    grouped = df.groupby(["n", "k"]).mean().reset_index()
    grouped = grouped[grouped["k"] != 1]
    return grouped

group_base = preprocess(df_base) if df_base is not None else None
group_sb   = preprocess(df_sb)   if df_sb   is not None else None


colors = {
    k: plt.cm.tab10(i)
    for i, k in enumerate(sorted(
        set()
        .union(group_base["k"] if group_base is not None else [])
        .union(group_sb["k"] if group_sb is not None else [])
    ))
}


# Plotting function

def plot_metric(metric, ylabel, filename, log_scale=False, only_sb=False):
    plt.figure()

    # Collect all k values
    ks = sorted(set()
        .union(group_base["k"] if (group_base is not None and not only_sb) else [])
        .union(group_sb["k"] if group_sb is not None else [])
    )

    colors = {k: plt.cm.tab10(i) for i, k in enumerate(ks)}

    # Plot baseline ONLY if not SB-only
    if group_base is not None and not only_sb:
        for k in group_base["k"].unique():
            subset = group_base[group_base["k"] == k]
            plt.plot(
                subset["n"],
                subset[metric],
                linestyle='-',
                marker='o',
                color=colors[k]
            )

    # Always plot SB if available
    if group_sb is not None:
        for k in group_sb["k"].unique():
            subset = group_sb[group_sb["k"] == k]
            plt.plot(
                subset["n"],
                subset[metric],
                linestyle='--' if not only_sb else '-',   # cleaner look
                marker='x' if not only_sb else 'o',
                color=colors[k]
            )

    # Legend for k
    color_legend = [
        Line2D([0], [0], color=colors[k], lw=2, label=f"k = {k}")
        for k in ks
    ]

    first_legend = plt.legend(handles=color_legend, title="k", loc="upper left")
    plt.gca().add_artist(first_legend)

    # Legend for method ONLY if both shown
    if not only_sb:
        style_legend = []
        if group_base is not None:
            style_legend.append(
                Line2D([0], [0], color='black', lw=2, linestyle='-', label='Baseline')
            )
        if group_sb is not None:
            style_legend.append(
                Line2D([0], [0], color='black', lw=2, linestyle='--', label='Strong bridge')
            )
        plt.legend(handles=style_legend, title="Method", loc="upper right")

    if log_scale:
        plt.yscale("log")

    plt.xlabel("n (number of nodes)")
    plt.ylabel(ylabel)
    plt.title(f"{ylabel} vs n")
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, filename), bbox_inches='tight')


def generate_latex_table(df_base, df_sb, output_file="table.txt"):
    # Merge on same instances
    merged = df_base.merge(
        df_sb,
        on=["n", "k", "seed"],
        suffixes=("_base", "_sb")
    )

    # Group averages per (n,k)
    grouped = merged.groupby(["n", "k"]).mean().reset_index()

    # Compute improvements
    grouped["conflict_reduction"] = (
        (grouped["conflicts_base"] - grouped["conflicts_sb"]) /
        grouped["conflicts_base"].replace(0, 1)
    ) * 100

    grouped["propagation_reduction"] = (
        (grouped["propagations_base"] - grouped["propagations_sb"]) /
        grouped["propagations_base"].replace(0, 1)
    ) * 100

    # Start LaTeX table
    lines = []

    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc|c}")
    lines.append("\\hline")
    lines.append("n & k & Conflicts (base) & Conflicts (SB) & $\\Delta$ Conflicts & Reduction (\\%) \\\\")
    lines.append("\\hline")

    for _, row in grouped.iterrows():
        n = int(row["n"])
        k = int(row["k"])

        base_conf = round(row["conflicts_base"], 1)
        sb_conf = round(row["conflicts_sb"], 1)
        delta_conf = round(abs(base_conf - sb_conf),1)
        reduction = round(row["conflict_reduction"], 1)

        # Handle division edge case
        if base_conf == 0:
            reduction_str = "--"
        else:
            reduction_str = f"{reduction}"

        lines.append(f"{n} & {k} & {base_conf} & {sb_conf} & {delta_conf} & {reduction_str} \\\\")

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Conflict reduction using strong bridges}")
    lines.append("\\end{table}")

    # Write to file
    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"LaTeX table written to {output_file}")


def generate_propagation_table(df_base, df_sb, output_file="table_prop.txt"):

    merged = df_base.merge(
        df_sb,
        on=["n", "k", "seed"],
        suffixes=("_base", "_sb")
    )

    grouped = merged.groupby(["n", "k"]).mean().reset_index()

    grouped["prop_reduction"] = (
        (grouped["propagations_base"] - grouped["propagations_sb"]) /
        grouped["propagations_base"].replace(0, 1)
    ) * 100

    lines = []

    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc|c}")
    lines.append("\\hline")
    lines.append("n & k & Prop (base) & Prop (SB) & $\\Delta$ Prop & Reduction (\\%) \\\\")
    lines.append("\\hline")

    for _, row in grouped.iterrows():
        n = int(row["n"])
        k = int(row["k"])

        base_prop = format_sci(round(row["propagations_base"], 1))
        sb_prop = format_sci(round(row["propagations_sb"], 1))

        delta_prop = format_sci(round(row["propagations_base"] - row["propagations_sb"], 1))
        reduction = round(row["prop_reduction"], 1)

        if base_prop == 0:
            reduction_str = "--"
        else:
            reduction_str = f"{reduction}"

        lines.append(
            f"{n} & {k} & ${base_prop}$ & ${sb_prop}$ & "
            f"${delta_prop}$ & {reduction_str} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Reduction in propagations using strong bridges}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"Propagation table written to {output_file}")


def format_sci(x):
    if x == 0:
        return "0"
    if x < 1000:  # keep small numbers normal
        return f"{x:.1f}"
    
    exponent = int(f"{x:.0e}".split("e")[1])
    base = x / (10 ** exponent)

    return f"{base:.2f} \\times 10^{exponent}"






# Generate plots

plot_metric("conflicts", "Average Conflicts", "conflicts.png", True)
plot_metric("propagations", "Average Propagations", "propagations.png", True)
plot_metric("solving time", "Average Runtime (s)", "runtime.png", True)
plot_metric("average lbd", "Average LBD", "lbd.png")

if df_base is not None and df_sb is not None:
    generate_latex_table(df_base, df_sb, TABLES_DIR + "/conflicts_table.txt")
    generate_propagation_table(df_base, df_sb, TABLES_DIR + "/propagation_table.txt")


if df_sb is not None:
    
    plot_metric("sb prop / all prop", "SB Propagations / Total Propagations", "sb_ratio.png", only_sb=True)
    plot_metric("scc prop / all prop", "SCC Propagations / Total Propagations", "scc_ratio.png", only_sb=True)
    plot_metric("sb propagations", "Number of Strong Bridge Propagations", "sb.png", only_sb=True, log_scale=True)
    plot_metric("scc propagations", "Number of SCC Propagations", "scc.png", only_sb=True, log_scale=True)




print("\nAnalysis complete")


