from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 20260825
N_STUDENTS = 300
N_LESSONS = 6

ROOT = Path(__file__).resolve().parents[1] / "testdata" / "pilot_300"
LESSONS = ROOT / "lessons"
ECONLENS = ROOT / "econlens"
EDULAB = ROOT / "edulab"

rng = random.Random(SEED)


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ------------------------------------------------------------
# Reset/create directories
# ------------------------------------------------------------

for p in [ROOT, LESSONS, ECONLENS, EDULAB]:
    p.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 1. Roster
# ------------------------------------------------------------

students = []

for i in range(1, N_STUDENTS + 1):
    sid = f"S{i:03d}"

    # Exactly 120 EAL / 180 non-EAL.
    eal = i <= 120

    # Broad readiness distribution.
    r = rng.random()

    if r < 0.20:
        mastery = rng.uniform(0.20, 0.39)
    elif r < 0.45:
        mastery = rng.uniform(0.40, 0.59)
    elif r < 0.75:
        mastery = rng.uniform(0.60, 0.79)
    elif r < 0.93:
        mastery = rng.uniform(0.80, 0.94)
    else:
        mastery = rng.uniform(0.95, 1.00)

    # Deliberate boundary cases.
    if i == 18:
        mastery = 0.86
    elif i == 37:
        mastery = 0.91
    elif i == 74:
        mastery = 0.44
    elif i == 121:
        mastery = 0.39

    tier = (
        "t1" if mastery < 0.50
        else "t2" if mastery < 0.80
        else "t3"
    )

    students.append({
        "student_id": sid,
        "name": f"Student {i:03d}",
        "eal": str(eal).lower(),
        "language_support": str(eal).lower(),
        "initial_mastery": round(mastery, 3),
        "initial_tier": tier,
        "fixture": "synthetic_test_data",
    })


write_csv(
    ROOT / "roster.csv",
    students,
    list(students[0].keys()),
)


# ------------------------------------------------------------
# 2. Unified assessment taxonomy
# ------------------------------------------------------------

items = []

for i in range(1, 16):
    if i <= 5:
        function = "concept"
    elif i <= 10:
        function = "calculate"
    else:
        function = "interpret"

    items.append({
        "item": f"q{i}",
        "function": function,
    })

write_csv(
    ROOT / "items.csv",
    items,
    ["item", "function"],
)


# ------------------------------------------------------------
# 3. Deliberate student profiles
# ------------------------------------------------------------

special_profiles = {
    # High overall readiness, persistent interpretation weakness.
    "S018": {"calculate": 1.00, "concept": 1.00, "interpret": 0.58},
    "S037": {"calculate": 1.00, "concept": 0.95, "interpret": 0.50},
    "S091": {"calculate": 0.95, "concept": 1.00, "interpret": 0.55},

    # Strong conceptual understanding but weak calculation.
    "S044": {"calculate": 0.30, "concept": 1.00, "interpret": 0.80},
    "S117": {"calculate": 0.25, "concept": 0.95, "interpret": 0.75},

    # Strong language support but low readiness.
    "S074": {"calculate": 0.30, "concept": 0.40, "interpret": 0.20},
    "S121": {"calculate": 0.35, "concept": 0.35, "interpret": 0.25},

    # EAL high performers.
    "S005": {"calculate": 1.00, "concept": 1.00, "interpret": 1.00},
    "S031": {"calculate": 0.90, "concept": 1.00, "interpret": 0.95},
    "S096": {"calculate": 1.00, "concept": 0.95, "interpret": 0.95},
}


def clamp(x):
    return max(0.0, min(1.0, x))


def profile_for(student):
    sid = student["student_id"]

    if sid in special_profiles:
        return special_profiles[sid].copy()

    # Base profile around initial mastery with realistic variation.
    m = student["initial_mastery"]

    concept = clamp(m + rng.uniform(-0.12, 0.12))
    calculate = clamp(m + rng.uniform(-0.15, 0.15))
    interpret = clamp(m + rng.uniform(-0.18, 0.12))

    return {
        "concept": round(concept, 3),
        "calculate": round(calculate, 3),
        "interpret": round(interpret, 3),
    }


base_profiles = {
    s["student_id"]: profile_for(s)
    for s in students
}


# ------------------------------------------------------------
# 4. Lesson results
# ------------------------------------------------------------

lesson_rows = {n: [] for n in range(1, N_LESSONS + 1)}

