"""Shared fixtures. The tiny corpus below is test data only (short excerpts),
so tests run in milliseconds and never depend on the real processed books."""

from __future__ import annotations

import pytest

from dafa.models import ScheduleInfo, Section
from dafa.retrieval.store import LawStore

FIXTURE = [
    Section(book="ppc", id="378", title="Theft", group="CHAPTER XVII OF OFFENCES AGAINST PROPERTY",
            text="Whoever, intending to take dishonestly any movable property out of the possession of any person without that person's consent, moves that property in order to such taking, is said to commit theft."),
    Section(book="ppc", id="379", title="Punishment for theft", group="CHAPTER XVII OF OFFENCES AGAINST PROPERTY",
            text="Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.",
            schedule=ScheduleInfo(offence="Theft", cognizable="Shall not arrest without warrant", bailable="Not bailable", compoundable="Compoundable", punishment="Imprisonment of either description for 3 years, or fine, or both", court="Any Magistrate")),
    Section(book="ppc", id="390", title="Robbery", group="CHAPTER XVII OF OFFENCES AGAINST PROPERTY",
            text="In all robbery there is either theft or extortion. Theft is robbery if, in order to the committing of the theft, the offender voluntarily causes or attempts to cause to any person death or hurt or wrongful restraint."),
    Section(book="ppc", id="302", title="Punishment of qatl-i-amd", group="CHAPTER XVI OF OFFENCES AFFECTING THE HUMAN BODY",
            text="Whoever commits qatl-i-amd shall, subject to the provisions of this Chapter be (a) punished with death as qisas; (b) punished with death or imprisonment for life as ta'zir."),
    Section(book="ppc", id="420", title="Cheating and dishonestly inducing delivery of property", group="CHAPTER XVII OF OFFENCES AGAINST PROPERTY",
            text="Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine."),
    Section(book="ppc", id="489-F", title="Dishonestly issuing a cheque", group="CHAPTER XVIII OF OFFENCES RELATING TO DOCUMENTS",
            text="Whoever dishonestly issues a cheque towards re-payment of a loan or fulfilment of an obligation which is dishonoured on presentation, shall be punishable with imprisonment which may extend to three years, or with fine, or with both."),
    Section(book="constitution", id="10", title="Safeguards as to arrest and detention", group="PART II Fundamental Rights and Principles of Policy",
            text="(1) No person who is arrested shall be detained in custody without being informed, as soon as may be, of the grounds for such arrest, nor shall he be denied the right to consult and be defended by a legal practitioner of his choice. (2) Every person who is arrested and detained in custody shall be produced before a magistrate within a period of twenty-four hours of such arrest."),
    Section(book="constitution", id="19", title="Freedom of speech, etc.", group="PART II Fundamental Rights and Principles of Policy",
            text="Every citizen shall have the right to freedom of speech and expression, and there shall be freedom of the press, subject to any reasonable restrictions imposed by law."),
    Section(book="constitution", id="25A", title="Right to education", group="PART II Fundamental Rights and Principles of Policy",
            text="The State shall provide free and compulsory education to all children of the age of five to sixteen years in such manner as may be determined by law."),
]


@pytest.fixture
def store() -> LawStore:
    return LawStore(FIXTURE)


class FakeLLM:
    """Scripted stand-in for GroqClient: returns queued JSON replies."""

    api_key = "fake"

    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def chat_json(self, system, user, usage=None, **kw):
        self.calls.append((system, user))
        if usage is not None:
            usage.calls += 1
        return self.replies.pop(0)
