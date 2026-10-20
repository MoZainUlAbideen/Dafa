from dafa.pipeline.verify import strip_bad_markers, verify

CTX = {
    "ppc:379": "Punishment for theft\nWhoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.",
    "ppc:489-F": "Dishonestly issuing a cheque\n... imprisonment which may extend to three years ...",
}


def test_clean_answer_passes():
    ans = "Theft is punishable with up to 3 years [ppc:379]."
    quotes = [{"key": "ppc:379", "text": "may extend to three years"}]
    assert verify(ans, quotes, CTX).ok


def test_invented_citation_is_caught():
    v = verify("See [ppc:380] for house theft.", [], CTX)
    assert not v.ok and v.bad_citations == ["ppc:380"]


def test_citation_key_tolerates_dash_variants():
    assert verify("Cheque bounce [ppc:489F].", [], CTX).ok


def test_misquote_is_caught():
    v = verify("[ppc:379]", [{"key": "ppc:379", "text": "may extend to seven years"}], CTX)
    assert not v.ok and v.bad_quotes


def test_quote_normalises_curly_quotes_and_spacing():
    ctx = {"ppc:1": "without that person’s   consent"}
    assert verify("[ppc:1]", [{"key": "ppc:1", "text": "without that person's consent"}], ctx).ok


def test_wrong_number_is_caught():
    v = verify("Theft carries up to 7 years [ppc:379].", [], CTX)
    assert not v.ok and v.unsupported_numbers == ["7 years"]


def test_number_written_in_words_in_source_counts():
    assert verify("Up to 3 years [ppc:379].", [], CTX).ok


def test_strip_bad_markers():
    assert strip_bad_markers("A [ppc:380] B", ["ppc:380"]) == "A  B"


def test_answer_without_any_citation_fails():
    # Regression: zero citations used to pass verification (nothing to reject).
    v = verify("Theft is punishable with imprisonment up to three years.", [], CTX)
    assert not v.ok and v.no_citations


def test_quote_with_non_breaking_hyphen_matches():
    ctx = {"ppc:381-A": "Whoever commits theft of a car or any other motor vehicle, including motor-cycle"}
    q = [{"key": "ppc:381-A", "text": "including motor‑cycle"}]
    assert verify("[ppc:381-A]", q, ctx).ok


def test_canonical_citations_variants():
    from dafa.pipeline.verify import canonical_citations
    assert canonical_citations("See 【ppc:302】.") == "See [ppc:302]."
    assert canonical_citations("See (PPC: 489F) and [constitution 25a]") == "See [ppc:489-F] and [constitution:25A]"
    assert canonical_citations("Both [ppc:378, ppc:379] apply") == "Both [ppc:378] [ppc:379] apply"
    assert canonical_citations("Already [ppc:379] fine") == "Already [ppc:379] fine"


def test_attach_citations_from_structured_field():
    from dafa.pipeline.verify import attach_citations
    out = attach_citations("Theft carries up to three years.", ["ppc:379", "PPC: 379"])
    assert out.endswith("Sources: [ppc:379]")
    assert verify(out, [], CTX).ok
    # inline markers present -> unchanged
    assert attach_citations("See [ppc:379].", ["ppc:420"]) == "See [ppc:379]."
    # listed key that was never provided is still caught by the verifier
    assert not verify(attach_citations("x", ["ppc:999"]), [], CTX).ok
