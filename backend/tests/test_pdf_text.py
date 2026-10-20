from dafa.ingest.pdf_text import _join, _Span, group_into_lines


def S(x0, x1, y, text, size=13.0):
    return _Span(x0, x1, y, size, text, False)


def test_heading_and_body_on_same_baseline_are_one_line_in_x_order():
    # Regression for PPC 302: body block had a slightly smaller y than the heading block.
    spans = [S(260, 560, 100.4, "Whoever commits qatl-e-amd shall, subject to the provisions"),
             S(33, 255, 101.2, "302. Punishment of qatl-e-amd."),
             S(33, 200, 116.0, "of this Chapter be")]
    lines = [_join(ln) for ln in group_into_lines(spans)]
    assert lines == ["302. Punishment of qatl-e-amd. Whoever commits qatl-e-amd shall, subject to the provisions",
                     "of this Chapter be"]
