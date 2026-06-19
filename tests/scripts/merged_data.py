import pandas as pd
import sys
import os

OUTPUT_DIR = ""


def remove_timeouts(df):
    return df[df["solving time"] != -1]

def load_grouped(path_base, path_sb):
    base = pd.read_csv(path_base, on_bad_lines='skip')
    sb = pd.read_csv(path_sb, on_bad_lines='skip')

    
    base = remove_timeouts(base)
    sb   = remove_timeouts(sb)


    merged = base.merge(sb, on=["n", "k", "seed"], suffixes=("_base", "_sb"))
    grouped = merged.groupby(["n", "k"]).mean().reset_index()

    return grouped


def get_all_keys(df1, df2):
    return (
        pd.concat([df1[["n", "k"]], df2[["n", "k"]]])
        .drop_duplicates()
        .sort_values(["n", "k"])
        .reset_index(drop=True)
    )


def get_row(df, n, k):
    row = df[(df["n"] == n) & (df["k"] == k)]
    return None if row.empty else row.iloc[0]


def safe_reduction(base, sb):
    if base is None or sb is None:
        return "-"
    if base == 0:
        return "-"
    return f"{(base - sb) / base * 100:.1f}"




def format_sci(x):
    if x == 0:
        return "0"

    if abs(x) < 1e4:
        return f"{x:.1f}"

    exponent = int(f"{x:.0e}".split("e")[1])
    base = x / (10 ** exponent)

    return f"${base:.2f} \\times 10^{{{exponent}}}$"

def format_time(x):
    if x < 0.001:
        return f"{x:.2e}"        # scientific for very small
    elif x < 1:
        return f"{x:.4f}"        # more precision
    else:
        return f"{x:.2f}"        # normal

def safe_format(x):
    if x == "-" or x is None:
        return "-"
    return format_sci(x)