for lesson in range(1, N_LESSONS + 1):

    for student in students:
        sid = student["student_id"]
        profile = base_profiles[sid]

        # Deliberate absences.
        absent = (
            (lesson == 2 and int(sid[1:]) % 17 == 0)
            or (lesson == 4 and int(sid[1:]) % 29 == 0)
        )

        if absent:
            lesson_rows[lesson].append({
                "student_id": sid,
                "lesson": lesson,
                "absent": "true",
                "score": "",
                "concept": "",
                "calculate": "",
                "interpret": "",
                "tier": student["initial_tier"],
                "fixture": "synthetic_test_data",
            })
            continue

        # General learning progression.
        improvement = (lesson - 1) * 0.025

        # Create three broad experimental trajectories.
        group = int(sid[1:]) % 6

        if group in (0, 1):
            improvement += (lesson - 1) * 0.018
        elif group in (2, 3):
            improvement -= (lesson - 1) * 0.002
        else:
            improvement += (lesson - 1) * 0.005

        concept = clamp(profile["concept"] + improvement)
        calculate = clamp(profile["calculate"] + improvement)
        interpret = clamp(profile["interpret"] + improvement)

        # Persistent weakness cohort.
        if sid in {"S018", "S037", "S091"}:
            interpret = clamp(profile["interpret"] - (lesson - 1) * 0.01)

        # Persistent calculation weakness.
        if sid in {"S044", "S117"}:
            calculate = clamp(profile["calculate"] - (lesson - 1) * 0.005)

        score = (concept + calculate + interpret) / 3

        tier = (
            "t1" if score < 0.50
            else "t2" if score < 0.80
            else "t3"
        )

        lesson_rows[lesson].append({
            "student_id": sid,
            "lesson": lesson,
            "absent": "false",
            "score": round(score, 3),
            "concept": round(concept, 3),
            "calculate": round(calculate, 3),
            "interpret": round(interpret, 3),
            "tier": tier,
            "fixture": "synthetic_test_data",
        })


for lesson, rows in lesson_rows.items():
    write_csv(
        LESSONS / f"lesson_{lesson:02d}.csv",
        rows,
        [
            "student_id",
            "lesson",
            "absent",
            "score",
            "concept",
            "calculate",
            "interpret",
            "tier",
            "fixture",
        ],
    )


# ------------------------------------------------------------
# 5. Teacher overrides
# ------------------------------------------------------------

overrides = [
    {
        "lesson": 2,
        "student_id": "S074",
        "from_tier": "t1",
        "to_tier": "t2",
        "reason": (
            "Oral explanation demonstrates secure conceptual understanding; "
            "written response is limiting evidence rather than readiness."
        ),
        "fixture": "synthetic_test_data",
    },
    {
        "lesson": 3,
        "student_id": "S117",
        "from_tier": "t2",
        "to_tier": "t3",
        "reason": (
            "Teacher conference confirms calculation procedure is secure; "
            "written timing caused the low recorded score."
        ),
        "fixture": "synthetic_test_data",
    },
    {
        "lesson": 4,
        "student_id": "S044",
        "from_tier": "t2",
        "to_tier": "t3",
        "reason": (
            "Teacher observation confirms conceptual and interpretive readiness; "
            "calculation error was procedural and independently corrected."
        ),
        "fixture": "synthetic_test_data",
    },
]

write_csv(
    ROOT / "overrides.csv",
    overrides,
    [
        "lesson",
        "student_id",
        "from_tier",
        "to_tier",
        "reason",
        "fixture",
    ],
)


# ------------------------------------------------------------
# 6. Absence index
# ------------------------------------------------------------

absences = []

for lesson, rows in lesson_rows.items():
    for row in rows:
        if row["absent"] == "true":
            absences.append({
                "lesson": lesson,
                "student_id": row["student_id"],
                "reason": "scheduled absence",
                "fixture": "synthetic_test_data",
            })

write_csv(
    ROOT / "absences.csv",
    absences,
    ["lesson", "student_id", "reason", "fixture"],
)


# ------------------------------------------------------------
# 7. EconLens cases
# ------------------------------------------------------------

rq_cases = [
    {
        "id": "RQ001",
        "text": "How does the sugar tax affect consumption of sugary drinks?",
        "expected": "pass_or_info",
    },
    {
        "id": "RQ002",
        "text": "Is the sugar tax good?",
        "expected": "needs_work",
    },
    {
        "id": "RQ003",
        "text": "How does the tax affect price elasticity of demand for sugary drinks?",
        "expected": "pass",
    },
]

claim_cases = [
    {
        "id": "CL001",
        "draft": (
            "The tax increases price and reduces quantity demanded. "
            "Therefore, consumption falls."
        ),
        "expected": "supported_or_partially_supported",
    },
    {
        "id": "CL002",
        "draft": (
            "The tax reduced sales by 20%. Therefore, it improved welfare for everyone."
        ),
        "expected": "overreach",
    },
    {
        "id": "CL003",
        "draft": (
            "Sales fell by 20%. However, the evidence does not isolate the tax effect."
        ),
        "expected": "mastery_aware",
    },
]

