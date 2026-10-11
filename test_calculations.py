"""Run with:  pytest -q
Checks that the data is consistent and that every financial definition is calculated correctly."""
import pandas as pd
import pytest

import hoomi
import metrics as m


@pytest.fixture(scope="module")
def df():
    return m.load_data()


@pytest.fixture(scope="module")
def targets():
    return m.load_targets()


def test_dataset_shape(df):
    assert len(df) == 50
    assert df["opportunity_id"].is_unique
    assert set(df["stage"]) <= set(m.STAGES)
    assert set(df["region"]) == {"US", "Europe", "LATAM", "APAC"}
    assert set(df["sales_owner"]) == {"Jon", "Sara", "Alex", "Emma", "Ryan"}


def test_gross_profit_is_revenue_minus_cost(df):
    assert ((df["expected_revenue"] - df["expected_delivery_cost"]) - df["expected_gross_profit"]).abs().max() < 1
    margin = df["expected_gross_profit"] / df["expected_revenue"] * 100
    assert (margin - df["gp_margin_pct"]).abs().max() < 0.1


def test_probabilities_match_stage(df):
    assert (df.loc[df.stage == "Won", "close_probability"] == 1).all()
    assert (df.loc[df.stage == "Lost", "close_probability"] == 0).all()
    open_p = df.loc[df.is_open, "close_probability"]
    assert open_p.between(0.05, 0.95).all()


def test_kpis_match_manual_calculation(df):
    k = m.kpis(df)
    open_df, won, lost = df[df.is_open], df[df.stage == "Won"], df[df.stage == "Lost"]
    assert k["open_pipeline"] == open_df["deal_value"].sum()
    assert k["weighted_pipeline"] == pytest.approx((open_df["deal_value"] * open_df["close_probability"]).sum())
    assert k["won_revenue"] == won["expected_revenue"].sum()
    assert k["won_gp"] == won["expected_gross_profit"].sum()
    assert k["gp_margin"] == pytest.approx(k["won_gp"] / k["won_revenue"])
    assert k["win_rate"] == pytest.approx(len(won) / (len(won) + len(lost)))
    assert k["weighted_pipeline"] < k["open_pipeline"]


def test_won_and_lost_never_in_pipeline(df):
    assert m.kpis(df[df.stage.isin(["Won", "Lost"])])["open_pipeline"] == 0


def test_group_summaries_add_up(df):
    k = m.kpis(df)
    for col in ["sales_owner", "region", "customer_segment", "service_offering"]:
        s = m.summarize_by(df, col)
        assert s["open_pipeline"].sum() == pytest.approx(k["open_pipeline"])
        assert s["won_revenue"].sum() == pytest.approx(k["won_revenue"])


def test_funnel_covers_all_deals(df):
    f = m.funnel(df)
    assert f["deals"].sum() == len(df)
    assert list(f["stage"]) == m.STAGES


def test_targets_vs_actuals(df, targets):
    by_month, by_rep = m.targets_vs_actuals(df, targets)
    assert by_rep["actual"].sum() == m.kpis(df)["won_revenue"]
    assert by_rep["target"].sum() == by_month["target"].sum() == targets[targets.month <= "2026-10"]["target"].sum()
    _, jon = m.targets_vs_actuals(df, targets, owners=["Jon"])
    assert list(jon["sales_owner"]) == ["Jon"]


def test_stalled_and_risk(df):
    s = m.stalled_deals(df)
    assert s["is_open"].all() and (s["days_since_activity"] > m.STALL_DAYS).all()
    assert set(s.opportunity_id) <= set(m.at_risk_deals(df).opportunity_id)


def test_money_format():
    assert m.money(1_250_000) == "$1.25M" and m.money(480_000) == "$480K" and m.money(0) == "$0"
