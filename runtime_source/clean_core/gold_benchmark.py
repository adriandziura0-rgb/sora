from __future__ import annotations

"""Deterministyczny benchmark jakości dla jednego aktywnego pipeline'u.

Benchmark wywołuje dokładnie ``analyze_active`` i nie implementuje własnego resolvera.
Sprawdza relacje, ramy P3, ranking, TOP oraz integralność ról.
"""

from collections import Counter
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .active_analysis import analyze_active

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD_PATH = ROOT / "benchmark" / "gold_current_cases.json"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _raw(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _norm(value: Any) -> str:
    return _clean(value).casefold()


def _safe_ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0


def load_gold_cases(path: str | Path | None = None) -> Dict[str, Any]:
    target = Path(path) if path else DEFAULT_GOLD_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _relations(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for card in (result.get("sections") or {}).get("canonical_relations", []) or []:
        relation = card.get("canonical_relation") if isinstance(card, dict) else None
        if isinstance(relation, dict) and relation.get("relation_id"):
            out.append(relation)
    return out


def _frame_cards(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        card for card in (result.get("sections") or {}).get("p3_frames", []) or []
        if isinstance(card, dict) and _clean(card.get("phrase"))
    ]


def _frames(result: Mapping[str, Any]) -> set[str]:
    return {_clean(card.get("phrase")) for card in _frame_cards(result)}


def _top_cards(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        card for card in (result.get("sections") or {}).get("public_top", []) or []
        if isinstance(card, dict)
    ]


def _relation_matches(row: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    checks = []
    speaker = _norm(expected.get("speaker"))
    source = _norm(expected.get("source"))
    claim_contains = _norm(expected.get("claim_contains"))
    action = _norm(expected.get("action"))
    speaker_kind = _norm(expected.get("speaker_kind"))
    if speaker:
        checks.append(_norm(row.get("speaker")) == speaker)
    if source:
        checks.append(_norm(row.get("source")) == source)
    if claim_contains:
        checks.append(claim_contains in _norm(row.get("claim")))
    if action:
        checks.append(_norm(row.get("speaker_action") or row.get("attribution_marker")) == action)
    if speaker_kind:
        checks.append(_norm(row.get("speaker_kind")) == speaker_kind)
    return all(checks) if checks else bool(row)


def _best_relation(rows: Iterable[Dict[str, Any]], expected: Mapping[str, Any]) -> Dict[str, Any] | None:
    rows = list(rows)
    if not rows:
        return None
    exact = [row for row in rows if _relation_matches(row, expected)]
    if exact:
        return exact[0]
    speaker = _norm(expected.get("speaker"))
    claim_contains = _norm(expected.get("claim_contains"))
    scored = []
    for row in rows:
        score = 0
        if speaker and _norm(row.get("speaker")) == speaker:
            score += 2
        if claim_contains and claim_contains in _norm(row.get("claim")):
            score += 3
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _evaluate_frame_ranking(case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
    cards = _frame_cards(result)
    phrases = [_clean(card.get("phrase")) for card in cards]
    phrase_set = set(phrases)
    top_phrase = phrases[0] if phrases else ""
    expected_top = _clean(case.get("expected_top_phrase"))
    expect_no_frames = bool(case.get("expect_no_frames"))
    required = {_clean(x) for x in case.get("required_phrases") or [] if _clean(x)}
    forbidden_top = {_clean(x) for x in case.get("forbidden_top_phrases") or [] if _clean(x)}

    if expect_no_frames:
        passed = not phrases
    else:
        passed = (not expected_top or top_phrase == expected_top)
        passed = passed and required.issubset(phrase_set) and top_phrase not in forbidden_top

    failure_stage = ""
    if not passed:
        if expect_no_frames and phrases:
            failure_stage = "false_positive_detection"
        elif expected_top and expected_top not in phrase_set:
            failure_stage = "detector_miss"
        elif expected_top and top_phrase != expected_top:
            failure_stage = "ranking_loss"
        elif required - phrase_set:
            failure_stage = "candidate_set_incomplete"
        elif top_phrase in forbidden_top:
            failure_stage = "forbidden_winner"
        else:
            failure_stage = "frame_contract_mismatch"

    return {
        "id": case.get("id"), "passed": passed, "expected_top": expected_top,
        "expect_no_frames": expect_no_frames, "actual_top": top_phrase,
        "actual_phrases": phrases, "missing_required": sorted(required - phrase_set),
        "failure_stage": failure_stage,
    }


def _evaluate_top(case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
    cards = _top_cards(result)
    claims = [_clean(card.get("claim") or card.get("phrase") or card.get("fragment")) for card in cards]
    speakers = [_clean(card.get("speaker") or card.get("kto_mowi")) for card in cards]
    required = [_clean(x) for x in case.get("required_top_contains") or [] if _clean(x)]
    forbidden = [_clean(x) for x in case.get("forbidden_top_contains") or [] if _clean(x)]
    expected_speaker = _clean(case.get("expected_top_speaker"))
    required_ok = all(any(_norm(needle) in _norm(claim) for claim in claims) for needle in required)
    forbidden_hits = sorted({needle for needle in forbidden if any(_norm(needle) in _norm(claim) for claim in claims)})
    speaker_ok = not expected_speaker or any(_norm(s) == _norm(expected_speaker) for s in speakers)
    passed = required_ok and not forbidden_hits and speaker_ok
    return {
        "id": case.get("id"), "passed": passed, "claims": claims, "speakers": speakers,
        "missing_required": [needle for needle in required if not any(_norm(needle) in _norm(claim) for claim in claims)],
        "forbidden_hits": forbidden_hits, "expected_top_speaker": expected_speaker,
    }


def _evaluate_role_integrity(case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
    rows = _relations(result)
    claim_contains = _norm(case.get("claim_contains"))
    scoped = [row for row in rows if not claim_contains or claim_contains in _norm(row.get("claim"))]
    expected_speaker = _clean(case.get("expected_speaker"))
    forbidden = {_norm(x) for x in case.get("forbidden_speakers") or [] if _clean(x)}
    actual_speakers = [_clean(row.get("speaker")) for row in scoped if _clean(row.get("speaker"))]
    expected_ok = not expected_speaker or any(_norm(s) == _norm(expected_speaker) for s in actual_speakers)
    forbidden_hits = sorted({s for s in actual_speakers if _norm(s) in forbidden})
    passed = bool(scoped) and expected_ok and not forbidden_hits
    return {
        "id": case.get("id"), "passed": passed, "claim_contains": _clean(case.get("claim_contains")),
        "expected_speaker": expected_speaker, "actual_speakers": actual_speakers,
        "forbidden_hits": forbidden_hits,
    }


def run_gold_benchmark(cases: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    gold = dict(cases or load_gold_cases())
    relation_cases = list(gold.get("relation_cases") or [])
    p3_cases = list(gold.get("p3_cases") or [])
    frame_ranking_cases = list(gold.get("frame_ranking_cases") or [])
    top_cases = list(gold.get("top_cases") or [])
    role_integrity_cases = list(gold.get("role_integrity_cases") or [])

    tp = fp = fn = tn = 0
    speaker_ok = speaker_total = 0
    source_ok = source_total = 0
    claim_ok = claim_total = 0
    relation_failures: List[Dict[str, Any]] = []
    rejection_reasons: Counter[str] = Counter()

    for case in relation_cases:
        result = analyze_active(_raw(case.get("text")))
        rows = _relations(result)
        expected = bool(case.get("expect_relation"))
        matched = any(_relation_matches(row, case) for row in rows) if expected else False
        predicted = matched if expected else bool(rows)
        if expected and matched:
            tp += 1
        elif not expected and rows:
            fp += 1
        elif expected and not matched:
            fn += 1
        else:
            tn += 1

        for rejection in (result.get("sections") or {}).get("canonical_relation_rejections", []) or []:
            for reason in rejection.get("reasons") or [rejection.get("reason")]:
                if reason:
                    rejection_reasons[str(reason)] += 1

        if not expected:
            if predicted:
                relation_failures.append({"id": case.get("id"), "kind": "false_positive", "text": case.get("text")})
            continue

        best = _best_relation(rows, case)
        if not best:
            relation_failures.append({"id": case.get("id"), "kind": "false_negative", "text": case.get("text")})
            continue
        if not _relation_matches(best, case):
            relation_failures.append({
                "id": case.get("id"), "kind": "target_relation_not_found",
                "expected_speaker": _clean(case.get("speaker")),
                "expected_claim_contains": _clean(case.get("claim_contains")),
                "actual_speaker": _clean(best.get("speaker")), "actual_claim": _clean(best.get("claim")),
                "text": case.get("text"),
            })

        expected_speaker = _clean(case.get("speaker"))
        if expected_speaker:
            speaker_total += 1
            if _norm(best.get("speaker")) == _norm(expected_speaker):
                speaker_ok += 1
            else:
                relation_failures.append({
                    "id": case.get("id"), "kind": "speaker_mismatch", "expected": expected_speaker,
                    "actual": _clean(best.get("speaker")), "text": case.get("text"),
                })

        expected_source = _clean(case.get("source"))
        if expected_source:
            source_total += 1
            if _norm(best.get("source")) == _norm(expected_source):
                source_ok += 1
            else:
                relation_failures.append({
                    "id": case.get("id"), "kind": "source_mismatch", "expected": expected_source,
                    "actual": _clean(best.get("source")), "text": case.get("text"),
                })

        claim_contains = _clean(case.get("claim_contains"))
        if claim_contains:
            claim_total += 1
            if _norm(claim_contains) in _norm(best.get("claim")):
                claim_ok += 1
            else:
                relation_failures.append({
                    "id": case.get("id"), "kind": "claim_mismatch", "expected_contains": claim_contains,
                    "actual": _clean(best.get("claim")), "text": case.get("text"),
                })

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)

    p3_tp = p3_fp = p3_fn = 0
    p3_failures: List[Dict[str, Any]] = []
    for case in p3_cases:
        result = analyze_active(_raw(case.get("text")))
        predicted = _frames(result)
        expected = {_clean(x) for x in case.get("expected_phrases") or [] if _clean(x)}
        forbidden = {_clean(x) for x in case.get("forbidden_phrases") or [] if _clean(x)}
        p3_tp += len(predicted & expected)
        p3_fp += len(predicted - expected)
        p3_fn += len(expected - predicted)
        forbidden_hit = sorted(predicted & forbidden)
        if predicted != expected or forbidden_hit:
            p3_failures.append({
                "id": case.get("id"), "text": case.get("text"), "expected": sorted(expected),
                "actual": sorted(predicted), "forbidden_hit": forbidden_hit,
            })

    p3_precision = _safe_ratio(p3_tp, p3_tp + p3_fp)
    p3_recall = _safe_ratio(p3_tp, p3_tp + p3_fn)

    frame_ranking_results = []
    for case in frame_ranking_cases:
        frame_ranking_results.append(_evaluate_frame_ranking(case, analyze_active(_raw(case.get("text")))))
    frame_ranking_failures = [row for row in frame_ranking_results if not row["passed"]]

    top_results = []
    for case in top_cases:
        top_results.append(_evaluate_top(case, analyze_active(_raw(case.get("text")))))
    top_failures = [row for row in top_results if not row["passed"]]

    role_results = []
    for case in role_integrity_cases:
        role_results.append(_evaluate_role_integrity(case, analyze_active(_raw(case.get("text")))))
    role_integrity_failures = [row for row in role_results if not row["passed"]]

    case_count = len(relation_cases) + len(p3_cases) + len(frame_ranking_cases) + len(top_cases) + len(role_integrity_cases)
    failure_count = len(relation_failures) + len(p3_failures) + len(frame_ranking_failures) + len(top_failures) + len(role_integrity_failures)
    failed_case_ids = sorted({
        str(row.get("id")) for group in (relation_failures, p3_failures, frame_ranking_failures, top_failures, role_integrity_failures)
        for row in group if row.get("id")
    })

    return {
        "schema": "drogowskazy_gold_benchmark_v3",
        "dataset": gold.get("name") or "GOLD",
        "status": gold.get("status") or "regression",
        "target_stage": gold.get("target_stage") or "",
        "case_count": case_count,
        "relation_case_count": len(relation_cases), "p3_case_count": len(p3_cases),
        "frame_ranking_case_count": len(frame_ranking_cases), "top_case_count": len(top_cases),
        "role_integrity_case_count": len(role_integrity_cases),
        "contract": {
            "preserves_paragraphs": True, "matches_specific_relation": True,
            "document_boundaries_preserved": True, "tests_frame_winner": bool(frame_ranking_cases),
            "tests_top_artifacts": bool(top_cases), "tests_speaker_role_integrity": bool(role_integrity_cases),
            "diagnoses_frame_failure_stage": bool(frame_ranking_cases),
        },
        "relations": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": _f1(precision, recall),
            "speaker_accuracy": _safe_ratio(speaker_ok, speaker_total), "speaker_n": speaker_total,
            "source_accuracy": _safe_ratio(source_ok, source_total), "source_n": source_total,
            "claim_contains_accuracy": _safe_ratio(claim_ok, claim_total), "claim_n": claim_total,
        },
        "p3": {
            "tp": p3_tp, "fp": p3_fp, "fn": p3_fn,
            "precision": p3_precision, "recall": p3_recall, "f1": _f1(p3_precision, p3_recall),
        },
        "frame_ranking": {
            "passed": len(frame_ranking_results) - len(frame_ranking_failures),
            "failed": len(frame_ranking_failures),
            "accuracy": _safe_ratio(len(frame_ranking_results) - len(frame_ranking_failures), len(frame_ranking_results)),
            "failure_stages": dict(Counter(
                row.get("failure_stage") for row in frame_ranking_failures if row.get("failure_stage")
            )),
        },
        "top_integrity": {
            "passed": len(top_results) - len(top_failures), "failed": len(top_failures),
            "accuracy": _safe_ratio(len(top_results) - len(top_failures), len(top_results)),
        },
        "role_integrity": {
            "passed": len(role_results) - len(role_integrity_failures), "failed": len(role_integrity_failures),
            "accuracy": _safe_ratio(len(role_results) - len(role_integrity_failures), len(role_results)),
        },
        "all_pass": not failed_case_ids,
        "failure_count": failure_count,
        "failed_case_count": len(failed_case_ids),
        "passed_case_count": case_count - len(failed_case_ids),
        "failed_case_ids": failed_case_ids,
        "top_rejection_reasons": rejection_reasons.most_common(12),
        "relation_failures": relation_failures, "p3_failures": p3_failures,
        "frame_ranking_failures": frame_ranking_failures, "top_failures": top_failures,
        "role_integrity_failures": role_integrity_failures,
    }


def write_gold_report(path: str | Path, cases: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    report = run_gold_benchmark(cases)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
