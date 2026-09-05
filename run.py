"""Run investigate() against both incidents and write answers.json.

Also prints the per-axis corroboration table so the confidence number
can be sanity-checked against the evidence that produced it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data.loader import load_incident   # noqa: E402
import solution                          # noqa: E402

INCIDENTS = ["incident_a_pool_exhaustion", "incident_b_ambiguous_delay"]


def main() -> None:
    answers = {}
    for name in INCIDENTS:
        query, corpus = load_incident(name)
        report, h = solution.investigate_verbose(query, corpus)
        answers[name] = report

        print(f"\n=== {name} ===")
        print(f"nominees: {[(c, round(s, 2)) for c, s in h.nominees[:5]]}")
        print(f"component: {h.component}   relevance: {h.relevance:.3f}   signature: {h.strong_sig or h.weak_sig}")
        for a in h.axes.values():
            mark = "HIT " if a.hit else "miss"
            extra = f" [{a.strength}]" if a.strength else ""
            extra += " (hedged)" if a.hedged else ""
            src = a.units[0].source if a.units else ""
            print(f"  {mark} {a.name:<12} w={a.weight():>2}{extra:<20} {src}")
        print(f"  counter-evidence sources: {sorted(h.hedge_sources())}")
        print(f"  raw={h.raw_score()}  confidence={report['confidence_score']}  "
              f"review={report['needs_human_review']}  mttr={report['mttr_minutes']}")
        print(f"  impacted: {report['impacted_systems']}")
        print(f"  root_cause: {report['root_cause']}")
        print(f"  remediation: {report['remediation']}")
        print(f"  evidence ({len(report['supporting_evidence'])}):")
        for e in report["supporting_evidence"]:
            print(f"    - {e['source']}: {e['excerpt'][:110]}")

        assert report["needs_human_review"] == (report["confidence_score"] < 50)
        assert set(report) == {"root_cause", "supporting_evidence", "impacted_systems",
                               "mttr_minutes", "remediation", "confidence_score", "needs_human_review"}

    out = Path(__file__).parent / "answers.json"
    out.write_text(json.dumps(answers, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
