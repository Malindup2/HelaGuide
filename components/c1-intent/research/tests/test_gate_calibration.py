"""gate_calibration.py helpers (no model needed): predictions, the gate table and the gate rule.
Run from research/:  python -m pytest -q tests
"""
import gate_calibration as gc


def row(conf, right):
    return {"id": "x", "gold": "nic_new", "pred": "nic_new" if right else "passport_new", "confidence": conf}


def test_gate_table_counts_wrong_and_right_below_each_gate():
    rows = [row(0.30, False), row(0.38, False), row(0.45, True), row(0.55, False), row(0.95, True)]
    t = {x["gate"]: x for x in gc.gate_table(rows, grid=(0.35, 0.5, 0.6))}
    assert (t[0.35]["below"], t[0.35]["wrong_below"], t[0.35]["right_below"], t[0.35]["net"]) == (1, 1, 0, 1)
    assert (t[0.5]["below"], t[0.5]["net"]) == (3, 1)          # 2 wrong, 1 right
    assert (t[0.6]["below"], t[0.6]["net"]) == (4, 2)          # 3 wrong, 1 right


def test_choose_gate_takes_the_best_net_and_the_lower_gate_on_ties():
    table = [{"gate": 0.35, "net": 1}, {"gate": 0.5, "net": 3}, {"gate": 0.6, "net": 3}, {"gate": 0.7, "net": 2}]
    assert gc.choose_gate(table) == 0.5


def test_no_positive_net_means_gating_off():
    assert gc.choose_gate([{"gate": 0.35, "net": 0}, {"gate": 0.5, "net": -2}]) == 0.0


def test_predictions_skip_greetings_and_use_the_history_without_them():
    dialogue = {"dialogue_id": "g1", "turns": [
        {"speaker": "user", "text": "hi", "state": {"intent": "nic_new"}},
        {"speaker": "user", "text": "mata ID ekak one", "state": {"intent": "nic_new"}},
        {"speaker": "bot", "text": "Koheda inne?"},
        {"speaker": "user", "text": "Galle", "state": {"intent": "nic_new"}},
    ]}
    seen = []

    def classify(history):
        seen.append(list(history))
        return "nic_new", 0.9

    rows = gc.predictions([dialogue], classify)
    assert [r["id"] for r in rows] == ["g1/1", "g1/3"]
    assert seen == [["mata ID ekak one"], ["mata ID ekak one", "Galle"]]


def test_reliability_bins():
    rows = [row(0.2, False), row(0.95, True), row(1.0, True)]
    bins = {b["bin"]: b for b in gc.reliability(rows)}
    assert bins["[0.00, 0.35)"] == {"bin": "[0.00, 0.35)", "n": 1, "accuracy": 0.0}
    assert bins["[0.90, 1.00]"]["n"] == 2                      # 1.0 falls in the last, closed bin
