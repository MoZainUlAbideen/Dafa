from dafa.retrieval.router import route
from dafa.retrieval.text import expand_query, tokenize


def test_router_ppc_variants():
    assert route("what is section 302?").refs == [("ppc", "302")]
    assert route("dafa 489-F kya hai").refs == [("ppc", "489-F")]
    assert route("420 PPC punishment").refs == [("ppc", "420")]
    assert route("302").refs == [("ppc", "302")]


def test_router_constitution():
    r = route("Explain Article 25A")
    assert r.refs == [("constitution", "25A")]
    assert r.book_hint == "constitution"


def test_router_no_ref_for_plain_question():
    assert route("someone stole my bike").refs == []


def test_tokenize_splits_hyphenated_legal_terms():
    toks = tokenize("qatl-i-amd")
    assert "qatl-i-amd" in toks and "qatl" in toks


def test_glossary_maps_roman_urdu():
    assert "theft" in expand_query("mera phone chori ho gaya")


def test_store_lookup_tolerates_dash(store):
    assert store.get("ppc", "489F").id == "489-F"
    assert store.get("ppc", "489-f").id == "489-F"
    assert store.get("constitution", "25a").id == "25A"
    assert store.get("ppc", "999") is None


def test_search_english(store):
    hits = store.search("someone stole my bicycle, what is the punishment for theft", k=3)
    assert hits[0].section.id in {"378", "379"}


def test_search_roman_urdu(store):
    hits = store.search("cheque bounce ho gaya", k=3)
    assert hits[0].section.id == "489-F"


def test_search_book_filter(store):
    hits = store.search("arrest rights", k=3, book="constitution")
    assert all(h.section.book == "constitution" for h in hits)
    assert hits[0].section.id == "10"


def test_toc_groups_in_order(store):
    toc = store.toc("constitution")
    assert toc[0]["name"].startswith("PART II")
    assert [s["id"] for s in toc[0]["sections"]] == ["10", "19", "25A"]