def generate_conflict_table(sat, opt, output_file):

    keys = get_all_keys(sat, opt)

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc|ccc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{3}{c|}{SAT} & \\multicolumn{3}{c}{OPT} \\\\")
    lines.append("n & k & Base & SB & (\\%) & Base & SB & (\\%) \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_row = get_row(sat, n, k)
        opt_row = get_row(opt, n, k)

        # SAT
        if sat_row is None:
            sat_base, sat_sb, sat_red = "-", "-", "-"
        else:
            
            raw_base = sat_row["conflicts_base"]
            raw_sb   = sat_row["conflicts_sb"]

            sat_red  = safe_reduction(raw_base, raw_sb)

            sat_base = safe_format(raw_base)
            sat_sb   = safe_format(raw_sb)


        # OPT
        if opt_row is None:
            opt_base, opt_sb, opt_red = "-", "-", "-"
        else:

            raw_base = opt_row["conflicts_base"]
            raw_sb   = opt_row["conflicts_sb"]

            opt_red  = safe_reduction(raw_base, raw_sb)

            opt_base = safe_format(raw_base)
            opt_sb   = safe_format(raw_sb)


        lines.append(
            f"{n} & {k} & {sat_base} & {sat_sb} & {sat_red} "
            f"& {opt_base} & {opt_sb} & {opt_red} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Conflict reduction (SAT vs OPT).}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

def generate_sb_scc_table(sat_sb_path, opt_sb_path, output_file):

    def prepare(path):
        df = pd.read_csv(path, on_bad_lines='skip')

        # average per (n,k)
        grouped = df.groupby(["n", "k"]).mean().reset_index()

        return grouped

    sat = prepare(sat_sb_path)
    opt = prepare(opt_sb_path)

    keys = get_all_keys(sat, opt)

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|cc|cc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{2}{c|}{SAT} & \\multicolumn{2}{c}{OPT} \\\\")
    lines.append("n & k & SB (\\%) & SCC (\\%) & SB (\\%) & SCC (\\%) \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_row = get_row(sat, n, k)
        opt_row = get_row(opt, n, k)

        # SAT
        if sat_row is None:
            sat_sb_ratio, sat_scc_ratio = "-", "-"
        else:
            total = sat_row["propagations"]

            if total > 0:
                sb_ratio  = sat_row["sb propagations"] / total * 100
                scc_ratio = sat_row["scc propagations"] / total * 100
                sat_sb_ratio  = f"{sb_ratio:.1f}"
                sat_scc_ratio = f"{scc_ratio:.1f}"
            else:
                sat_sb_ratio, sat_scc_ratio = "-", "-"

        # OPT
        if opt_row is None:
            opt_sb_ratio, opt_scc_ratio = "-", "-"
        else:
            total = opt_row["propagations"]

            if total > 0:
                sb_ratio  = opt_row["sb propagations"] / total * 100
                scc_ratio = opt_row["scc propagations"] / total * 100
                opt_sb_ratio  = f"{sb_ratio:.1f}"
                opt_scc_ratio = f"{scc_ratio:.1f}"
            else:
                opt_sb_ratio, opt_scc_ratio = "-", "-"

        lines.append(
            f"{n} & {k} & {sat_sb_ratio} & {sat_scc_ratio} "
            f"& {opt_sb_ratio} & {opt_scc_ratio} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Relative frequency of strong bridge (SB) and SCC propagations as a percentage of total propagations.}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))


def generate_prop_table(sat, opt, output_file):

    keys = get_all_keys(sat, opt)

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc|ccc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{3}{c|}{SAT} & \\multicolumn{3}{c}{OPT} \\\\")
    lines.append("n & k & Base & SB & (\\%) & Base & SB & (\\%) \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_row = get_row(sat, n, k)
        opt_row = get_row(opt, n, k)

        # SAT
        if sat_row is None:
            sat_base, sat_sb, sat_red = "-", "-", "-"
        else:

            raw_base = sat_row["propagations_base"]
            raw_sb   = sat_row["propagations_sb"]

            sat_red  = safe_reduction(raw_base, raw_sb)

            sat_base = safe_format(raw_base)
            sat_sb   = safe_format(raw_sb)


        # OPT
        if opt_row is None:
            opt_base, opt_sb, opt_red = "-", "-", "-"
        else:

            raw_base = opt_row["propagations_base"]
            raw_sb   = opt_row["propagations_sb"]

            opt_red  = safe_reduction(raw_base, raw_sb)

            opt_base = safe_format(raw_base)
            opt_sb   = safe_format(raw_sb)


        lines.append(
            f"{n} & {k} & {sat_base} & {sat_sb} & {sat_red} "
            f"& {opt_base} & {opt_sb} & {opt_red} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Propagation reduction (SAT vs OPT).}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))


def count_timeouts(df):
    df = df.copy()
    df["timeout"] = df["solving time"] == -1
    return df.groupby(["n", "k"])["timeout"].sum().reset_index()


def safe_int(x):
    return "-" if pd.isna(x) else int(x)


def generate_timeout_table(sat_base, sat_sb, opt_base, opt_sb, output_file):

    sat_base = count_timeouts(sat_base)
    sat_sb = count_timeouts(sat_sb)
    opt_base = count_timeouts(opt_base)
    opt_sb = count_timeouts(opt_sb)

    
    keys = get_all_keys(
        get_all_keys(sat_base, sat_sb),
        get_all_keys(opt_base, opt_sb)
    )


    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|cc|cc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{2}{c|}{SAT} & \\multicolumn{2}{c}{OPT} \\\\")
    lines.append("n & k & Base & SB & Base & SB \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_b = get_row(sat_base, n, k)
        sat_s = get_row(sat_sb, n, k)
        opt_b = get_row(opt_base, n, k)
        opt_s = get_row(opt_sb, n, k)

        lines.append(
            f"{n} & {k} & "
            f"{safe_int(sat_b['timeout']) if sat_b is not None else '-'} & "
            f"{safe_int(sat_s['timeout']) if sat_s is not None else '-'} & "
            f"{safe_int(opt_b['timeout']) if opt_b is not None else '-'} & "
            f"{safe_int(opt_s['timeout']) if opt_s is not None else '-'} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Timeout counts (SAT vs OPT).}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

def generate_runtime_table(sat, opt, output_file):

    keys = get_all_keys(sat, opt)

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|ccc|ccc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{3}{c|}{SAT} & \\multicolumn{3}{c}{OPT} \\\\")
    lines.append("n & k & Base (s) & SB (s) & (\\%) & Base (s) & SB (s) & (\\%) \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_row = get_row(sat, n, k)
        opt_row = get_row(opt, n, k)

        # SAT
        if sat_row is None:
            sat_base, sat_sb, sat_red = "-", "-", "-"
        else:
            raw_base = sat_row["solving time_base"]
            raw_sb   = sat_row["solving time_sb"]

            sat_red  = safe_reduction(raw_base, raw_sb)

            sat_base = format_time(raw_base)
            sat_sb   = format_time(raw_sb)

        # OPT
        if opt_row is None:
            opt_base, opt_sb, opt_red = "-", "-", "-"
        else:
            raw_base = opt_row["solving time_base"]
            raw_sb   = opt_row["solving time_sb"]

            opt_red  = safe_reduction(raw_base, raw_sb)

            opt_base = format_time(raw_base)
            opt_sb   = format_time(raw_sb)

        lines.append(
            f"{n} & {k} & {sat_base} & {sat_sb} & {sat_red} "
            f"& {opt_base} & {opt_sb} & {opt_red} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Runtime comparison (SAT vs OPT).}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))


def generate_lbd_ng_table(sat, opt, output_file):

    keys = get_all_keys(sat, opt)

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|cc|cc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{2}{c|}{SAT} & \\multicolumn{2}{c}{OPT} \\\\")
    lines.append("n & k & LBD (\\%) & NG (\\%) & LBD (\\%) & NG (\\%) \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_row = get_row(sat, n, k)
        opt_row = get_row(opt, n, k)

        # ----- SAT -----
        if sat_row is None:
            sat_lbd, sat_ng = "-", "-"
        else:
            sat_lbd = safe_reduction(
                sat_row["average lbd_base"],
                sat_row["average lbd_sb"]
            )
            sat_ng = safe_reduction(
                sat_row["average nogood length_base"],
                sat_row["average nogood length_sb"]
            )

        # ----- OPT -----
        if opt_row is None:
            opt_lbd, opt_ng = "-", "-"
        else:
            opt_lbd = safe_reduction(
                opt_row["average lbd_base"],
                opt_row["average lbd_sb"]
            )
            opt_ng = safe_reduction(
                opt_row["average nogood length_base"],
                opt_row["average nogood length_sb"]
            )

        lines.append(
            f"{n} & {k} & {sat_lbd} & {sat_ng} & {opt_lbd} & {opt_ng} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\caption{Relative change in LBD and nogood length (SAT vs OPT). Negative values indicate an increase.}")
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

def generate_time_shift_table(sat_base_path, sat_sb_path,
                              opt_base_path, opt_sb_path,
                              output_file):

    def prepare_base(path):
        df = pd.read_csv(path, on_bad_lines='skip')
        df = remove_timeouts(df)

        total = df["solving time"]
        base  = df["base time"]

        df["f_base"]  = base / total
        df["f_other"] = 1 - df["f_base"]

        grouped = df.groupby(["n", "k"])[["f_base", "f_other"]].mean().reset_index()
        return grouped

    def prepare_ext(path):
        df = pd.read_csv(path, on_bad_lines='skip')
        df = remove_timeouts(df)

        total = df["solving time"]
        base  = df["base time"]
        sb    = df["sb time"]
        scc   = df["scc time"]

        # Avoid division errors
        total = total.replace(0, 1e-9)

        df["f_base"] = base / total
        df["f_sb"]   = sb   / total
        df["f_scc"]  = scc  / total

        # clamp sum to <= 1 (handles instrumentation overlaps)
        df["sum_prop"] = df["f_base"] + df["f_sb"] + df["f_scc"]
        df["sum_prop"] = df["sum_prop"].clip(upper=1.0)

        df["f_other"] = 1 - df["sum_prop"]

        grouped = df.groupby(["n", "k"])[
            ["f_base", "f_sb", "f_scc", "f_other"]
        ].mean().reset_index()

        return grouped

    # prepare datasets
    sat_base = prepare_base(sat_base_path)
    sat_ext  = prepare_ext(sat_sb_path)

    opt_base = prepare_base(opt_base_path)
    opt_ext  = prepare_ext(opt_sb_path)

    keys = get_all_keys(sat_base, sat_ext)

    lines = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\begin{tabular}{cc|cc|cccc}")
    lines.append("\\hline")
    lines.append(" &  & \\multicolumn{2}{c|}{Baseline} & \\multicolumn{4}{c}{Extension} \\\\")
    lines.append("n & k & Prop & Other & Base & SB & SCC & Other \\\\")
    lines.append("\\hline")

    for _, key in keys.iterrows():
        n, k = int(key["n"]), int(key["k"])

        sat_b = get_row(sat_base, n, k)
        sat_e = get_row(sat_ext, n, k)

        if sat_b is None:
            base_vals = ["-", "-"]
        else:
            base_vals = [
                f"{sat_b['f_base']*100:.1f}",
                f"{sat_b['f_other']*100:.1f}",
            ]

        if sat_e is None:
            ext_vals = ["-"] * 4
        else:
            ext_vals = [
                f"{sat_e['f_base']*100:.1f}",
                f"{sat_e['f_sb']*100:.1f}",
                f"{sat_e['f_scc']*100:.1f}",
                f"{sat_e['f_other']*100:.1f}",
            ]

        lines.append(
            f"{n} & {k} & " +
            " & ".join(base_vals) +
            " & " +
            " & ".join(ext_vals) +
            " \\\\"
        )

    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append(
        "\\caption{Shift in runtime distribution between baseline and strong bridge extension (in \\%). Baseline spends most time outside propagation, while the extension shifts computation toward SB and SCC propagation.}"
    )
    lines.append("\\end{table}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))



if len(sys.argv) < 5:
    raise ValueError("Usage: python merged_data.py <sat_base> <sat_sb> <opt_base> <opt_sb>")

sat_base = sys.argv[1]
sat_sb   = sys.argv[2]

opt_base = sys.argv[3]
opt_sb   = sys.argv[4]


sat_group = load_grouped(sat_base, sat_sb)
opt_group = load_grouped(opt_base, opt_sb)

OUTPUT_DIR = os.path.dirname(sat_base) + "/../merged_analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)

generate_conflict_table(sat_group, opt_group, f"{OUTPUT_DIR}/conflicts_merged.txt")
generate_prop_table(sat_group, opt_group, f"{OUTPUT_DIR}/propagations_merged.txt")

generate_timeout_table(
    pd.read_csv(sat_base, on_bad_lines='skip'),
    pd.read_csv(sat_sb, on_bad_lines='skip'),
    pd.read_csv(opt_base, on_bad_lines='skip'),
    pd.read_csv(opt_sb, on_bad_lines='skip'),
    f"{OUTPUT_DIR}/timeouts_merged.txt"
)


generate_sb_scc_table(
    sat_sb,
    opt_sb,
    f"{OUTPUT_DIR}/sb_scc_merged.txt"
)


generate_runtime_table(sat_group, opt_group, f"{OUTPUT_DIR}/runtime_merged.txt")

generate_lbd_ng_table(
    sat_group,
    opt_group,
    f"{OUTPUT_DIR}/lbd_ng_merged.txt"
)


generate_time_shift_table(
    sat_base,
    sat_sb,
    opt_base,
    opt_sb,
    f"{OUTPUT_DIR}/time_breakdown.txt"
)


print("Merged tables generated")