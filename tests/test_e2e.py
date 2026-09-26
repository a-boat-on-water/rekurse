"""Full pipeline on fake Pi + MemoryStore + stubbed reflector. Offline, no LLM."""
import time
from pathlib import Path

from rekurse import demo
from rekurse.models import TRAP_ROOT
from rekurse.store import MemoryStore


def test_full_pipeline_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("REKURSE_FAKE_RECOVER_BEFORE", "2")
    demo._fake_mode()
    store = MemoryStore()
    heldout = "heldout" if (TRAP_ROOT / "heldout" / "trap.json").exists() else None
    t0 = time.time()
    doc = demo.run_pipeline(store, "primary", heldout, "e2e", tmp_path / "work",
                            demo.stub_reflector, demo.fake_embed, seeds=3, decision_seeds=5, concurrency=4, log=lambda *_: None)
    assert time.time() - t0 < 60

    session = store.get_session(doc["session_id"])
    assert session["accepted"] and session["hint_turn"] == 3 and session["solved_turn"] == 3
    # fake recovers with <2 prior user turns, so the wrong turn is checkpoint 2.
    # bisect probes k=1 (rescued 2/2, early stop) then k=2 (0/2); k=0 is never run and stays gray.
    assert doc["probed_ks"] == [1, 2] and doc["wrong_turn_k"] == 2
    assert doc["sweep_rates"] == {"1": [2, 2], "2": [0, 2]}

    lessons = {L["text"]: L for L in store.lessons("e2e")}
    bad = next(L for t, L in lessons.items() if "format_date" in t)
    assert bad["status"] == "rejected" and "format_date" in bad["reason"]
    merged = [L for L in lessons.values() if L["status"] == "merged"]
    assert len(merged) == 1 and merged[0]["top1_similarity"] >= 0.96
    best = store.get_lesson(doc["best_lesson_id"])
    assert best["status"] == "adopted" and doc["decision"] == "adopted"
    assert doc["decision_lesson"] == [5, 5] and doc["decision_baseline"] == [0, 5]
    assert doc["p_values"]["wrong_turn"] < 0.01
    if heldout:
        assert doc["heldout_with"][0] >= doc["heldout_without"][0]

    paths = demo.write_outputs if hasattr(demo, "write_outputs") else None
    from rekurse import report
    out = tmp_path / "out"
    report.write_outputs(store, doc, out)
    html = (out / "report.html").read_text()
    assert "k=2" in html and "0/2" in html and "5/5" in html and "ADOPTED" in html
    assert best["text"] in (out / "AGENTS.md").read_text()
    pm = (out / "postmortem.md").read_text()
    assert "checkpoint 2" in pm and "Discarded lesson" in pm