evaluation_cases = [
    {
        "id": "EV001",
        "draft": (
            "The tax raises price, which reduces quantity demanded. "
            "Lower consumption may reduce the external cost. "
            "Therefore, the policy is effective."
        ),
        "expected": "check_mechanism_consequence_judgement",
    },
    {
        "id": "EV002",
        "draft": (
            "The tax is effective because sales fell. "
            "Therefore, the government should increase it."
        ),
        "expected": "missing_evaluation_chain",
    },
]

draft_cases = [
    {
        "id": "DR001",
        "draft": (
            "The tax increases price. Quantity demanded falls. "
            "This may reduce consumption, although other factors could also explain the change."
        ),
        "expected": "good_with_opportunity",
    },
    {
        "id": "DR002",
        "draft": (
            "The tax definitely improves welfare for every stakeholder."
        ),
        "expected": "critical_overreach",
    },
]

write_json(ECONLENS / "rq_cases.json", rq_cases)
write_json(ECONLENS / "claim_cases.json", claim_cases)
write_json(ECONLENS / "evaluation_cases.json", evaluation_cases)
write_json(ECONLENS / "draft_cases.json", draft_cases)


# ------------------------------------------------------------
# 8. edulab cohort
# ------------------------------------------------------------

cohorts = []

for i, student in enumerate(students, start=1):
    cohorts.append({
        "student_id": student["student_id"],
        "cohort": "treatment" if i % 2 else "control",
        "assignment": "individual_randomized",
        "seed": SEED,
        "fixture": "synthetic_test_data",
    })

write_csv(
    EDULAB / "cohorts.csv",
    cohorts,
    [
        "student_id",
        "cohort",
        "assignment",
        "seed",
        "fixture",
    ],
)


# ------------------------------------------------------------
# 9. edulab pre/post
# ------------------------------------------------------------

pre_rows = []
post_rows = []

for student in students:
    sid = student["student_id"]
    base = student["initial_mastery"]

    # Product metric deliberately separate from learning metric.
    pre_learning = round(base * 100, 2)

    cohort = next(
        x["cohort"]
        for x in cohorts
        if x["student_id"] == sid
    )

    if cohort == "treatment":
        gain = rng.uniform(8, 22)
        engagement_gain = rng.uniform(10, 30)
    else:
        gain = rng.uniform(2, 12)
        engagement_gain = rng.uniform(3, 15)

    post_learning = min(100, round(pre_learning + gain, 2))

    pre_rows.append({
        "student_id": sid,
        "learning_score": pre_learning,
        "product_engagement": round(rng.uniform(40, 80), 2),
        "fixture": "synthetic_test_data",
    })

    post_rows.append({
        "student_id": sid,
        "learning_score": post_learning,
        "product_engagement": round(
            rng.uniform(40, 80) + engagement_gain,
            2,
        ),
        "fixture": "synthetic_test_data",
    })


write_csv(
    EDULAB / "pre.csv",
    pre_rows,
    ["student_id", "learning_score", "product_engagement", "fixture"],
)

write_csv(
    EDULAB / "post.csv",
    post_rows,
    ["student_id", "learning_score", "product_engagement", "fixture"],
)


# ------------------------------------------------------------
# 10. Manifest
# ------------------------------------------------------------

manifest = {
    "fixture": "pilot_300",
    "type": "synthetic_test_data",
    "seed": SEED,
    "students": N_STUDENTS,
    "eal_students": 120,
    "non_eal_students": 180,
    "lessons": N_LESSONS,
    "assessment_functions": [
        "concept",
        "calculate",
        "interpret",
    ],
    "contains": {
        "absences": len(absences),
        "teacher_overrides": len(overrides),
        "econlens_rq_cases": len(rq_cases),
        "econlens_claim_cases": len(claim_cases),
        "econlens_evaluation_cases": len(evaluation_cases),
        "econlens_draft_cases": len(draft_cases),
        "edulab_students": N_STUDENTS,
    },
    "do_not_present_as_real_classroom_evidence": True,
}

write_json(ROOT / "manifest.json", manifest)


print(f"Generated synthetic fixture: {ROOT}")
print(f"Students: {N_STUDENTS}")
print(f"Lessons: {N_LESSONS}")
print(f"Absences: {len(absences)}")
print(f"Overrides: {len(overrides)}")
print("Functions: concept / calculate / interpret")
print(f"Seed: {SEED}")
