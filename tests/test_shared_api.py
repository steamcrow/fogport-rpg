"""Safety tests for the shared kanka_librarian.api toolbox."""

from __future__ import annotations

import unittest
from unittest import mock

from kanka_librarian import api


class FakeResponse:
    def __init__(self, status: int, body: object) -> None:
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = str(body)
        self._body = body
        self.headers: dict[str, str] = {}

    def json(self) -> object:
        return self._body


class HeaderTests(unittest.TestCase):
    def test_no_content_type_by_default_so_uploads_work(self) -> None:
        built = api.headers("tok")
        self.assertNotIn("Content-Type", built)
        self.assertEqual(built["Authorization"], "Bearer tok")

    def test_json_body_adds_content_type(self) -> None:
        built = api.headers("tok", json_body=True)
        self.assertEqual(built["Content-Type"], "application/json")


class RequestTests(unittest.TestCase):
    def test_failure_raises_system_exit_with_status(self) -> None:
        with mock.patch.object(
            api.requests, "request", return_value=FakeResponse(500, "boom")
        ):
            with self.assertRaises(SystemExit) as caught:
                api.request("tok", "GET", "campaigns/1")
        self.assertIn("HTTP 500", str(caught.exception))

    def test_success_returns_parsed_body(self) -> None:
        with mock.patch.object(
            api.requests, "request", return_value=FakeResponse(200, {"data": {"id": 7}})
        ):
            body = api.request("tok", "GET", "campaigns/1")
        self.assertEqual(body, {"data": {"id": 7}})


class AllPagesTests(unittest.TestCase):
    def test_requests_maximum_page_size_and_walks_pages(self) -> None:
        pages = [
            FakeResponse(200, {"data": [{"id": 1}], "meta": {"last_page": 2}}),
            FakeResponse(200, {"data": [{"id": 2}], "meta": {"last_page": 2}}),
        ]
        calls = []

        def fake(method, url, **kwargs):
            calls.append(kwargs.get("params"))
            return pages[len(calls) - 1]

        with mock.patch.object(api.requests, "request", side_effect=fake):
            records = api.all_pages("tok", "campaigns/1/characters")

        self.assertEqual([r["id"] for r in records], [1, 2])
        self.assertEqual(calls[0]["limit"], 100)
        self.assertEqual(calls[1]["page"], 2)


class ExactTests(unittest.TestCase):
    def test_exact_matches_ignoring_case_and_spaces(self) -> None:
        records = [{"name": "  Fogport "}]
        self.assertIsNotNone(api.exact(records, "fogport"))

    def test_exact_refuses_ambiguous_duplicates(self) -> None:
        records = [{"name": "Lott"}, {"name": "lott"}]
        with self.assertRaises(SystemExit):
            api.exact(records, "Lott", "character")

    def test_exact_one_requires_exactly_one_match(self) -> None:
        records = [{"name": "Lastlight"}]
        found = api.exact_one(records, ("Lastlight",), "location")
        self.assertEqual(found["name"], "Lastlight")
        with self.assertRaises(SystemExit):
            api.exact_one(records, ("Missing",), "location")


if __name__ == "__main__":
    unittest.main()
