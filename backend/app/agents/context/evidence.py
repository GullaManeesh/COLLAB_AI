from dataclasses import dataclass, field
from typing import Literal


Assessment = Literal["well_supported", "partially_supported", "insufficient_evidence"]
Coverage = Literal["complete", "partial", "unknown"]


@dataclass
class EvidenceAssessment:
    assessment: Assessment
    explanation: str
    coverage: Coverage = "unknown"
    limitations: list[str] = field(default_factory=list)


def assess_evidence(sources: list[dict], citations: list[dict], *, complete: bool | None = None, limitations: list[str] | None = None) -> EvidenceAssessment:
    limitations = list(limitations or [])
    cited = {source.get("chunk_id") or source.get("source_id") for source in citations}
    valid = [source for source in sources if (source.get("chunk_id") or source.get("source_id")) in cited]
    if not sources or not valid:
        return EvidenceAssessment(
            "insufficient_evidence",
            "No relevant, verifiable workspace source supports an answer to this request.",
            "unknown",
            limitations or ["No relevant source passages were found."],
        )
    if complete is False:
        limitations.append("Not every indexed section was available within the processing limit.")
        return EvidenceAssessment(
            "partially_supported",
            "The cited passages support part of the response, but document processing was incomplete.",
            "partial",
            limitations,
        )
    if complete is True and len(valid) == len(sources):
        return EvidenceAssessment(
            "well_supported",
            "All indexed document sections in scope were processed and the response cites the verified source passages.",
            "complete",
            limitations,
        )
    strong = [source for source in valid if isinstance(source.get("score"), (int, float)) and source["score"] >= 0.35]
    if strong and len(strong) == len(valid) and not limitations:
        return EvidenceAssessment(
            "well_supported",
            "The response cites relevant passages retrieved from the authorized workspace.",
            "complete" if complete is True else "unknown",
            [],
        )
    limitations.append("Some requested details may not be covered by the retrieved passages.")
    return EvidenceAssessment(
        "partially_supported",
        "The cited passages support some details, while retrieval cannot establish that all requested details are covered.",
        "partial" if complete is not None else "unknown",
        limitations,
    )
