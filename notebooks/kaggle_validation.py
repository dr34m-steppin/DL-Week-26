"""
Optional evidence script:
- Downloads ASSISTments-style data from Kaggle
- Applies simple topic mastery aggregation
- Prints summary statistics

Run (after kagglehub install):
  pip install kagglehub pandas
  python notebooks/kaggle_validation.py
"""

from collections import defaultdict


def main() -> None:
    import kagglehub
    import pandas as pd

    path = kagglehub.dataset_download("nicolaswattiez/skillbuilder-data-2009-2010")
    print("Dataset path:", path)

    csv_files = [
        f for f in __import__("pathlib").Path(path).glob("*.csv")
    ]
    if not csv_files:
        raise RuntimeError("No CSV files found in downloaded dataset")

    df = pd.read_csv(csv_files[0])
    required = ["user_id", "skill", "correct"]
    for col in required:
        if col not in df.columns:
            raise RuntimeError(f"Missing required column: {col}")

    df = df.dropna(subset=["user_id", "skill", "correct"]).copy()
    df["correct"] = df["correct"].astype(int)

    by_user_topic = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for _, row in df.iterrows():
        key = (int(row["user_id"]), str(row["skill"]))
        by_user_topic[key]["attempts"] += 1
        by_user_topic[key]["correct"] += int(row["correct"])

    rows = []
    for (user_id, topic), stats in by_user_topic.items():
        attempts = stats["attempts"]
        correct = stats["correct"]
        mastery = (correct + 1) / (attempts + 2)
        rows.append((user_id, topic, attempts, correct, round(mastery, 4)))

    out = pd.DataFrame(rows, columns=["user_id", "topic", "attempts", "correct", "mastery"])
    print(out.head(10))
    print("Rows:", len(out))
    print("Mean mastery:", out["mastery"].mean())


if __name__ == "__main__":
    main()
