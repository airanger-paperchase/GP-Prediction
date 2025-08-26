# build_artifacts.py
import argparse, os, json
from shared_setup import load_label_csv, build_lookups, build_hierarchical_json, build_descriptions_from_hierarchy, save_json

def main(csv_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    df = load_label_csv(csv_path)
    exact_lookup, examples, parents, grandparents = build_lookups(df)
    hier = build_hierarchical_json(df)
    descriptions = build_descriptions_from_hierarchy(hier)

    # Save artifacts
    save_json(hier, os.path.join(outdir, "hierarchy.json"))
    save_json(exact_lookup, os.path.join(outdir, "exact_lookup.json"))
    save_json(descriptions, os.path.join(outdir, "descriptions.json"))

    print("Artifacts saved to:", outdir)
    print(f"hierarchy top-level keys: {len(hier)}; exact_lookup entries: {len(exact_lookup)}; descriptions: {len(descriptions)}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, help="labeled CSV path")
    p.add_argument("--outdir", required=True, help="output artifacts directory")
    args = p.parse_args()
    main(args.csv, args.outdir)
