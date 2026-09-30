import unittest

from domain import content_hash
from evidence import (
    ActionReceipt,
    Claim,
    DecisionPacket,
    EvidenceError,
    EvidenceGraph,
    EvidenceItem,
    SourceSnapshot,
    Transformation,
)


NOW = "2026-09-24T12:00:00Z"


class EvidenceGraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = EvidenceGraph()
        self.content = "Supplier S-100 has amount 1250."
        self.graph.add_source(SourceSnapshot("src", "fixture://supplier/S-100", "v1", content_hash(self.content), NOW, "confidential", "text/plain", self.content))
        self.graph.add_evidence(EvidenceItem("ev", "extraction", "src", NOW, "confidential", "extractor@1", "S-100", "supplier.id", 9, 14))

    def test_bounds_and_access_inheritance_fail_closed(self):
        with self.assertRaises(EvidenceError):
            self.graph.add_evidence(EvidenceItem("public", "extraction", "src", NOW, "public", "extractor@1", "bad", excerpt_start=0, excerpt_end=999))

    def test_claims_keep_conflicts_visible_and_validate_deterministic_values(self):
        self.graph.add_evidence(EvidenceItem("other", "human", "src", NOW, "confidential", "reviewer", "S-200"))
        with self.assertRaises(EvidenceError):
            self.graph.add_claim(Claim("claim", "Supplier identity", "id", "spaces are invalid", ("ev",), status="supported"))
        with self.assertRaises(EvidenceError):
            self.graph.add_claim(Claim("claim", "Supplier identity", "id", "S-100", ("ev",), ("other",), status="supported"))
        self.graph.add_claim(Claim("claim", "Supplier identity", "id", "S-100", ("ev",), ("other",), status="conflicted"))
        self.assertEqual("conflicted", self.graph.claims["claim"].status)

    def test_transform_decision_and_receipt_references_are_real(self):
        self.graph.add_transformation(Transformation("tx", "normalize", "normalizer@1", ("ev",), "Normalize supplier identity."))
        fingerprint = "a" * 64
        packet = DecisionPacket("decision", fingerprint, "fixture-ticket", {"apiKey": "never-export"}, ("ev",), ("reviewer",), ("External CSR contract unconfirmed",), "2026-09-25T12:00:00Z", "Commit one fixture ticket", "confidential")
        self.graph.add_decision_packet(packet)
        self.graph.add_receipt(ActionReceipt("receipt", fingerprint, "op-1", "acknowledged", "AX-1", NOW, ("ev",)))
        exported = self.graph.to_dict(maximum_access="confidential")
        self.assertEqual("[REDACTED]", exported["decisionPackets"][0]["payload"]["apiKey"])
        self.assertNotIn("content", exported["sources"][0])
        self.assertEqual("acknowledged", exported["actionReceipts"][0]["state"])

    def test_access_filtered_export_does_not_leak_references(self):
        self.graph.add_claim(Claim("claim", "Supplier identity", "id", "S-100", ("ev",), status="supported"))
        public = self.graph.to_dict(maximum_access="public")
        self.assertEqual([], public["sources"])
        self.assertEqual([], public["evidence"])
        self.assertEqual([], public["claims"])


if __name__ == "__main__":
    unittest.main()
