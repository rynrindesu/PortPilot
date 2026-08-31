import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from pprint import pformat

from PortPilot.agent.scheduling_rules import (
    _affected_vessel_count,
    _total_schedule_shift,
    _repeat_changes,
    _resource_utilisation,
    rank_options,
)
from PortPilot.database.postgres import get_vessel_schedule

RUN_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scheduling_pipeline_tests" / "test_output" / "run_output_2.txt"
)
RANK_OPTIONS_RESULTS_PATH = (
    Path(__file__).resolve().parent / "sample_tests_results" / "rank_options.txt"
)

"""
Tests scoring_rules.py's soft-constraint scoring and ranking - the four
scorer functions and rank_options(). Hard-constraint filtering
(filter_valid_options()) is not tested here: it's already exercised more
realistically by scheduling_pipeline_tests/monitoring_pipeline.py, which
runs it against live-generated candidates across multiple real vessels.

Run with:
    python3 backend/tests/rank_options_tests.py/test_rank_options.py           # everything below
    python3 backend/tests/rank_options_tests.py/test_rank_options.py score     # just the scoring functions
    python3 backend/tests/rank_options_tests.py/test_rank_options.py rank      # just rank_options()
    python3 backend/tests/rank_options_tests.py/test_rank_options.py rank-real # rank_options() against monitoring_pipeline.py's real output
"""

# A frozen snapshot of a filter_valid_options() "valid" result from an
# earlier run (see sample_tests_results/filter_valid_options_sample_output.txt).
# Its hardcoded 2026-08-30 times drift into the freeze window as real time
# passes, but as a fixed input to the scoring functions that doesn't
# matter - this snapshot lets test_scoring()/test_ranking() exercise them
# regardless of live DB/freeze-window state.
sample_valid_options = [
    {
        "option_id": "shift_same_resources",
        "strategy": "shift_same_resources",
        "target_eta": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
        "affected_vessels": [
            {"vessel_name": "MAO GANG GUANG ZHOU", "imo_number": "9981348"}
        ],
        "changes": [
            {
                "vessel_name": "MAO GANG GUANG ZHOU",
                "imo_number": "9981348",
                "allocations": {
                    "berth": {
                        "resource_id": "B25",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 4, 54, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "pilot": {
                        "resource_id": "P16",
                        "start_time": datetime(2026, 8, 30, 22, 43, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "tug": {
                        "resource_id": "T13",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 0, 18, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                },
            }
        ],
        "resource_conflicts": [],
    },
]


def test_scoring():
    # Scoring only makes sense for candidates that actually passed
    # filter_valid_options() - an invalid candidate can't be applied, so
    # there's nothing to rank it against. Uses the frozen sample_valid_options
    # snapshot rather than a live filter_valid_options() call, since the live
    # sample candidates' hardcoded times drift into the freeze window over
    # time and would otherwise leave nothing to score.
    print("scoring (against a frozen snapshot of a prior valid filter_valid_options() result):")
    for option in sample_valid_options:
        print(f"  {option['option_id']}")
        print(f"    affected_vessel_count: {_affected_vessel_count(option)}")
        print(f"    total_schedule_shift (min): {_total_schedule_shift(option)}")
        print(f"    repeat_changes: {_repeat_changes(option)}")
        print(f"    resource_utilisation (min): {_resource_utilisation(option)}")


def test_ranking():
    # Smoke test: rank_options() must handle the real filter_valid_options()
    # shape without error, even with just one candidate to "rank".
    print("ranking sample_valid_options (single candidate, trivial order):")
    ranked = rank_options(sample_valid_options)
    print("  ", [o["option_id"] for o in ranked])

    # Synthetic candidates that differ only in affected_vessel_count - the
    # dominant DEFAULT_PRIORITY criterion - so the expected order is
    # deterministic without depending on which vessels are currently seeded
    # (unlike sample_valid_options, which needs real DB vessels to score
    # meaningfully - see test_sample_vessels_exist()).
    def synthetic_option(option_id, num_vessels):
        changes = [
            {
                "vessel_name": f"RANK TEST VESSEL {i}",
                "imo_number": f"900000{i}",
                "allocations": {
                    "berth": {
                        "resource_id": f"RANK_TEST_B{i}",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 0, 30, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                },
            }
            for i in range(num_vessels)
        ]
        return {
            "option_id": option_id,
            "affected_vessels": [
                {"vessel_name": c["vessel_name"], "imo_number": c["imo_number"]} for c in changes
            ],
            "changes": changes,
            "resource_conflicts": [],
        }

    candidates = [
        synthetic_option("three_vessels", 3),
        synthetic_option("one_vessel", 1),
        synthetic_option("two_vessels", 2),
    ]
    ranked = rank_options(candidates)

    print()
    print("ranking synthetic candidates (differing only in affected_vessel_count):")
    print("  input order: ", [o["option_id"] for o in candidates])
    print("  ranked order:", [o["option_id"] for o in ranked])
    print("  expected:     ['one_vessel', 'two_vessels', 'three_vessels'] "
          "(fewer affected vessels ranks first)")


def _parse_datetimes(value):
    """Recursively turn ISO datetime strings back into datetime objects.

    monitoring_pipeline.py serialises its report with
    json.dumps(default=...), which converts every datetime to
    value.isoformat(); this undoes that so the scoring functions get real
    datetime objects to do timedelta arithmetic with, not strings.
    """
    if isinstance(value, dict):
        return {key: _parse_datetimes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_parse_datetimes(item) for item in value]
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _load_run_output(path):
    """Load the most recent report appended to a monitoring_pipeline.py
    output file (reports are appended, separated by a line of "=")."""
    text = path.read_text()
    blocks = [block.strip() for block in text.split("=" * 88) if block.strip()]
    report = json.loads(blocks[-1])
    return _parse_datetimes(report)


def test_ranking_real_run_output():
    # Rank rank_options() against real filter_valid_options() output taken
    # from RUN_OUTPUT_PATH - currently run_output_2.txt, produced by
    # filter_generated_options_snapshot.py - rather than only
    # synthetic/frozen data.
    # Prints the raw ranked option dicts (not just a scores summary), and
    # writes that same raw output to RANK_OPTIONS_RESULTS_PATH, replacing
    # whatever was there before rather than appending - this file always
    # reflects only the most recent run, unlike monitoring_pipeline.py's
    # own append-per-run output.
    report = _load_run_output(RUN_OUTPUT_PATH)

    lines = [
        f"ranking real filter_valid_options() output from {RUN_OUTPUT_PATH.name} "
        f"(run executed {report['executed_at']}):"
    ]

    for vessel_plan in report["vessel_plans"]:
        vessel_name = vessel_plan["vessel_name"]
        imo_number = vessel_plan["imo_number"]
        valid_options = vessel_plan["validated_plans"]

        lines.append(f"\n{vessel_name} ({imo_number}) - {len(valid_options)} valid plan(s):")
        if not valid_options:
            lines.append("  (nothing to rank)")
            continue

        ranked = rank_options(valid_options)
        lines.append(pformat(ranked))

    output_text = "\n".join(lines)
    print(output_text)

    RANK_OPTIONS_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RANK_OPTIONS_RESULTS_PATH.open("w", encoding="utf-8") as results_file:
        results_file.write(output_text)
        results_file.write("\n")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("score", "all"):
        test_scoring()
    if which in ("rank", "all"):
        test_ranking()
    if which in ("rank-real", "all"):
        test_ranking_real_run_output()
