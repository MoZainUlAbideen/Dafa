"""Parser tests on synthetic lines shaped like Pakistani statute PDFs.
(Real-PDF behaviour is covered by tests/test_processed_data.py.)"""

import pytest

from dafa.ingest.parse_sections import numbering_gaps, parse, split_title
from dafa.ingest.pdf_text import Line, clean_text


def L(*texts):
    return [Line(page=i // 10 + 1, text=t, bold=False, size=10) for i, t in enumerate(texts)]


PPC_LINES = L(
    "PAKISTAN PENAL CODE",
    "CONTENTS",
    "CHAPTER I",
    "1. Title and extent of operation of the Code",
    "2. Punishment of offences committed within Pakistan",
    "378. Theft",
    "379. Punishment for theft",
    "PREAMBLE",
    "CHAPTER I",
    "INTRODUCTION",
    "1. Title and extent of operation of the Code. This Act shall be called the Pakistan Penal Code,",
    "and shall take effect throughout Pakistan.",
    "2. Punishment of offences committed within Pakistan. Every person shall be liable to punishment",
    "under this Code and not otherwise.",
    "3. [Omitted]",
    "CHAPTER XVII",
    "OF OFFENCES AGAINST PROPERTY",
    "Of Theft",
    "4. Extension of Code to extra-territorial offences.- The provisions of this Code apply also",
    "to any offence committed by (1) any citizen of Pakistan; (2) any person on any ship.",
    "5. Certain laws not to be affected: Nothing in this Act shall affect",
    "12. this number is out of order inside a body and must be ignored",
    "6. Definitions.-Throughout this Code every definition",
    "6A. Inserted section.- Body of 6A.",
    "SCHEDULE",
    "1. Not a section",
)


def test_skips_table_of_contents_and_parses_body():
    secs = parse(PPC_LINES, "ppc")
    assert [s.id for s in secs] == ["1", "2", "3", "4", "5", "6", "6-A"]
    assert secs[0].title == "Title and extent of operation of the Code"
    assert secs[0].text.startswith("This Act shall be called")
    assert secs[0].text.endswith("throughout Pakistan.")


def test_out_of_order_number_stays_in_body():
    s5 = parse(PPC_LINES, "ppc")[4]
    assert "out of order" in s5.text


def test_omitted_flag():
    s3 = parse(PPC_LINES, "ppc")[2]
    assert s3.omitted and s3.title == "Omitted"


def test_groups_and_subheadings():
    secs = parse(PPC_LINES, "ppc")
    assert secs[0].group == "Chapter I: Introduction"
    assert secs[3].group == "Chapter XVII: Of Offences against Property"
    assert "Of Theft" not in secs[2].text


def test_stops_at_schedule():
    assert parse(PPC_LINES, "ppc")[-1].id == "6-A"


@pytest.mark.parametrize(
    "rest,title,body",
    [
        ("Theft.- Whoever intending", "Theft", "Whoever intending"),
        ("Theft.—Whoever intending", "Theft", "Whoever intending"),
        ("Theft: Whoever intending", "Theft", "Whoever intending"),
        ("Theft:- Whoever intending", "Theft", "Whoever intending"),
        ("Freedom of speech, etc.- Every citizen", "Freedom of speech, etc", "Every citizen"),
        ("Right to education. The State shall", "Right to education", "The State shall"),
        ("Punishment for theft.", "Punishment for theft", ""),
    ],
)
def test_split_title(rest, title, body):
    assert split_title(rest) == (title, body)


def test_constitution_part_and_chapter_combine():
    lines = L(
        "PART I",
        "Introductory",
        "1. The Republic and its territories.- (1) Pakistan shall be a Federal Republic",
        "to be known as the Islamic Republic of Pakistan.",
        "PART II",
        "Fundamental Rights and Principles of Policy",
        "2. Islam to be State religion.- Islam shall be the State religion of Pakistan.",
        "CHAPTER 1. FUNDAMENTAL RIGHTS",
        "3. Elimination of exploitation.- The State shall ensure the elimination of all forms of exploitation.",
        "FIRST SCHEDULE",
        "4. Not an article",
    )
    secs = parse(lines, "constitution")
    assert [s.id for s in secs] == ["1", "2", "3"]
    assert secs[0].group == "Part I: Introductory"
    assert secs[2].group == "Part II: Fundamental Rights and Principles of Policy, Chapter 1: Fundamental Rights"


def test_clean_text_removes_amendment_markers():
    assert clean_text("shall be called the 1[Pakistan] Penal Code") == "shall be called the Pakistan Penal Code"
    assert clean_text("take effect * * * throughout") == "take effect throughout"


def test_numbering_gaps():
    secs = parse(PPC_LINES, "ppc")
    assert numbering_gaps(secs) == []


def test_two_digit_sections_not_split_by_footnote_prefix():
    # Regression: "10." used to parse as footnote "1" + section "0".
    lines = L(
        "1. Title.- Body one.",
        "9. Number.- Body nine.",
        "10. “Man” “Woman”. The word man denotes a male.",
        "[14. “Servant of the State”. The words denote all officers.",
        "11[15. Inserted.- Body fifteen.",
    )
    assert [s.id for s in parse(lines, "ppc")] == ["1", "9", "10", "14", "15"]


def test_clean_text_removes_spaced_footnote_marker():
    assert clean_text("for a term which 4 [shall not be less than fourteen years]") == "for a term which shall not be less than fourteen years"
    assert clean_text("under clause (4) of Article 10") == "under clause (4) of Article 10"


def test_constitution_titles_come_from_arrangement_of_articles():
    lines = L(
        "ARRANGEMENT OF ARTICLES",
        "1.    The Republic and its territories.",
        "2.    Islam to be State religion.",
        "3.    Elimination of exploitation and",
        "fulfilment of fundamental principle.",
        "PART I",
        "Introductory",
        "1.   (1) Pakistan shall be Federal Republic to be known as the Islamic Republic of Pakistan.",
        "2.   Islam shall be the State religion of Pakistan.",
        "3.   The State shall ensure the elimination of all forms of exploitation.",
    )
    secs = parse(lines, "constitution")
    assert [s.title for s in secs] == [
        "The Republic and its territories",
        "Islam to be State religion",
        "Elimination of exploitation and fulfilment of fundamental principle",
    ]
    assert secs[0].text.startswith("(1) Pakistan shall be Federal Republic")


def test_start_is_first_real_section_not_a_later_schedule_list():
    # Regression: a numbered list in a schedule with a long "1." entry was chosen as the start.
    lines = L(
        "1.  The Republic and its territories.",
        "2.  Islam to be State religion.",
        "1.   (1) Pakistan shall be Federal Republic to be known as the Islamic Republic of Pakistan, hereinafter referred to as Pakistan, and its territories shall comprise the Provinces.",
        "2.   Islam shall be the State religion of Pakistan, and every citizen shall have rights.",
        "[FIRST SCHEDULE",
        "1.   The Federal Legislative List, entry one, which is a very long entry that goes on and on about defence of the Federation and every part thereof, including preparation for defence.",
        "continues for many more characters of schedule text here and here and here and here.",
    )
    secs = parse(lines, "constitution")
    assert [s.id for s in secs] == ["1", "2"]
    assert "Federal Republic" in secs[0].text


def test_prefixed_and_bare_section_numbers():
    lines = L(
        "1. Title.- Body one.",
        "2.",
        "Fractions of terms of punishment. In calculating fractions.",
        "[[3. Trade mark. A mark used for denoting goods.",
        "*4. Sale of noxious food. Whoever sells.",
        "[“5. Ta'zir after waiver. Where all the wali.",
        "(1) this clause marker must stay in the body of 5",
    )
    secs = parse(lines, "ppc")
    assert [s.id for s in secs] == ["1", "2", "3", "4", "5"]
    assert secs[1].title == "Fractions of terms of punishment"
    assert "(1) this clause marker" in secs[4].text


def test_omitted_by_note_and_ppc_hyphen_ids():
    lines = L(
        "1. Title.- Body one.",
        "2. [Definition of “Queen”.] Omitted by A.O., 1961, Art. 2 and Sch.",
        "2F. Dishonestly issuing a cheque. Whoever dishonestly issues a cheque.",
    )
    secs = parse(lines, "ppc")
    assert secs[1].omitted and secs[1].title == "Omitted"
    assert "Omitted by A.O., 1961" in secs[1].text
    assert secs[2].id == "2-F"


def test_two_line_uppercase_chapter_heading():
    lines = L(
        "CHAPTER XVIII",
        "OF OFFENCES RELATING TO DOCUMENTS AND TO",
        "PROPERTY MARKS",
        "1. Title.- Body one.",
    )
    assert parse(lines, "ppc")[0].group == "Chapter XVIII: Of Offences relating to Documents and to Property Marks"


def test_title_wrapped_onto_next_line():
    lines = L(
        "1. Title.- Body one.",
        "2. Public servant taking gratification other than legal remuneration in respect of an official",
        "act. Whoever, being or expecting to be a public servant, accepts any gratification.",
    )
    s2 = parse(lines, "ppc")[1]
    assert s2.title == "Public servant taking gratification other than legal remuneration in respect of an official act"
    assert s2.text.startswith("Whoever, being or expecting")


def test_lowercase_chapter_reference_is_not_a_heading():
    lines = L(
        "1. Title.- Whoever does the thing described in",
        "Chapter XVI of this Code shall be punished.",
        "2. Next.- Body two.",
    )
    secs = parse(lines, "ppc")
    assert secs[0].group == "" and "Chapter XVI of this Code" in secs[0].text


def test_split_title_takes_earliest_separator():
    # Regression (PPC 359): the colon later in the body won over the earlier ". ".
    assert split_title("Kidnapping. Kidnapping is of two kinds: kidnapping from Pakistan") == (
        "Kidnapping", "Kidnapping is of two kinds: kidnapping from Pakistan")


def test_toc_dehyphenation_uses_book_vocabulary():
    from dafa.ingest.parse_sections import toc_title_map
    vocab = {"fundamental", "accordance"}
    titles = toc_title_map(["8. Laws inconsistent with Funda- mental Rights to be void.",
                            "13. Protection against double punishment and self- incrimination."], vocab)
    assert titles == {"8": "Laws inconsistent with Fundamental Rights to be void",
                      "13": "Protection against double punishment and self-incrimination"}


def test_split_title_lowercase_whoever():
    assert split_title("Punishment for hurt by corrosive substance. whoever causes hurt") == (
        "Punishment for hurt by corrosive substance", "whoever causes hurt")


def test_split_title_body_starting_at_clause_one():
    assert split_title("Making or using documents resembling currency-notes (1) Whoever makes, or causes") == (
        "Making or using documents resembling currency-notes", "(1) Whoever makes, or causes")
