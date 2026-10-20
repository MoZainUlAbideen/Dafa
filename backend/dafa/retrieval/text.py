"""Tokenising and query normalisation.

Statutes use a fixed legal vocabulary ("theft", "qatl-i-amd", "dishonestly"),
while people type "mobile chheen liya" or "chori". This module closes that gap
cheaply and deterministically with:
  1. a small Roman Urdu / Urdu -> legal English glossary
  2. light stemming so "cheated" matches "cheating"
The LLM query rewriter (pipeline/answer.py) does the heavier lifting when an
API key is available; this layer keeps search useful without one.
"""

from __future__ import annotations

import re

STOPWORDS = set(
    """a an the of to in on for by with is are was were be been being it its this that
    these those or and as at from into than then there their his her he she they them
    what which who whom whose when where why how do does did can could should would may
    might shall will i me my we our you your if not no any all such other under under
    section article sections articles law laws pakistan pakistani act code penal
    ki ka ke ko hai hain mein me se par kya kia tha thi aur ya bhi""".split()
)

# Roman Urdu / Urdu words -> legal English terms that appear in the statutes.
GLOSSARY: dict[str, list[str]] = {
    "chori": ["theft"], "chor": ["theft"], "churaya": ["theft"], "chura": ["theft"],
    "چوری": ["theft"],
    "chheen": ["robbery", "snatching"], "chheena": ["robbery", "snatching"],
    "chhina": ["robbery", "snatching"], "chheenna": ["robbery", "snatching"],
    "daka": ["dacoity", "robbery"], "dakaiti": ["dacoity"], "dacoit": ["dacoity"],
    "ڈکیتی": ["dacoity"],
    "qatl": ["qatl", "murder"], "katal": ["qatl", "murder"], "qatal": ["qatl", "murder"],
    "قتل": ["qatl"], "murder": ["qatl", "murder"], "kill": ["qatl"], "killed": ["qatl"],
    "dhoka": ["cheating"], "dhokay": ["cheating"], "dhokha": ["cheating"], "fraud": ["cheating"],
    "دھوکہ": ["cheating"], "scam": ["cheating"],
    "rishwat": ["gratification", "bribery"], "bribe": ["gratification", "bribery"],
    "رشوت": ["gratification"],
    "maarpeet": ["hurt"], "maar": ["hurt"], "mara": ["hurt"], "pitai": ["hurt"],
    "beat": ["hurt"], "beaten": ["hurt"], "assault": ["assault", "hurt"],
    "zakhmi": ["hurt"], "injury": ["hurt"], "injured": ["hurt"],
    "agwa": ["kidnapping", "abduction"], "aghwa": ["kidnapping", "abduction"],
    "اغوا": ["kidnapping", "abduction"], "kidnap": ["kidnapping"], "kidnapped": ["kidnapping"],
    "jaali": ["forgery"], "jali": ["forgery"], "fake": ["forgery", "counterfeit"],
    "forged": ["forgery"], "signature": ["forgery"],
    "dhamki": ["intimidation"], "dhamkiyan": ["intimidation"], "threat": ["intimidation"],
    "threatened": ["intimidation"], "blackmail": ["extortion"], "bhatta": ["extortion"],
    "tauheen": ["defamation"], "badnami": ["defamation"], "defame": ["defamation"],
    "cheque": ["cheque", "dishonestly"], "check": ["cheque"], "bounce": ["cheque"],
    "bounced": ["cheque"],
    "zameen": ["property"], "qabza": ["trespass"], "kabza": ["trespass"],
    "ghar": ["house"], "ghus": ["trespass"], "ghusa": ["trespass"],
    "aag": ["fire", "mischief"], "talaaq": ["marriage"], "shaadi": ["marriage"],
    "nikah": ["marriage"], "bivi": ["wife"], "shohar": ["husband"],
    "harassment": ["harassment", "insult", "modesty"], "harass": ["harassment", "modesty"],
    "chhed": ["modesty", "harassment"], "chherna": ["modesty", "harassment"],
    "acid": ["corrosive", "acid"], "tezaab": ["corrosive"],
    "hathiyar": ["weapon"], "pistol": ["weapon", "firearm"],
    "giraftari": ["arrest", "detention"], "girftar": ["arrest", "detention"],
    "arrest": ["arrest", "detention"], "arrested": ["arrest", "detention"],
    "police": ["police", "arrest"], "adalat": ["court"], "court": ["court"],
    "azadi": ["freedom", "liberty"], "taleem": ["education"], "education": ["education"],
    "school": ["education"], "vote": ["election", "vote"], "election": ["election"],
    "intikhab": ["election"], "mazhab": ["religion"], "religion": ["religion"],
    "speech": ["speech", "expression"], "bolne": ["speech"], "protest": ["assembly"],
    "jalsa": ["assembly"], "jaidad": ["property"], "property": ["property"],
    "privacy": ["privacy", "dignity"], "naukri": ["employment"], "job": ["employment"],
    "majdoor": ["labour"], "forced": ["forced", "slavery"], "begaar": ["forced", "labour"],
    "wazir": ["minister"], "pm": ["prime", "minister"], "president": ["president"],
    "sadar": ["president"], "judge": ["judge"], "jaj": ["judge"],
    "khudkushi": ["suicide"], "suicide": ["suicide"], "zehar": ["poison"],
    "nasha": ["intoxication"], "sharab": ["intoxication"],
    "blasphemy": ["religion", "prophet", "defiling"], "toheen": ["insult", "defamation"],
    "riot": ["rioting"], "fasad": ["rioting", "affray"], "jhagra": ["affray", "hurt"],
}

_TOKEN_RE = re.compile(r"[\w؀-ۿ]+(?:-[\w]+)*", re.UNICODE)


def stem(tok: str) -> str:
    """Very light suffix stripping. Deliberately conservative: legal terms
    like 'qatl-i-amd' and 'dishonestly' must survive intact enough to match."""
    if len(tok) <= 4 or not tok.isascii():
        return tok
    for suf in ("ings", "ing", "edly", "ed", "es", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def tokenize(text: str) -> list[str]:
    toks = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in STOPWORDS or raw.isdigit():
            continue
        toks.append(stem(raw))
        if "-" in raw:  # also index the parts: "qatl-i-amd" -> qatl, amd
            toks.extend(stem(p) for p in raw.split("-") if len(p) > 2 and p not in STOPWORDS)
    return toks


def expand_query(query: str) -> list[str]:
    """Tokenise a user query and add glossary translations."""
    toks = tokenize(query)
    extra: list[str] = []
    for raw in _TOKEN_RE.findall(query.lower()):
        for term in GLOSSARY.get(raw, []):
            extra.extend(tokenize(term))
    return toks + extra
