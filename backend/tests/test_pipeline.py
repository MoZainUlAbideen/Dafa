from conftest import FakeLLM

from dafa.pipeline.answer import Pipeline, detect_language


def test_detect_language():
    assert detect_language("What is the punishment for theft?") == "en"
    assert detect_language("chori ki saza kya hai") == "roman_ur"
    assert detect_language("چوری کی سزا کیا ہے") == "ur"


def test_search_only_mode_without_llm(store):
    res = Pipeline(store, llm=None).answer("what is the punishment for theft")
    assert res.mode == "search_only"
    assert res.sections and res.sections[0].id in {"378", "379"}


def test_direct_reference_skips_rewrite(store):
    llm = FakeLLM([{"answer": "It punishes theft with up to 3 years [ppc:379].",
                    "quotes": [{"key": "ppc:379", "text": "Whoever commits theft"}]}])
    res = Pipeline(store, llm=llm).answer("section 379")
    assert len(llm.calls) == 1  # no rewrite call for an exact reference
    assert res.mode == "answer" and res.verified
    assert res.sections[0].id == "379"


def test_full_flow_with_rewrite(store):
    llm = FakeLLM([
        {"language": "roman_ur", "in_scope": True, "book": "ppc", "english_query": "phone stolen",
         "keywords": ["theft", "movable property"]},
        {"answer": "Chori ki saza 3 saal tak qaid hai [ppc:379].", "quotes": []},
    ])
    res = Pipeline(store, llm=llm).answer("mera phone chori ho gaya, saza kya hai")
    assert res.mode == "answer" and res.verified
    assert res.language == "roman_ur"
    assert {s.id for s in res.sections[:2]} & {"378", "379"}


def test_out_of_scope(store):
    llm = FakeLLM([{"language": "en", "in_scope": False, "book": "both", "english_query": "", "keywords": []}])
    res = Pipeline(store, llm=llm).answer("best biryani recipe")
    assert res.mode == "out_of_scope" and not res.sections


def test_repair_round_fixes_bad_citation(store):
    llm = FakeLLM([
        {"answer": "Theft: see [ppc:381].", "quotes": []},  # invented section
        {"answer": "Theft is punished under [ppc:379].", "quotes": []},  # fixed
    ])
    res = Pipeline(store, llm=llm).answer("section 379")
    assert len(llm.calls) == 2
    assert "REPAIR" not in res.answer and res.verified
    assert "Cited sections that were not provided" in llm.calls[1][1]


def test_unfixable_answer_is_stripped_and_flagged(store):
    bad = {"answer": "See [ppc:381] and [ppc:379].", "quotes": [{"key": "ppc:379", "text": "made up words"}]}
    llm = FakeLLM([bad, bad])
    res = Pipeline(store, llm=llm).answer("section 379")
    assert not res.verified
    assert "[ppc:381]" not in res.answer and "[ppc:379]" in res.answer
    assert res.quotes == [] and res.warnings


def test_rate_limited_writer_falls_back_to_sections_with_a_busy_note(store):
    from dafa.llm.groq_client import LLMError

    class BusyLLM:
        api_key = "x"

        def chat_json(self, *a, **k):
            raise LLMError("Groq rate limit (429): would need to wait 40s (max 8s)")

    res = Pipeline(store, llm=BusyLLM()).answer("section 379")
    assert res.mode == "search_only" and res.sections[0].id == "379"
    assert "busy" in res.warnings[-1]
