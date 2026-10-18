"""Tests for the CSV import (gtm/importers.py), CSV-safe export, and structured numbers Q&A (gtm/numbers_qa.py)."""
import pytest

from gtm import importers, kyc, numbers_qa, pulse
from gtm.store import GTMStore
from gtm.validation import ValidationError


@pytest.fixture()
def store(tmp_path):
    return GTMStore(tmp_path / "gtm.db")


APOLLO = (b"First Name,Last Name,Title,Company,Email,Person Linkedin Url\n"
          b"Nora,Whitfield,VP of AI,Deepcurrent Labs,nora.w@deepcurrentlabs.example.com,https://www.linkedin.com/in/nora-w\n"
          b"Omar,Haddad,Head of Data,Tessera Cloud Inc.,omar.h@tesseracloud.example.com,\n"
          b"Pia,Lund,CTO,Unknown Startup,pia@unknown.example.com,\n"
          b"Quinn,Park,Head of ML,Deepcurrent Labs,not-an-email,\n"
          b"Nora,Whitfield,VP of AI,Deepcurrent Labs,NORA.W@deepcurrentlabs.example.com,\n"
          b"Tomas,Zielinski,VP of AI Research,Deepcurrent Labs,tomas.zielinski@deepcurrentlabs.example.com,\n")
ZOOMINFO = (b"First Name,Last Name,Job Title,Company Name,Email Address,Direct Phone Number\n"
            b"Rae,Okafor,Director of Data,Tessera Cloud,rae.o@tesseracloud.example.com,+1 555 0100\n")


# ---------------------------------------------------------------- import mapping
def test_detects_apollo_and_zoominfo_headers():
    assert importers.detect_mapping(["First Name", "Last Name", "Title", "Company", "Email", "Person Linkedin Url"]) == {
        "first_name": "First Name", "last_name": "Last Name", "title": "Title", "company": "Company", "email": "Email", "linkedin_url": "Person Linkedin Url"}
    z = importers.detect_mapping(["First Name", "Last Name", "Job Title", "Company Name", "Email Address", "Direct Phone Number", "Revenue"])
    assert z["title"] == "Job Title" and z["company"] == "Company Name" and z["email"] == "Email Address" and z["phone"] == "Direct Phone Number"
    assert "Revenue" not in z.values()


def test_preview_classifies_every_row_and_writes_nothing(store):
    before = store.counts()
    mapping, prev = importers.preview(store, APOLLO)
    assert store.counts() == before and len(prev) == 6
    status = dict(zip(prev.name, prev.status))
    rows = prev.set_index("row")
    assert rows.loc[2, "status"] == "ok" and rows.loc[3, "status"] == "ok"                      # company matched through name normalisation (Inc.)
    assert rows.loc[4, "status"] == "unmatched account" and "create it first" in rows.loc[4, "reason"]
    assert rows.loc[5, "status"] == "invalid" and "Email" in rows.loc[5, "reason"]
    assert rows.loc[6, "status"] == "duplicate in file"
    assert rows.loc[7, "status"] == "duplicate" and "email" in rows.loc[7, "reason"]            # already in the store
    assert status["Pia Lund"] == "unmatched account" and mapping["company"] == "Company"


def test_import_inserts_only_ok_rows_with_the_csv_source_and_chosen_owner(store):
    result = importers.import_rows(store, APOLLO, owner="Harry")
    assert result == {"imported": 2, "skipped": 4, "errors": []}
    new = store.prospects().query("email in ['nora.w@deepcurrentlabs.example.com', 'omar.h@tesseracloud.example.com']")
    assert len(new) == 2 and set(new.lead_source) == {"CSV import"} and set(new.owner) == {"Harry"}
    assert set(new.sequence_status) == {"Active"} and set(new.lead_temperature) == {"Cold"}
    again = importers.import_rows(store, APOLLO, owner="Harry")                                  # re-importing the same file adds nothing
    assert again["imported"] == 0 and store.counts()["prospects"] == 111


def test_zoominfo_file_imports_phone_and_title(store):
    assert importers.import_rows(store, ZOOMINFO)["imported"] == 1
    row = store.prospects().query("email == 'rae.o@tesseracloud.example.com'").iloc[0]
    assert row.title == "Director of Data" and row.phone == "+1 555 0100" and row.account_id == "ACC-102"


@pytest.mark.parametrize("raw, message", [
    (b"", "no data rows"), (b"Name,Company\n", "no data rows"), (b"foo,bar\n1,2\n", "required columns"),
    (b"Email,Title\na@b.co,CEO\n", "required columns"), ("x" * (importers.MAX_BYTES + 1), "too large"), ("not bytes", "Upload a CSV")])
