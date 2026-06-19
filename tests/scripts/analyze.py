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

if len(sys.argv) < 3:
    raise ValueError("Usage: python analyze.py <file1> <file2> <'sat' or 'opt'>")

file1 = sys.argv[1]
file2 = sys.argv[2]
mode = sys.argv[3]

# Detect roles based on filename
df_base = None
df_sb = None

def remove_timeouts(df):
    return df[df["solving time"] != -1]


df_base_raw = pd.read_csv(file1) if "sb" not in file1 else None
df_sb_raw = pd.read_csv(file1) if "sb" in file1 else None


if "sb" in file1:
    df_sb = remove_timeouts(pd.read_csv(file1))
else:
    df_base = remove_timeouts(pd.read_csv(file1))

if file2:
    if "sb" in file2:
        df_sb = remove_timeouts(pd.read_csv(file2))
        df_sb_raw = pd.read_csv(file2)
    else:
        df_base = remove_timeouts(pd.read_csv(file2))
        df_base_raw = pd.read_csv(file2)


OUTPUT_DIR = os.path.dirname(file1) + "/analysis"
PLOTS_DIR = OUTPUT_DIR + "/plots"
TABLES_DIR = OUTPUT_DIR + "/tables"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)




def add_normalized_time_shares(df):
    df = df.copy()

    total = df["base time"] + df["sb time"] + df["scc time"]

    df["base share"] = df["base time"] / total.replace(0, pd.NA)
    df["sb share"] = df["sb time"] / total.replace(0, pd.NA)
    df["scc share"] = df["scc time"] / total.replace(0, pd.NA)
    df["ext share"]   = df["sb share"] + df["scc share"]

    return df



# Preprocess
def preprocess(df):
    grouped = df.groupby(["n", "k"]).mean().reset_index()
    grouped = grouped[grouped["k"] != 1]
    return grouped

group_base = preprocess(df_base) if df_base is not None else None
df_sb = add_normalized_time_shares(df_sb)
group_sb   = preprocess(df_sb)   if df_sb   is not None else None


colors = {
    k: plt.cm.tab10(i)
    for i, k in enumerate(sorted(
        set()
        .union(group_base["k"] if group_base is not None else [])
        .union(group_sb["k"] if group_sb is not None else [])
    ))
}


def generate_timeout_table(df_base_raw, df_sb_raw, output_file):

    # mark timeouts
    if df_base_raw is not None:
        df_base_raw["timeout"] = df_base_raw["solving time"] == -1
    
    if df_sb_raw is not None:
        df_sb_raw["timeout"] = df_sb_raw["solving time"] == -1

    # base counts
    base_group = None
    if df_base_raw is not None:
        base_group = df_base_raw.groupby(["n", "k"]).agg(
            base_timeouts=("timeout", "sum"),
            total=("timeout", "count")
        ).reset_index()

    # sb counts
    sb_group = None
    if df_sb_raw is not None:
        sb_group = df_sb_raw.groupby(["n", "k"]).agg(
            sb_timeouts=("timeout", "sum")
        ).reset_index()

    # merge if both exist
    if base_group is not None and sb_group is not None:
        grouped = base_group.merge(sb_group, on=["n", "k"])
    elif base_group is not None:
        grouped = base_group
        grouped["sb_timeouts"] = "-"
    else:
        grouped = sb_group
        grouped["base_timeouts"] = "-"

    # build LaTeX
    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|cc}")
    lines.append("\\hline")
    lines.append("n & k & Base Timeouts & SB Timeouts \\\\")
    lines.append("\\hline")

    for _, row in grouped.iterrows():
        n = int(row["n"])
        k = int(row["k"])

        base = row.get("base_timeouts", "-")
        sb = row.get("sb_timeouts", "-")

        lines.append(f"{n} & {k} & {base} & {sb} \\\\")

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Number of timeouts per configuration.}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))



def plot_metric(metric, ylabel, title, filename, log_scale=False, only_sb=False):
    plt.figure()

    plt.rcParams.update({
        "font.size": 12,          # general font
        "axes.titlesize": 16,     # title
        "axes.labelsize": 14,     # axis labels
        "legend.fontsize": 12,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14
    })

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
    plt.title(title)
    plt.grid(True)
    
    


    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, filename), bbox_inches='tight')


def plot_stacked_time_shares(term):
    plt.figure(figsize=(12, 6))

    # Sort for consistent ordering
    df = group_sb.sort_values(["n", "k"]).copy()

    # Create labels like (20,2), (40,2), ...
    df["label"] = df.apply(lambda r: f"({int(r['n'])},{int(r['k'])})", axis=1)

    x = range(len(df))

    base = df["base share"]
    scc = df["scc share"]
    sb = df["sb share"]

    # Stacked bars
    plt.bar(x, base, label="Base", color="#4C72B0")
    plt.bar(x, scc, bottom=base, label="SCC", color="#55A868")
    plt.bar(x, sb, bottom=base + scc, label="SB", color="#C44E52")

    # X-axis
    plt.xticks(x, df["label"], rotation=45)
    plt.xlabel("(n, k)")

    # Y-axis
    plt.ylabel("Relative Time Share")
    plt.ylim(0, 1)

    plt.title(f"Relative Propagation Time ({term})")

    plt.legend()
    plt.grid(axis="y")

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, f"{mode}_stacked_time_shares.pdf"))


