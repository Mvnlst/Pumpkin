import csv

base_file = "../experiments/experiment420/sat/results_base_seed420.csv"
sb_file = "../experiments/experiment420/sat/results_sb_seed420.csv"
output_file = "../experiments/experiment420/sat/base_filtered.csv"

# Step 1: collect (n, k, seed) from sb.csv
valid_keys = set()

with open(sb_file, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        key = (row["n"], row["k"], row["seed"])
        valid_keys.add(key)

# Step 2: filter base.csv
with open(base_file, "r") as infile, open(output_file, "w", newline="") as outfile:
    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)

    writer.writeheader()

    for row in reader:
        key = (row["n"], row["k"], row["seed"])
        if key in valid_keys:
            writer.writerow(row)

print(f"Filtered file written to {output_file}")
