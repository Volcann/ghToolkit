import json
import unittest
from urllib.parse import parse_qs, urlsplit

from ghtoolkit import GhResponseError
from ghtoolkit.api import GhAPI, Repository

from tests.helpers import FakeRunner


class APITests(unittest.TestCase):
    def test_repository_is_explicitly_host_scoped(self):
        self.assertEqual(
            Repository.parse("acme/widget").cli_name, "github.com/acme/widget"
        )
        self.assertEqual(
            Repository.parse("GH.EXAMPLE.test/acme/widget").host, "gh.example.test"
        )

    def test_invalid_repository_values(self):
        for value in (
            "acme",
            "https://github.com/acme/widget",
            "acme/../widget",
            "acme/",
            "-/a/b",
            "a/b/c/d",
            "a/b\x00",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Repository.parse(value)

    def test_paginated_array_pages_are_flattened(self):
        runner = FakeRunner(json_results=[[[{"id": 1}], [{"id": 2}]]])
        result = GhAPI(Repository.parse("acme/widget"), runner).list("pulls/1/reviews")
        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        args = runner.calls[0][1]
        self.assertIn("--paginate", args)
        self.assertIn("--slurp", args)
        self.assertEqual(args[args.index("--method") + 1], "GET")

    def test_query_values_are_url_encoded(self):
        runner = FakeRunner(json_results=[[[]]])
        GhAPI(Repository.parse("acme/widget"), runner).list(
            "commits", {"author": "a+b@example.test", "sha": "feature/a & b"}
        )
        query = parse_qs(urlsplit(runner.calls[0][1][1]).query)
        self.assertEqual(query["author"], ["a+b@example.test"])
        self.assertEqual(query["sha"], ["feature/a & b"])
        self.assertEqual(query["per_page"], ["100"])

    def test_wrong_page_shape_is_an_error(self):
        for response in ({}, [{"id": 1}], [[None]]):
            with self.subTest(response=response), self.assertRaises(GhResponseError):
                GhAPI(
                    Repository.parse("a/b"), FakeRunner(json_results=[response])
                ).list("pulls")

    def test_post_payload_uses_stdin_and_explicit_post(self):
        runner = FakeRunner(json_results=[{"id": 9}])
        api = GhAPI(Repository.parse("a/b"), runner)
        payload = {"body": "Unicode café\n\n```suggestion\nx()\n```"}
        self.assertEqual(api.post("pulls/1/reviews", payload), {"id": 9})
        _, args, kwargs = runner.calls[0]
        self.assertEqual(args[args.index("--method") + 1], "POST")
        self.assertIn("--input", args)
        self.assertNotIn(payload["body"], args)
        self.assertEqual(json.loads(kwargs["input_text"]), payload)

    def test_graphql_errors_are_not_partial_success(self):
        runner = FakeRunner(
            json_results=[[{"errors": [{"message": "denied"}], "data": {}}]]
        )
        with self.assertRaises(GhResponseError):
            GhAPI(Repository.parse("a/b"), runner).graphql_pages("query {}", {})

    def test_object_endpoint_rejects_array(self):
        with self.assertRaises(GhResponseError):
            GhAPI(Repository.parse("a/b"), FakeRunner(json_results=[[]])).get_object(
                "pulls/1"
            )
