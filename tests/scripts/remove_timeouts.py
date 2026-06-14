import csv

file = "../experiments/experiment420/sat/results_sb_seed420.csv"
output_file = "../experiments/experiment420/sat/sb_no_timeouts.csv"

# Step 1: collect (n, k, seed) from sb.csv
valid_keys = set()

# Step 2: filter base.csv
with open(file, "r") as infile, open(output_file, "w", newline="") as outfile:
    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)

    writer.writeheader()
    
    for row in reader:
            # Keep only rows where nodes != -1, so no timeouts
            if row["nodes"] != "-1":
                writer.writerow(row)

print(f"Filtered file written to {output_file}")