def test_bad_files_are_rejected_with_a_clear_message(store, raw, message):
    raw = raw.encode() if isinstance(raw, str) and message == "too large" else raw
    with pytest.raises(ValidationError, match=message):
        importers.preview(store, raw)


def test_row_limit_and_latin1_files(store):
    with pytest.raises(ValidationError, match="Too many rows"):
        importers.preview(store, b"Name,Company\n" + b"A B,Deepcurrent Labs\n" * (importers.MAX_ROWS + 1))
    latin = "Full Name,Company,Email\nRen\xe9 Dubois,Deepcurrent Labs,rene@deepcurrentlabs.example.com\n".encode("latin-1")
    _, prev = importers.preview(store, latin)
    assert prev.iloc[0].status == "ok" and prev.iloc[0]["name"] == "Ren\xe9 Dubois"


# ---------------------------------------------------------------- CSV-safe export
@pytest.mark.parametrize("cell", ["=SUM(A1)", "+1+1", "-2", "@cmd", "\tx"])
def test_csv_cells_that_look_like_formulas_are_neutralised(cell):
    assert kyc.csv_safe(cell) == "'" + cell
    assert kyc.csv_safe("normal text") == "normal text" and kyc.csv_safe(None) == ""


def test_exported_profile_has_no_live_formulas(store):
    data, _ = store.kyc_profile("ACC-101")
    out = kyc.profile_csv("ACC-101", "=HYPERLINK(\"http://x\")", {**data, "website": "@evil", "pain_points": "-5+5"}).decode()
    assert "'=HYPERLINK" in out and "'@evil" in out and "'-5+5" in out


# ---------------------------------------------------------------- structured numbers Q&A (separate from RAG)
@pytest.fixture()
def snap(store):
    return pulse.snapshot(store)


@pytest.mark.parametrize("question, expected_topic", [
    ("What is our open pipeline?", "pipeline"), ("What is the weighted pipeline?", "weighted"), ("what's our GP margin", "gp_margin"),
    ("How much revenue have we won?", "revenue"), ("What is our win rate?", "win_rate"), ("How many hot leads do we have?", "hot"),
    ("How many follow-ups are pending?", "followups"), ("Who is the top SDR?", "sdr"), ("Which deals are stalled?", "stalled"),
    ("Are we on track for our monthly target?", "target"), ("How many accounts closed?", "accounts_closed"),
    ("What are the most requested capabilities?", "demand")])
def test_metric_questions_are_recognised(question, expected_topic):
    assert numbers_qa.topic(question) == expected_topic and numbers_qa.route(question) == "numbers"


@pytest.mark.parametrize("question", ["Who is our ideal customer?", "What capabilities do we offer?", "Tell me about the Deepcurrent KYC profile",
                                      "How do we position against competitors?", "What case studies do we have?", "hello"])
def test_document_questions_are_not_taken_by_the_numbers_path(question):
    assert numbers_qa.route(question) == "documents"


def test_every_suggested_numbers_question_gets_an_answer_with_the_dashboard_figures(snap):
    c = snap["commercial"]
    for q in numbers_qa.SUGGESTIONS:
        text = numbers_qa.answer(q, snap)
        assert text and "Executive Pulse" in text and "as of" in text, q
    assert numbers_qa.money(c["open_pipeline"]) in numbers_qa.answer("What is our open pipeline?", snap)
    assert f"{c['win_rate']:.0%}" in numbers_qa.answer("What is our win rate?", snap)
    assert snap["sdr"].iloc[0].sdr in numbers_qa.answer("Who is the top SDR?", snap)
    assert str(snap["leads"]["hot_leads"]) in numbers_qa.answer("How many hot leads do we have?", snap)
    assert numbers_qa.answer("Tell me a story", snap) is None


def test_answers_follow_the_data_when_it_changes(store):
    before = numbers_qa.answer("How many follow-ups are pending?", pulse.snapshot(store))
    pid = store.df("SELECT p.prospect_id FROM prospects p WHERE p.sequence_status='Active' AND EXISTS "
                   "(SELECT 1 FROM follow_ups f WHERE f.prospect_id=p.prospect_id AND f.status='Pending') ORDER BY 1").iloc[0].prospect_id
    store.update_prospect(pid, {"response_status": "Opt-out"})
    assert numbers_qa.answer("How many follow-ups are pending?", pulse.snapshot(store)) != before
