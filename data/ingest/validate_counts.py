from __future__ import annotations

import sys
from pathlib import Path

from data.ingest.ingest_courses import parse_classes

EXPECTED_COURSES = 3410  # 3735 raw entries, deduplicated by course code (topics courses)
EXPECTED_SECTIONS = 13223
EXPECTED_DEPARTMENTS = 152


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "cu_classes.json"
    courses, sections = parse_classes(path)

    results: list[tuple[str, bool]] = []

    # --- Count checks ---
    actual_courses = len(courses)
    actual_sections = len(sections)
    actual_depts = len({c["dept"] for c in courses})

    results.append((
        f"Course count == {EXPECTED_COURSES} (got {actual_courses})",
        actual_courses == EXPECTED_COURSES,
    ))
    results.append((
        f"Section count == {EXPECTED_SECTIONS} (got {actual_sections})",
        actual_sections == EXPECTED_SECTIONS,
    ))
    results.append((
        f"Department count == {EXPECTED_DEPARTMENTS} (got {actual_depts})",
        actual_depts == EXPECTED_DEPARTMENTS,
    ))

    # --- All CRNs are numeric strings ---
    non_numeric_crns = [s["crn"] for s in sections if not s["crn"].isdigit()]
    results.append(
        (
            f"All CRNs are numeric strings ({len(non_numeric_crns)} non-numeric found)",
            len(non_numeric_crns) == 0,
        )
    )

    # --- All course codes are unique ---
    codes = [c["code"] for c in courses]
    duplicate_codes = [code for code in set(codes) if codes.count(code) > 1]
    results.append(
        (
            f"All course codes are unique ({len(duplicate_codes)} duplicates found)",
            len(duplicate_codes) == 0,
        )
    )

    # --- Anomaly flags (informational, not PASS/FAIL) ---
    empty_titles = [c["code"] for c in courses if not c["title"].strip()]
    empty_descriptions = [c["code"] for c in courses if not c["description"].strip()]
    empty_codes = [c["code"] for c in courses if not c["code"].strip()]

    topics_courses = [c for c in courses if c["topic_titles"]]
    total_topic_titles = sum(len(c["topic_titles"].split("|")) for c in topics_courses)

    print("=" * 60)
    print("CUAI-20 Acceptance Criteria Validation")
    print("=" * 60)

    all_passed = True
    for label, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")
        if not passed:
            all_passed = False

    print()
    print("Anomaly Report (informational):")
    print(f"  Courses with empty titles:       {len(empty_titles)}")
    print(f"  Courses with empty descriptions: {len(empty_descriptions)}")
    print(f"  Courses with empty codes:        {len(empty_codes)}")
    print(
        f"  [INFO] Courses with topic variants: {len(topics_courses)}"
        f" (total topic titles: {total_topic_titles})"
    )

    print()
    print("=" * 60)
    if all_passed:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
