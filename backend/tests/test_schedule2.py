from dafa.ingest.schedule2 import (
    DITTO_RE, Word, bounds_at, cell_text, map_columns, normalise_sec, parse_page_rows, rows_to_schedule,
)

HEADER = [
    "Section", "Offence",
    "Whether the police may arrest without warrant or not",
    "Whether a warrant or a summons shall ordinarily issue in the first instance",
    "Whether bailable or not", "Whether compoundable or not",
    "Punishment under the Pakistan Penal Code", "By what Court triable",
]
EDGES = [90.0, 120.0, 190.0, 240.0, 290.0, 340.0, 390.0, 450.0, 500.0]


def segs(top=40.0, bottom=600.0, edges=EDGES):
    return [(x, top, bottom) for x in edges]


def W(x, y, text):
    return Word(x, x + 6 * len(text), y, text)


def test_map_columns_by_header_words():
    assert map_columns(HEADER) == {
        "warrant_or_summons": 3, "section": 0, "offence": 1, "cognizable": 2,
        "bailable": 4, "compoundable": 5, "punishment": 6, "court": 7,
    }


def test_normalise_section_ids():
    assert normalise_sec("379") == "379"
    assert normalise_sec("489F") == "489-F"
    assert normalise_sec("337 A") == "337-A"
    assert normalise_sec("Theft") is None


def test_rows_merge_continuations():
    rows = [
        ["379", "Theft", "Shall not arrest", "Warrant", "Not bailable", "Compoundable", "Imprisonment of either", "Any Magistrate"],
        ["", "", "without warrant", "", "", "", "description for 3 years", ""],
    ]
    sched = rows_to_schedule(rows, map_columns(HEADER))
    assert sched["379"].cognizable == "Shall not arrest without warrant"


def test_words_assigned_to_columns_by_ruling_lines():
    words = [W(92, 60, "379"), W(122, 60, "Theft."), W(192, 60, "May"), W(192, 72, "arrest"),
             W(292, 60, "Not"), W(292, 72, "bailable"), W(392, 60, "Imprisonment"), W(392, 72, "for"),
             W(392, 84, "3"), W(400, 84, "years"), W(452, 60, "Any"), W(452, 72, "Magistrate.")]
    rows, carry = parse_page_rows(words, segs())
    assert rows == [["379", "Theft.", "May arrest", "", "Not bailable", "", "Imprisonment for 3 years", "Any Magistrate."]]


def test_lowercase_of_line_is_not_a_heading():
    # Regression: case-insensitive "Of [A-Z]" dropped the whole visual line "of stolen ... 3 years".
    words = [W(92, 60, "414"), W(122, 60, "Assisting"), W(122, 79, "of"), W(134, 79, "stolen"),
             W(392, 60, "Imprisonment"), W(392, 79, "3"), W(400, 79, "years")]
    rows, _ = parse_page_rows(words, segs())
    assert rows[0][1] == "Assisting of stolen" and rows[0][6] == "Imprisonment 3 years"


def test_real_subheading_is_dropped():
    words = [W(92, 60, "375"), W(122, 60, "Rape."), W(122, 90, "Of"), W(140, 90, "Rape"), W(92, 110, "376"), W(122, 110, "Rape")]
    rows, _ = parse_page_rows(words, segs())
    assert [r[1] for r in rows] == ["Rape.", "Rape"]


def test_first_row_above_where_ruling_lines_start():
    # Regression (p.272): the anchor sat at y=41 but vertical lines began at y=44.
    assert bounds_at(segs(top=44), 41) == EDGES


def test_top_of_page_text_is_carried_to_previous_row():
    words = [W(392, 50, "and"), W(400, 50, "fine."), W(92, 70, "380"), W(122, 70, "Theft")]
    rows, carry = parse_page_rows(words, segs())
    assert carry[5] == "and fine." and rows[0][0] == "380"


def test_ditto_and_cell_cleanup():
    assert DITTO_RE.match("Ditto..") and DITTO_RE.match("Do.")
    assert cell_text([W(100, 10, "conse-"), W(100, 22, "quence")]) == "consequence"
    assert cell_text([W(100, 10, "May"), W(130, 10, "arrest."), W(100, 22, "Ditto..")]) == "May arrest."
