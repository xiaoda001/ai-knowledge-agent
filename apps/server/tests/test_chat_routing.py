import unittest
from types import SimpleNamespace

from app.services.chat_routing import cited_sources, resolve_knowledge_base_scope, route_catalog


class AutomaticKnowledgeBaseRoutingTests(unittest.TestCase):
    def test_catalog_exposes_per_turn_refs_and_resolver_maps_only_known_refs(self):
        bases = [
            SimpleNamespace(id="finance-id", name="财务与采购", description="差旅和报销"),
            SimpleNamespace(id="support-id", name="产品支持", description="保修和维修"),
        ]

        catalog, id_by_ref = route_catalog(bases, lambda value: value)

        self.assertEqual(catalog[0], {
            "ref": "kb_1", "name": "财务与采购", "description": "差旅和报销",
        })
        self.assertEqual(resolve_knowledge_base_scope(["kb_1", "unknown"], id_by_ref,
                                                     ["finance-id", "support-id"]), ["finance-id"])
        self.assertEqual(resolve_knowledge_base_scope(["unknown"], id_by_ref,
                                                     ["finance-id", "support-id"]),
                         ["finance-id", "support-id"])

    def test_cited_sources_filters_candidates_and_keeps_original_numbers(self):
        sources = [{"chunk_id": f"chunk-{index}"} for index in range(1, 5)]

        cited = cited_sources("报销规则参考 [1]，审批时限见 [3]。", sources)

        self.assertEqual(cited, [
            {"chunk_id": "chunk-1", "source_number": 1},
            {"chunk_id": "chunk-3", "source_number": 3},
        ])
        self.assertEqual(cited_sources("未提供引用。", sources), [])


if __name__ == "__main__":
    unittest.main()
