from pathlib import Path
import tempfile
import unittest

from scripts.audit_librarian_safety import audit_workflows


SAFE = """name: Publish
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  publish:
    steps:
      - run: python -m pip install --requirement requirements.txt
      - env:
          KANKA_API_TOKEN: ${{ secrets.KANKA_API_TOKEN }}
          KANKA_ENABLE_WRITES: FOGPORT_410879
        run: python scripts/publish.py
"""


class LibrarianSafetyTests(unittest.TestCase):
    def audit(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "publish.yml").write_text(text, encoding="utf-8")
            return audit_workflows(Path(directory))

    def test_manual_read_only_writer_is_safe(self):
        self.assertEqual(self.audit(SAFE), [])

    def test_automatic_kanka_triggers_are_rejected(self):
        for trigger in ("push", "pull_request", "schedule"):
            with self.subTest(trigger):
                unsafe = SAFE.replace("  workflow_dispatch:\n", f"  workflow_dispatch:\n  {trigger}:\n")
                self.assertTrue(any("must not run" in error for error in self.audit(unsafe)))

    def test_manual_dispatch_is_required(self):
        errors = self.audit(SAFE.replace("  workflow_dispatch:\n", ""))
        self.assertTrue(any("must require workflow_dispatch" in error for error in errors))

    def test_repository_write_permission_is_rejected(self):
        errors = self.audit(SAFE.replace("contents: read", "contents: write"))
        self.assertTrue(any("must not have repository write" in error for error in errors))

    def test_librarian_package_install_is_required(self):
        errors = self.audit(
            SAFE.replace("      - run: python -m pip install --requirement requirements.txt\n", "")
        )
        self.assertTrue(any("must install the Librarian package" in error for error in errors))

    def test_workflow_cannot_push_receipts(self):
        errors = self.audit(SAFE + "\n      - run: git push\n")
        self.assertTrue(any("must not push receipts" in error for error in errors))

    def test_explicit_fogport_write_enable_is_required(self):
        errors = self.audit(SAFE.replace("          KANKA_ENABLE_WRITES: FOGPORT_410879\n", ""))
        self.assertTrue(any("must explicitly enable FOGPORT_410879" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