def generate_time_share_table(df_sb, output_file=f"{mode}_time_share_table.txt"):

    grouped = df_sb.groupby(["n", "k"]).mean().reset_index()

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc}")
    lines.append("\\hline")
    lines.append("n & k & Base (\\%) & Extension (\\%) \\\\")
    lines.append("\\hline")

    for _, row in grouped.iterrows():
        n = int(row["n"])
        k = int(row["k"])

        base = row["base share"] * 100
        ext  = row["ext share"] * 100

        lines.append(
            f"{n} & {k} & {base:.1f} & {ext:.1f} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Normalized distribution of computational effort (in \\%) across base propagation,and strong bridge extension (SB & SCC).}")
    lines.append("\\end{table}")

    # Write to file
    with open(output_file, "w") as f:
        f.write("\n".join(lines))


def generate_latex_table(df_base, df_sb, output_file=f"{mode}_table.txt"):
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



def generate_propagation_table(df_base, df_sb, output_file=f"{mode}_table_prop.txt"):

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


def plot_time_ratios():
    plt.figure()

    ks = sorted(group_sb["k"].unique())
    colors = {k: plt.cm.tab10(i) for i, k in enumerate(ks)}

    for k in ks:
        subset = group_sb[group_sb["k"] == k]

        plt.plot(
            subset["n"],
            subset["base share"],
            linestyle='-',
            marker='o',
            color=colors[k],
            label=f"SB (k={k})"
        )

        plt.plot(
            subset["n"],
            subset["ext share"],
            linestyle='--',
            marker='x',
            color=colors[k],
            label=f"SCC (k={k})"
        )

    plt.xlabel("n")
    plt.ylabel("Time / Total Time")
    plt.title("Relative Propagation Time (SB vs SCC vs Base)")
    plt.grid(True)

    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, f"{mode}_time_ratios.pdf"))


def generate_runtime_table(df_base, df_sb, output_file=f"{mode}_runtime_table.txt"):

    merged = df_base.merge(
        df_sb,
        on=["n", "k", "seed"],
        suffixes=("_base", "_sb")
    )

    grouped = merged.groupby(["n", "k"]).mean().reset_index()

    grouped["time_diff"] = grouped["solving time_base"] - grouped["solving time_sb"]

    grouped["time_reduction"] = (
        grouped["time_diff"] /
        grouped["solving time_base"].replace(0, 1)
    ) * 100

    lines = []

    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc|c}")
    lines.append("\\hline")
    lines.append("n & k & Time (base) & Time (SB) & $\\Delta$ Time & Reduction (\\%) \\\\")
    lines.append("\\hline")

    for _, row in grouped.iterrows():
        n = int(row["n"])
        k = int(row["k"])

        
        base_time = format_time(row["solving time_base"])
        sb_time = format_time(row["solving time_sb"])
        delta_time = format_time(row["time_diff"])
        reduction = round(row["time_reduction"], 1)

        if base_time == 0:
            reduction_str = "--"
        else:
            reduction_str = f"{reduction}"

        lines.append(
            f"{n} & {k} & {base_time} & {sb_time} & {delta_time} & {reduction_str} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Runtime comparison between baseline and strong bridge propagation.}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))



def format_sci(x):
    if x == 0:
        return "0"
    if x < 1000:  # keep small numbers normal
        return f"{x:.1f}"
    
    exponent = int(f"{x:.0e}".split("e")[1])
    base = x / (10 ** exponent)

    return f"{base:.2f} \\times 10^{exponent}"


def format_time(x):
    if x < 0.001:
        return f"{x:.2e}"        # scientific for very small
    elif x < 1:
        return f"{x:.4f}"        # more precision
    else:
        return f"{x:.2f}"        # normal





# Generate plots
term = "Satisfaction" if mode == 'sat' else "Optimization"

plot_metric("conflicts", "Average Conflict Amount", f"Conflicts ({term})", f"{mode}_conflicts.pdf", True)
plot_metric("propagations", "Average Propagation Amount", f"Propagations ({term})", f"{mode}_propagations.pdf", True)
plot_metric("solving time", "Average Runtime (s)", f"Runtime ({term})", f"{mode}_runtime_log.pdf", True)
plot_metric("solving time", "Average Runtime (s)", f"Runtime ({term})", f"{mode}_runtime.pdf")
plot_metric("average lbd", "Average LBD", f"LBD ({term})", f"{mode}_lbd.pdf")
plot_metric("average nogood length", "Average nogood Length", f"Nogood Length ({term})", f"{mode}_nogood.pdf")

if df_base is not None and df_sb is not None:
    generate_latex_table(df_base, df_sb, TABLES_DIR + f"/{mode}_conflicts_table.txt")
    generate_propagation_table(df_base, df_sb, TABLES_DIR + f"/{mode}_propagation_table.txt")
    generate_runtime_table(df_base, df_sb, TABLES_DIR + f"/{mode}_runtime_table.txt")
    generate_time_share_table(df_sb, TABLES_DIR + f"/{mode}_time_share_table.txt")
    generate_timeout_table(df_base_raw, df_sb_raw, TABLES_DIR + f"/{mode}_timeouts_table.txt")



if df_sb is not None:
    plot_time_ratios()
    plot_stacked_time_shares(term)
    plot_metric("sb prop / all prop", "Strong Bridge Propagation Ratio", "Share of Strong Bridge Propagations", f"{mode}_sb_ratio.pdf", only_sb=True)
    plot_metric("scc prop / all prop", "SCC Propagation Ratio", "Share of SCC Propagations", f"{mode}_scc_ratio.pdf", only_sb=True)
    plot_metric("sb propagations", "Average Strong Bridge Propagation Amount", "Strong Bridge Propagation Count", f"{mode}_sb.pdf", only_sb=True, log_scale=True)
    plot_metric("scc propagations", "Average SCC Propagation Amount", "SCC Propagation Count", f"{mode}_scc.pdf", only_sb=True, log_scale=True)




print("\nAnalysis complete")


