"""First-class evidence graph records and deterministic validation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
from typing import Any, Iterable

from domain import content_hash


EVIDENCE_SCHEMA_VERSION = "axiom.evidence.v1"
ACCESS_ORDER = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
EVIDENCE_KINDS = {"source", "extraction", "calculation", "inference", "human"}
_SECRET_KEY = re.compile(r"(?:secret|password|token|api[_-]?key|private[_-]?key|authorization)", re.I)


class EvidenceError(ValueError):
    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("; ".join(issue["message"] for issue in issues))


def _time(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class SourceSnapshot:
    id: str
    uri: str
    version: str
    content_hash: str
    observed_at: str
    access_label: str
    media_type: str
    content: str | None = None


@dataclass(frozen=True)
class Transformation:
    id: str
    kind: str
    producer_version: str
    input_evidence_ids: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    kind: str
    source_id: str
    observed_at: str
    access_label: str
    producer_version: str
    value: Any
    field_path: str | None = None
    excerpt_start: int | None = None
    excerpt_end: int | None = None
    transformation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    claim_type: str
    value: Any
    supporting_evidence_ids: tuple[str, ...]
    conflicting_evidence_ids: tuple[str, ...] = ()
    status: str = "unverified"


@dataclass(frozen=True)
class DecisionPacket:
    id: str
    action_fingerprint: str
    target: str
    payload: dict[str, Any]
    evidence_ids: tuple[str, ...]
    policy_obligations: tuple[str, ...]
    remaining_uncertainty: tuple[str, ...]
    expires_at: str
    unlocks: str
    access_label: str


@dataclass(frozen=True)
class ActionReceipt:
    id: str
    action_fingerprint: str
    operation_key: str
    state: str
    provider_reference: str | None
    observed_at: str
    evidence_ids: tuple[str, ...] = ()


@dataclass
class EvidenceGraph:
    sources: dict[str, SourceSnapshot] = field(default_factory=dict)
    transformations: dict[str, Transformation] = field(default_factory=dict)
    evidence: dict[str, EvidenceItem] = field(default_factory=dict)
    claims: dict[str, Claim] = field(default_factory=dict)
    decisions: dict[str, DecisionPacket] = field(default_factory=dict)
    receipts: dict[str, ActionReceipt] = field(default_factory=dict)
    schema_version: str = EVIDENCE_SCHEMA_VERSION

    def add_source(self, source: SourceSnapshot) -> None:
        issues = []
        if source.id in self.sources:
            issues.append({"field": "id", "message": "Source ID already exists."})
        if source.access_label not in ACCESS_ORDER:
            issues.append({"field": "accessLabel", "message": "Source access label is unsupported."})
        try:
            _time(source.observed_at)
        except ValueError:
            issues.append({"field": "observedAt", "message": "Source observedAt is invalid."})
        if not re.fullmatch(r"[0-9a-f]{64}", source.content_hash):
            issues.append({"field": "contentHash", "message": "Source content hash must be SHA-256 hex."})
        if source.content is not None and content_hash(source.content) != source.content_hash:
            issues.append({"field": "contentHash", "message": "Source content does not match its recorded hash."})
        if issues:
            raise EvidenceError(issues)
        self.sources[source.id] = source

    def add_transformation(self, transformation: Transformation) -> None:
        issues = []
        if transformation.id in self.transformations:
            issues.append({"field": "id", "message": "Transformation ID already exists."})
        missing = [ident for ident in transformation.input_evidence_ids if ident not in self.evidence]
        if missing:
            issues.append({"field": "inputEvidenceIds", "message": "Transformation references unknown evidence: " + ", ".join(missing)})
        if issues:
            raise EvidenceError(issues)
        self.transformations[transformation.id] = transformation

    def add_evidence(self, item: EvidenceItem) -> None:
        issues = []
        source = self.sources.get(item.source_id)
        if item.id in self.evidence:
            issues.append({"field": "id", "message": "Evidence ID already exists."})
        if not source:
            issues.append({"field": "sourceId", "message": "Evidence references an unknown source snapshot."})
        if item.kind not in EVIDENCE_KINDS:
            issues.append({"field": "kind", "message": "Evidence kind is unsupported."})
        if item.access_label not in ACCESS_ORDER:
            issues.append({"field": "accessLabel", "message": "Evidence access label is unsupported."})
        elif source and ACCESS_ORDER[item.access_label] < ACCESS_ORDER[source.access_label]:
            issues.append({"field": "accessLabel", "message": "Derived evidence cannot be less restricted than its source."})
        try:
            _time(item.observed_at)
        except ValueError:
            issues.append({"field": "observedAt", "message": "Evidence observedAt is invalid."})
        span_values = (item.excerpt_start, item.excerpt_end)
        if any(value is not None for value in span_values):
            if (not all(isinstance(value, int) and not isinstance(value, bool) for value in span_values)
                    or item.excerpt_start < 0 or item.excerpt_end <= item.excerpt_start):
                issues.append({"field": "excerpt", "message": "Excerpt uses valid zero-based [start,end) offsets."})
            elif not source or source.content is None:
                issues.append({"field": "excerpt", "message": "Excerpt offsets require retained source content."})
            elif item.excerpt_end > len(source.content):
                issues.append({"field": "excerpt", "message": "Excerpt end exceeds the source boundary."})
        missing_transforms = [ident for ident in item.transformation_ids if ident not in self.transformations]
        if missing_transforms:
            issues.append({"field": "transformationIds", "message": "Evidence references unknown transformations."})
        if issues:
            raise EvidenceError(issues)
        self.evidence[item.id] = item

    def add_claim(self, claim: Claim) -> None:
        issues = []
        if claim.id in self.claims:
            issues.append({"field": "id", "message": "Claim ID already exists."})
        all_refs = set(claim.supporting_evidence_ids) | set(claim.conflicting_evidence_ids)
        missing = sorted(all_refs - set(self.evidence))
        if missing:
            issues.append({"field": "evidenceIds", "message": "Claim references unknown evidence: " + ", ".join(missing)})
        overlap = set(claim.supporting_evidence_ids) & set(claim.conflicting_evidence_ids)
        if overlap:
            issues.append({"field": "evidenceIds", "message": "The same evidence cannot both support and conflict with one claim."})
        if claim.status not in {"supported", "conflicted", "unsupported", "unverified"}:
            issues.append({"field": "status", "message": "Claim status is unsupported."})
        deterministic = {
            "id": lambda value: isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value)),
            "amount": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
            "date": lambda value: _valid_date(value),
        }
        if claim.claim_type in deterministic and not deterministic[claim.claim_type](claim.value):
            issues.append({"field": "value", "message": f"Claim value is invalid for deterministic type {claim.claim_type}."})
        if claim.status == "supported" and not claim.supporting_evidence_ids:
            issues.append({"field": "status", "message": "A supported claim needs at least one supporting evidence item."})
        if claim.conflicting_evidence_ids and claim.status != "conflicted":
            issues.append({"field": "status", "message": "A claim with conflicting evidence must remain visibly conflicted."})
        if issues:
            raise EvidenceError(issues)
        self.claims[claim.id] = claim

    def add_decision_packet(self, packet: DecisionPacket) -> None:
        issues = []
        if packet.id in self.decisions:
            issues.append({"field": "id", "message": "Decision packet ID already exists."})
        if not re.fullmatch(r"[0-9a-f]{64}", packet.action_fingerprint):
            issues.append({"field": "actionFingerprint", "message": "Decision packet needs a canonical SHA-256 action fingerprint."})
        missing = sorted(set(packet.evidence_ids) - set(self.evidence))
        if missing:
            issues.append({"field": "evidenceIds", "message": "Decision packet references unknown evidence."})
        if packet.access_label not in ACCESS_ORDER:
            issues.append({"field": "accessLabel", "message": "Decision packet access label is unsupported."})
        else:
            for ident in packet.evidence_ids:
                evidence = self.evidence.get(ident)
                if evidence and ACCESS_ORDER[packet.access_label] < ACCESS_ORDER[evidence.access_label]:
                    issues.append({"field": "accessLabel", "message": "Decision packet must inherit the strongest evidence restriction."})
                    break
        try:
            _time(packet.expires_at)
        except ValueError:
            issues.append({"field": "expiresAt", "message": "Decision packet expiry is invalid."})
        if issues:
            raise EvidenceError(issues)
        self.decisions[packet.id] = packet

    def add_receipt(self, receipt: ActionReceipt) -> None:
        issues = []
        if receipt.id in self.receipts:
            issues.append({"field": "id", "message": "Action receipt ID already exists."})
        if receipt.state not in {"prepared", "dispatched", "acknowledged", "unknown", "reconciled", "compensated"}:
            issues.append({"field": "state", "message": "Action receipt state is unsupported."})
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.action_fingerprint):
            issues.append({"field": "actionFingerprint", "message": "Action receipt fingerprint is invalid."})
        if set(receipt.evidence_ids) - set(self.evidence):
            issues.append({"field": "evidenceIds", "message": "Action receipt references unknown evidence."})
        try:
            _time(receipt.observed_at)
        except ValueError:
            issues.append({"field": "observedAt", "message": "Action receipt observedAt is invalid."})
        if issues:
            raise EvidenceError(issues)
        self.receipts[receipt.id] = receipt

    def to_dict(self, *, maximum_access: str = "restricted", include_source_content: bool = False) -> dict[str, Any]:
        if maximum_access not in ACCESS_ORDER:
            raise ValueError("maximum_access is unsupported")
        allowed = ACCESS_ORDER[maximum_access]
        sources = []
        allowed_source_ids = set()
        for source in self.sources.values():
            if ACCESS_ORDER[source.access_label] <= allowed:
                value = asdict(source)
                if not include_source_content:
                    value.pop("content", None)
                else:
                    value["content"] = _redact(value.get("content"))
                sources.append(value)
                allowed_source_ids.add(source.id)
        evidence = [asdict(item) for item in self.evidence.values()
                    if item.source_id in allowed_source_ids and ACCESS_ORDER[item.access_label] <= allowed]
        visible_evidence = {item["id"] for item in evidence}
        claims = [asdict(claim) for claim in self.claims.values()
                  if set(claim.supporting_evidence_ids) | set(claim.conflicting_evidence_ids) <= visible_evidence]
        decisions = [asdict(packet) for packet in self.decisions.values()
                     if ACCESS_ORDER[packet.access_label] <= allowed and set(packet.evidence_ids) <= visible_evidence]
        receipts = [asdict(receipt) for receipt in self.receipts.values() if set(receipt.evidence_ids) <= visible_evidence]
        result = {
            "schemaVersion": self.schema_version,
            "sources": sources,
            "transformations": [asdict(item) for item in self.transformations.values()
                                if set(item.input_evidence_ids) <= visible_evidence],
            "evidence": evidence,
            "claims": claims,
            "decisionPackets": decisions,
            "actionReceipts": receipts,
        }
        return _redact(result)


def _valid_date(value: Any) -> bool:
    try:
        _time(value)
        return True
    except (ValueError, TypeError):
        return False


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def strongest_access(labels: Iterable[str]) -> str:
    labels = tuple(labels)
    if any(label not in ACCESS_ORDER for label in labels):
        raise ValueError("Unsupported access label")
    return max(labels, key=ACCESS_ORDER.get) if labels else "public"
