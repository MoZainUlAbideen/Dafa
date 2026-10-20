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
