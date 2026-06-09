from __future__ import annotations

import unittest
from pathlib import Path

from runtime.config.spec_loader import load_spec


class RuntimeSpecLoaderTests(unittest.TestCase):
    def test_load_spec_reads_schemas_and_registries(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]

        spec = load_spec(repo_root)

        self.assertIn("message_envelope", spec.schemas)
        self.assertIn("task_state_machine", spec.schemas)
        self.assertIn("skill_invocation", spec.schemas)
        self.assertIn("skill_result", spec.schemas)
        self.assertIn("error_payload", spec.schemas)

        self.assertIn("agents", spec.registries)
        self.assertIn("skills", spec.registries)

        self.assertIn("coding.generate_patch@1.0.0", spec.skills)
        self.assertEqual(spec.skills["coding.generate_patch@1.0.0"]["agent_binding"], "coding")

        envelope_schema = spec.schemas["message_envelope"]
        self.assertEqual(envelope_schema.get("title"), "Message Envelope")
        self.assertEqual((spec.message_envelope or {}).get("schema_ref"), "schemas/message-envelope.schema.json")


if __name__ == "__main__":
    unittest.main()
