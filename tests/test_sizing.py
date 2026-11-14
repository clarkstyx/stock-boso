"""
Position-size calculator: boso.position_size() and its JavaScript twin in index.html.

It answers one question: how many shares can I buy so that, if the stop is hit, I lose only
the amount I chose? It never suggests an entry, a stop or a direction. Long positions only.

    pytest -q tests/test_sizing.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import boso

CASES = json.loads((Path(__file__).parent / "fixtures" / "sizing_cases.json").read_text())


def size(**kw):
    return boso.position_size(kw["account"], kw["risk_pct"], kw["entry"], kw["stop"], kw.get("atr"))


def test_readme_example():
    """$5,000 account, 0.5% risk = $25; stop $12 below entry -> 2 shares, $24 actually at risk."""
    r = size(account=5000, risk_pct=0.5, entry=112, stop=100, atr=8)
    assert r["ok"]
    assert r["risk_budget"] == pytest.approx(25)
    assert r["risk_per_share"] == pytest.approx(12)
    assert r["shares"] == 2
    assert r["actual_risk"] == pytest.approx(24)
    assert r["actual_risk_pct"] == pytest.approx(0.48)
    assert r["position_value"] == pytest.approx(224)
    assert r["position_pct"] == pytest.approx(4.48)
    assert r["stop_pct"] == pytest.approx(12 / 112 * 100)
    assert r["stop_atr"] == pytest.approx(1.5)
    assert r["gap_loss"] == pytest.approx(2 * (12 + 8))  # stop gapped through by one ATR
    assert r["warnings"] == []


@pytest.mark.parametrize("account,risk_pct,entry,stop,expected", [
    (10000, 0.3, 1.1, 1.0, 300),   # 30 / 0.1 is 299.9999... in floating point
    (10000, 0.7, 1.3, 1.2, 700),   # 70 / 0.1 is 699.9999...
])
def test_float_noise_does_not_lose_a_share(account, risk_pct, entry, stop, expected):
    assert size(account=account, risk_pct=risk_pct, entry=entry, stop=stop)["shares"] == expected


def test_always_rounds_down_never_up():
    r = size(account=5000, risk_pct=0.5, entry=110, stop=100)  # $25 / $10 = 2.5
    assert r["shares"] == 2
    assert r["actual_risk"] <= r["risk_budget"]


def test_zero_shares_when_one_share_risks_too_much():
    r = size(account=1000, risk_pct=0.25, entry=500, stop=490, atr=12)  # $2.50 budget, $10 per share
    assert r["ok"] and r["shares"] == 0
    assert "zero_shares" in r["warnings"]
    assert r["actual_risk"] == 0 and r["position_value"] == 0


def test_capped_by_cash_no_margin():
    r = size(account=1000, risk_pct=2, entry=100, stop=99.9, atr=2)  # risk allows 200, cash allows 10
    assert r["shares_by_risk"] == 200
    assert r["shares"] == 10
    assert r["position_value"] <= 1000
    assert "cash_capped" in r["warnings"]


@pytest.mark.parametrize("risk_pct,warned", [(0.25, False), (0.5, False), (0.51, True), (1, True)])
def test_risk_above_learning_range_is_warned(risk_pct, warned):
    r = size(account=10000, risk_pct=risk_pct, entry=50, stop=48)
    assert ("risk_high" in r["warnings"]) is warned


@pytest.mark.parametrize("stop,warning", [(178, "stop_tight"), (172, None), (160, "stop_wide")])
def test_stop_distance_checked_against_atr(stop, warning):
    r = size(account=20000, risk_pct=0.5, entry=180, stop=stop, atr=5)  # 0.4 / 1.6 / 4.0 ATR
    found = [w for w in r["warnings"] if w.startswith("stop_")]
    assert found == ([warning] if warning else [])


def test_no_atr_means_no_atr_readings():
    r = size(account=5000, risk_pct=0.5, entry=112, stop=100, atr=None)
    assert r["ok"] and r["stop_atr"] is None and r["gap_loss"] is None


@pytest.mark.parametrize("stop", [100, 105])
def test_stop_must_be_below_entry(stop):
    r = size(account=5000, risk_pct=0.5, entry=100, stop=stop)
    assert r == {"ok": False, "error": "stop_not_below_entry"}


@pytest.mark.parametrize("kw", [
    dict(account=None, risk_pct=0.5, entry=100, stop=95),
    dict(account=0, risk_pct=0.5, entry=100, stop=95),
    dict(account=5000, risk_pct=0.5, entry=-100, stop=-105),
    dict(account=5000, risk_pct=0.5, entry=float("nan"), stop=95),
    dict(account=5000, risk_pct=0, entry=100, stop=95),
])
def test_missing_or_bad_inputs(kw):
    assert size(**kw) == {"ok": False, "error": "missing"}


def test_risk_pct_over_100_is_rejected():
    assert size(account=5000, risk_pct=150, entry=100, stop=95) == {"ok": False, "error": "risk_pct_range"}


def test_output_has_no_signal_fields():
    """The calculator sizes a trade you already chose. It must not grade, rank or suggest one."""
    r = size(account=5000, risk_pct=0.5, entry=112, stop=100, atr=8)
    banned = {"score", "signal", "rating", "buy", "sell", "target", "suggested_stop", "suggested_entry"}
    assert not banned & set(r)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_parity_with_javascript():
    js = subprocess.run(["node", str(Path(__file__).parent / "parity.js")], capture_output=True, text=True, check=True)
    web = json.loads(js.stdout)["_sizing"]
    assert len(web) == len(CASES)
    for case, w in zip(CASES, web):
        py = size(**case)
        assert w["ok"] == py["ok"], case["name"]
        if not py["ok"]:
            assert w["error"] == py["error"], case["name"]
            continue
        assert w["shares"] == py["shares"], case["name"]
        assert w["shares_by_risk"] == py["shares_by_risk"], case["name"]
        assert w["warnings"] == py["warnings"], case["name"]
        for k in ("risk_budget", "risk_per_share", "actual_risk", "actual_risk_pct", "position_value",
                  "position_pct", "stop_pct", "stop_atr", "gap_loss"):
            if py[k] is None:
                assert w[k] is None, (case["name"], k)
            else:
                assert w[k] == pytest.approx(py[k], abs=1e-9), (case["name"], k)
