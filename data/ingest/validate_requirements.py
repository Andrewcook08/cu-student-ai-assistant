from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from data.ingest.ingest_requirements import parse_requirements

EXPECTED_PROGRAMS = 203
EXPECTED_REQUIREMENTS = 6005
EXPECTED_PROGRAMS_WITH_TOTAL_CREDITS = 174


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "cu_degree_requirements.json"
    programs, requirements = parse_requirements(path)

    results: list[tuple[str, bool]] = []

    # --- Count checks ---
    actual_programs = len(programs)
    actual_requirements = len(requirements)

    results.append(
        (
            f"Program count == {EXPECTED_PROGRAMS} (got {actual_programs})",
            actual_programs == EXPECTED_PROGRAMS,
        )
    )
    results.append(
        (
            f"Requirement count == {EXPECTED_REQUIREMENTS} (got {actual_requirements})",
            actual_requirements == EXPECTED_REQUIREMENTS,
        )
    )

    # --- All OR-alternatives have a predecessor ---
    bad_or = [
        r
        for r in requirements
        if r["requirement_type"] == "or_alternative" and r["or_predecessor_position"] is None
    ]
    results.append(
        (
            f"All OR-alternatives have predecessor ({len(bad_or)} failures found)",
            len(bad_or) == 0,
        )
    )

    # --- Programs with total_credits extracted ---
    programs_with_credits = [p for p in programs if p["total_credits"] is not None]
    actual_with_credits = len(programs_with_credits)
    results.append(
        (
            f"Programs with total_credits == {EXPECTED_PROGRAMS_WITH_TOTAL_CREDITS}"
            f" (got {actual_with_credits})",
            actual_with_credits == EXPECTED_PROGRAMS_WITH_TOTAL_CREDITS,
        )
    )

    # --- No duplicate program names ---
    names = [p["program_name"] for p in programs]
    duplicate_names = [name for name in set(names) if names.count(name) > 1]
    results.append(
        (
            f"No duplicate program names ({len(duplicate_names)} duplicates found)",
            len(duplicate_names) == 0,
        )
    )

    # --- Anomaly report data ---
    programs_without_credits = [p["program_name"] for p in programs if p["total_credits"] is None]
    type_counts = Counter(r["requirement_type"] for r in requirements)

    print("=" * 60)
    print("CUAI-21 Acceptance Criteria Validation")
    print("=" * 60)

    all_passed = True
    for label, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")
        if not passed:
            all_passed = False

    print()
    print("Anomaly Report (informational):")
    print(f"  Programs without total_credits: {len(programs_without_credits)}")
    if programs_without_credits:
        for name in programs_without_credits[:5]:
            print(f"    - {name}")
        if len(programs_without_credits) > 5:
            print(f"    ... and {len(programs_without_credits) - 5} more")
    print("  Type distribution:")
    for req_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {req_type:<25} {count}")

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
