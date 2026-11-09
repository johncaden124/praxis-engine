"""Challenge 2 — CSV & Descriptive Stats (Stage 1) → benchmark s1_csv

Dataset: _assets/survey_stage1.csv (a synthetic social-media & wellbeing survey).
1. Load it with pandas.
2. Drop rows where wellbeing_score or hours_social_media is missing/corrupt.
3. Compute the mean and standard deviation of wellbeing_score.
4. Run a Welch t-test: does wellbeing differ between "treatment" and "control"?
5. Save a plot (shown in the game) and submit_result(mean=..., std=..., p_value=...).

This file is a worked example so you can see the challenge pass.
To earn s1_csv honestly: delete it and rewrite it from a blank file.
"""
import math

import pandas as pd

from station_api import dataset_path, log, plot_csv, submit_result

df = pd.read_csv(dataset_path("survey_stage1.csv"))
log(f"Loaded {len(df)} rows")

df["wellbeing_score"] = pd.to_numeric(df["wellbeing_score"], errors="coerce")
df["hours_social_media"] = pd.to_numeric(df["hours_social_media"], errors="coerce")
clean = df.dropna(subset=["wellbeing_score", "hours_social_media"])
log(f"{len(df) - len(clean)} corrupted rows removed")

mean = clean["wellbeing_score"].mean()
std = clean["wellbeing_score"].std()  # sample std (ddof=1)

a = clean.loc[clean["group"] == "treatment", "wellbeing_score"]
b = clean.loc[clean["group"] == "control", "wellbeing_score"]
se = math.sqrt(a.var() / len(a) + b.var() / len(b))
t = (a.mean() - b.mean()) / se
try:
    from scipy import stats

    p = stats.ttest_ind(a, b, equal_var=False).pvalue
except ImportError:
    # Normal approximation (fine for n > 100 per group)
    p = math.erfc(abs(t) / math.sqrt(2))
log(f"t = {t:.2f}, p = {p:.4g}")

plot_csv(dataset_path("survey_stage1.csv"), x="hours_social_media", y="wellbeing_score")
submit_result(mean=mean, std=std, p_value=p)
