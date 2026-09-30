import unittest

from domain import (
    RuleError,
    SchemaDefinitionError,
    evaluate_rule,
    schema_assignable,
    template_hashes,
    validate_instance,
)


class DomainPrimitiveTests(unittest.TestCase):
    def test_constrained_schema_validates_nested_values(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 2},
                "amount": {"type": "number", "minimum": 0},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
            },
            "required": ["name", "amount"],
            "additionalProperties": False,
        }
        self.assertEqual([], validate_instance(schema, {"name": "Acme", "amount": 12, "tags": ["new"]}))
        codes = {issue.code for issue in validate_instance(schema, {"name": "A", "amount": -1, "extra": True})}
        self.assertEqual({"VALUE_MIN_LENGTH", "VALUE_MINIMUM", "VALUE_ADDITIONAL_PROPERTY"}, codes)

    def test_unsupported_schema_keyword_fails_closed(self):
        with self.assertRaises(SchemaDefinitionError):
            validate_instance({"type": "string", "pattern": ".*"}, "anything")

    def test_date_formats_are_validated_and_preserved_by_assignability(self):
        date_schema = {"type": "string", "format": "date"}
        self.assertEqual([], validate_instance(date_schema, "2026-09-18"))
        self.assertIn("VALUE_FORMAT", {issue.code for issue in validate_instance(date_schema, "2026-02-30")})
        self.assertIn("VALUE_FORMAT", {issue.code for issue in validate_instance(date_schema, "not-a-date")})
        self.assertTrue(schema_assignable(date_schema, {"type": "string"})[0])
        self.assertFalse(schema_assignable({"type": "string"}, date_schema)[0])

        timestamp_schema = {"type": "string", "format": "date-time"}
        self.assertEqual([], validate_instance(timestamp_schema, "2026-09-18T10:15:30Z"))
        self.assertIn("VALUE_FORMAT", {issue.code for issue in validate_instance(timestamp_schema, "2026-09-18T10:15:30")})
        with self.assertRaises(SchemaDefinitionError):
            validate_instance({"type": "string", "format": "email"}, "person@example.test")
        with self.assertRaises(SchemaDefinitionError):
            validate_instance({"format": "date"}, "2026-09-18")

    def test_schema_assignability_is_conservative(self):
        source = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
        target = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
        self.assertTrue(schema_assignable(source, target)[0])
        target["properties"]["amount"] = {"type": "number"}
        target["required"].append("amount")
        self.assertFalse(schema_assignable(source, target)[0])

    def test_schema_assignability_honors_scalar_bounds(self):
        safe_string = {"type": "string", "minLength": 3, "maxLength": 8}
        string_target = {"type": "string", "minLength": 2, "maxLength": 10}
        self.assertTrue(schema_assignable(safe_string, string_target)[0])

        ok, issues = schema_assignable({"type": "string", "minLength": 1}, {"type": "string", "minLength": 2})
        self.assertFalse(ok)
        self.assertIn("SCHEMA_MIN_LENGTH_NOT_ASSIGNABLE", {issue.code for issue in issues})

        self.assertTrue(schema_assignable(
            {"type": "integer", "minimum": 0.5, "maximum": 4.9},
            {"type": "number", "minimum": 1, "maximum": 4},
        )[0])
        self.assertFalse(schema_assignable(
            {"type": "number", "minimum": 0.5},
            {"type": "number", "minimum": 1},
        )[0])

    def test_schema_assignability_checks_optional_and_additional_properties(self):
        source = {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "additionalProperties": False,
        }
        target = {
            "type": "object",
            "properties": {"label": {"type": "string", "minLength": 2}},
            "additionalProperties": False,
        }
        ok, issues = schema_assignable(source, target)
        self.assertFalse(ok)
        self.assertEqual("$.properties.label", issues[0].path)

        closed = {"type": "object", "properties": {}, "additionalProperties": False}
        open_source = {"type": "object", "properties": {}}
        ok, issues = schema_assignable(open_source, closed)
        self.assertFalse(ok)
        self.assertIn("SCHEMA_ADDITIONAL_PROPERTIES_NOT_ASSIGNABLE", {issue.code for issue in issues})

        typed_extras = {
            "type": "object",
            "additionalProperties": {"type": "string", "minLength": 3},
        }
        extras_target = {
            "type": "object",
            "additionalProperties": {"type": "string", "minLength": 2},
        }
        self.assertTrue(schema_assignable(typed_extras, extras_target)[0])

    def test_schema_assignability_checks_array_shape_and_items(self):
        source = {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": {"type": "string", "minLength": 2},
        }
        target = {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"type": "string", "minLength": 1},
        }
        self.assertTrue(schema_assignable(source, target)[0])

        unsafe = {"type": "array", "items": {"type": "string"}}
        ok, issues = schema_assignable(unsafe, {"type": "array", "maxItems": 2, "items": {"type": "string"}})
        self.assertFalse(ok)
        self.assertIn("SCHEMA_MAX_ITEMS_NOT_ASSIGNABLE", {issue.code for issue in issues})

    def test_finite_source_assignability_uses_actual_values(self):
        source = {"type": ["integer", "boolean"], "enum": [1]}
        self.assertTrue(schema_assignable(source, {"type": "integer"})[0])
        self.assertFalse(schema_assignable(source, {"type": "integer", "minimum": 2})[0])

        # Python considers True == 1; JSON Schema does not conflate them.
        issues = validate_instance({"type": ["integer", "boolean"], "enum": [1]}, True)
        self.assertIn("VALUE_ENUM", {issue.code for issue in issues})

        with self.assertRaises(SchemaDefinitionError):
            validate_instance({"enum": [1, 1.0]}, 1)

    def test_very_large_integers_do_not_overflow_validation(self):
        enormous = 10 ** 1000
        self.assertEqual([], validate_instance({"type": "integer", "minimum": 0}, enormous))
        self.assertTrue(schema_assignable(
            {"type": "integer", "minimum": enormous},
            {"type": "number", "minimum": enormous - 1},
        )[0])

    def test_rule_ast_supports_typed_boolean_logic(self):
        rule = {"op": "and", "rules": [
            {"op": "exists", "path": "supplier.id"},
            {"op": "gte", "path": "amount", "value": 1000},
            {"op": "not", "rule": {"op": "eq", "path": "region", "value": "blocked"}},
        ]}
        self.assertTrue(evaluate_rule(rule, {"supplier": {"id": "S-1"}, "amount": 1000, "region": "APAC"}))
        self.assertTrue(evaluate_rule(
            {"op": "gte", "path": "amount", "value": 1000.0},
            {"amount": 1000},
        ))
        self.assertFalse(evaluate_rule(rule, {"supplier": {}, "amount": 1000, "region": "APAC"}))
        with self.assertRaises(RuleError):
            evaluate_rule({"op": "eval", "value": "__import__('os')"}, {})

    def test_semantic_and_layout_hashes_are_distinct(self):
        template = {"id": "t", "nodes": [{"id": "n", "agentId": "a", "x": 1, "y": 2}], "edges": []}
        first = template_hashes(template)
        template["nodes"][0]["x"] = 99
        second = template_hashes(template)
        self.assertEqual(first["semanticHash"], second["semanticHash"])
        self.assertNotEqual(first["layoutHash"], second["layoutHash"])


if __name__ == "__main__":
    unittest.main()
