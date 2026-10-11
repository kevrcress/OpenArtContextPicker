"""Tests for dcp_validate: one accepting and one rejecting case for every input rule."""

from __future__ import annotations

import copy
import json
import resource
import subprocess
import sys
import time
import unittest
from pathlib import Path

import dcp_validate
from dcp_validate import MAX_BYTES, InvalidRequest, validate_request

_ROOT = Path(__file__).resolve().parent.parent


def card(card_id: str, version: str, **overrides: object) -> dict:
    """Return a minimal valid card."""
    result = {
        "id": card_id,
        "version": version,
        "supersedes": [],
        "requires": [],
        "conflict_group": None,
        "tokens": 3,
        "covers": [],
    }
    result.update(overrides)
    return result


def base() -> dict:
    """Return a small valid request: v0 -> v1 -> v3 and v0 -> v2 (v1 and v2 are unrelated branches)."""
    return {
        "versions": [
            {"id": "v0", "parents": []},
            {"id": "v1", "parents": ["v0"]},
            {"id": "v2", "parents": ["v0"]},
            {"id": "v3", "parents": ["v1"]},
        ],
        "cards": [
            card("a", "v0", covers=["f1"]),
            card("b", "v1", supersedes=["a"], conflict_group="g", covers=["f2"], text="x"),
            card("c", "v2", requires=["a"]),
            card("d", "v3"),
        ],
        "features": {"f1": 5, "f2": 1},
        "head": "v3",
        "budget": 10,
        "mandatory": ["a"],
        "contradictions": [["a", "c"]],
    }


def enc(request: object) -> bytes:
    return json.dumps(request).encode("utf-8")


def big_request() -> dict:
    """Return a request at the public limits: 96 versions, 500 cards, 1,024 features, 10,000 pairs."""
    versions = [{"id": "v0", "parents": []}]
    versions += [{"id": f"v{i}", "parents": [f"v{i - 1}"]} for i in range(1, 96)]
    features = {f"feat{i}": 1 + i % 1000 for i in range(1024)}
    cards = []
    for i in range(500):
        cards.append(
            card(
                f"card{i}",
                f"v{i % 96}",
                supersedes=[f"card{i - 1}"] if i % 96 else [],
                requires=[f"card{(i + k) % 500}" for k in range(1, 9)],
                conflict_group=f"group{i % 40}",
                tokens=1 + i % 512,
                covers=[f"feat{(i * 7 + k) % 1024}" for k in range(64)],
                text="t" * 200,
            )
        )
    pairs = []
    for i in range(500):
        for k in range(1, 21):
            pairs.append([f"card{i}", f"card{(i + k) % 500}"])
    return {
        "versions": versions,
        "cards": cards,
        "features": features,
        "head": "v95",
        "budget": 8192,
        "mandatory": [f"card{i}" for i in range(0, 500, 50)],
        "contradictions": pairs,
    }


def maximum_request(filler: str) -> dict:
    """Return a valid request at every contract maximum at once, with each card text made only of the filler.

    Identifiers are 64 characters padded with colons. Each version lists the 8 versions before it as parents (as
    many as exist for the first 8), and each card supersedes 8 cards of an earlier version where any exist.
    """

    def name(kind: str, number: int) -> str:
        return f"{kind}{number}".rjust(64, ":")

    def version_of(position: int) -> int:
        return position * 96 // 500

    versions = [{"id": name("v", i), "parents": [name("v", j) for j in range(max(0, i - 8), i)]} for i in range(96)]
    cards = []
    for i in range(500):
        cards.append(
            card(
                name("c", i),
                name("v", version_of(i)),
                supersedes=[name("c", j) for j in range(8)] if version_of(i) > version_of(7) else [],
                requires=[name("c", (i + k) % 500) for k in range(1, 9)],
                conflict_group=name("g", i),
                tokens=512,
                covers=[name("f", (i + k) % 1024) for k in range(64)],
                text=filler * 2048,
            )
        )
    return {
        "versions": versions,
        "cards": cards,
        "features": {name("f", i): 1000 for i in range(1024)},
        "head": name("v", 95),
        "budget": 8192,
        "mandatory": [name("c", i) for i in range(500)],
        "contradictions": [[name("c", i), name("c", (i + k) % 500)] for i in range(500) for k in range(1, 21)],
    }


class ValidateTestCase(unittest.TestCase):
    def assert_valid(self, request: object) -> dict:
        raw = request if isinstance(request, bytes) else enc(request)
        return validate_request(raw)

    def assert_invalid(self, request: object) -> None:
        raw = request if isinstance(request, bytes) else enc(request)
        with self.assertRaises(InvalidRequest) as caught:
            validate_request(raw)
        reason = str(caught.exception)
        self.assertTrue(reason)
        self.assertTrue(reason.isascii())


class TestRawInput(ValidateTestCase):
    def test_validate_request_base_request_returns_parsed_dict(self):
        request = base()
        self.assertEqual(self.assert_valid(request), request)

    def test_validate_request_contract_empty_session_valid(self):
        self.assert_valid(
            b'{"versions": [{"id": "v0", "parents": []}], "cards": [], "features": {}, "head": "v0",'
            b' "budget": 0, "mandatory": [], "contradictions": []}'
        )

    def test_validate_request_exactly_max_bytes_valid(self):
        body = enc(base())
        raw = body + b" " * (MAX_BYTES - len(body))
        self.assertEqual(len(raw), 16 * 1024 * 1024)
        self.assert_valid(raw)

    def test_validate_request_one_byte_over_max_invalid(self):
        body = enc(base())
        self.assert_invalid(body + b" " * (MAX_BYTES - len(body) + 1))

    def test_validate_request_invalid_utf8_invalid(self):
        self.assert_invalid(enc(base()).replace(b'"x"', b'"\xff"'))
        self.assert_invalid(b"\xff\xfe")

    def test_validate_request_non_ascii_utf8_text_valid(self):
        request = base()
        request["cards"][1]["text"] = "café \U0001f3ac"
        self.assert_valid(json.dumps(request, ensure_ascii=False).encode("utf-8"))

    def test_validate_request_bom_invalid(self):
        self.assert_invalid(b"\xef\xbb\xbf" + enc(base()))

    def test_validate_request_empty_or_whitespace_only_invalid(self):
        for raw in (b"", b" ", b"\n", b" \t\r\n "):
            with self.subTest(raw=raw):
                self.assert_invalid(raw)

    def test_validate_request_top_level_not_object_invalid(self):
        for raw in (b"[]", enc([base()]), b"null", b"1", b'"x"', b"true"):
            with self.subTest(raw=raw[:10]):
                self.assert_invalid(raw)

    def test_validate_request_trailing_bytes_invalid(self):
        body = enc(base())
        for tail in (b"x", b"{}", b" {}", body, b",", b"\x00", b"\x0c", b"\xc2\xa0"):
            with self.subTest(tail=tail[:10]):
                self.assert_invalid(body + tail)

    def test_validate_request_surrounding_json_whitespace_valid(self):
        self.assert_valid(b" \t\r\n" + enc(base()) + b" \t\r\n")

    def test_validate_request_leading_non_json_whitespace_invalid(self):
        for lead in (b"\x0c", b"\x0b", b"\xc2\xa0", b"\xe2\x80\x83"):
            with self.subTest(lead=lead):
                self.assert_invalid(lead + enc(base()))

    def test_validate_request_malformed_json_invalid(self):
        for raw in (b"{", b'{"versions": [}', b"{'head': 1}", enc(base())[:-1], b'{"a": 01}'):
            with self.subTest(raw=raw[:16]):
                self.assert_invalid(raw)

    def test_validate_request_non_bytes_argument_invalid(self):
        with self.assertRaises(InvalidRequest):
            validate_request(None)  # type: ignore[arg-type]

    def test_validate_request_duplicate_top_level_key_invalid(self):
        raw = enc(base())
        self.assert_invalid(raw[:-1] + b', "budget": 10}')

    def test_validate_request_duplicate_key_inside_card_invalid(self):
        raw = enc(base())
        self.assertIn(b'"tokens": 3', raw)
        self.assert_invalid(raw.replace(b'"tokens": 3', b'"tokens": 3, "tokens": 3', 1))

    def test_validate_request_duplicate_key_inside_version_and_features_invalid(self):
        raw = enc(base())
        self.assert_invalid(raw.replace(b'"parents": []', b'"parents": [], "parents": []', 1))
        self.assert_invalid(raw.replace(b'"f1": 5', b'"f1": 5, "f1": 5', 1))

    def test_validate_request_deep_nesting_invalid(self):
        depth = 100_000
        for raw in (
            b"[" * depth + b"]" * depth,
            b'{"a":' * depth + b"1" + b"}" * depth,
            enc(base())[:-1] + b', "x": ' + b"[" * depth + b"]" * depth + b"}",
        ):
            with self.subTest(raw=raw[:8]):
                self.assert_invalid(raw)


class TestNumbers(ValidateTestCase):
    def budget_raw(self, literal: bytes) -> bytes:
        raw = enc(base())
        self.assertIn(b'"budget": 10', raw)
        return raw.replace(b'"budget": 10', b'"budget": ' + literal)

    def test_validate_request_integer_notation_valid(self):
        for literal in (b"0", b"10", b"8192", b"-0"):
            with self.subTest(literal=literal):
                self.assert_valid(self.budget_raw(literal))

    def test_validate_request_non_integer_notation_invalid(self):
        for literal in (b"1.0", b"1e2", b"1E2", b"10.5", b"1e-1", b"0.0", b"-1"):
            with self.subTest(literal=literal):
                self.assert_invalid(self.budget_raw(literal))

    def test_validate_request_boolean_as_integer_invalid(self):
        for literal in (b"true", b"false"):
            with self.subTest(literal=literal):
                self.assert_invalid(self.budget_raw(literal))
        request = base()
        request["cards"][0]["tokens"] = True
        self.assert_invalid(request)
        request = base()
        request["features"]["f1"] = True
        self.assert_invalid(request)

    def test_validate_request_non_finite_number_invalid(self):
        for literal in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(literal=literal):
                self.assert_invalid(self.budget_raw(literal))

    def test_validate_request_huge_integer_literal_invalid(self):
        self.assert_invalid(self.budget_raw(b"1" * 5000))
        self.assert_invalid(self.budget_raw(b"0" * 5000))

    def test_json_decoder_python_defaults_pinned(self):
        """Pin the 3.11 parser behaviour the validator relies on (plan step 1.1 assumption)."""
        seen: list[str] = []
        decoder = json.JSONDecoder(parse_float=seen.append, parse_constant=seen.append)
        decoder.decode('[1.0, 1e2, NaN, Infinity, -Infinity, 7]')
        self.assertEqual(seen, ["1.0", "1e2", "NaN", "Infinity", "-Infinity"])
        self.assertEqual(json.loads('{"a": 1, "a": 2}'), {"a": 2})
        with self.assertRaises(ValueError):
            json.loads("1" * 5000)
        with self.assertRaises(RecursionError):
            json.loads("[" * 100_000 + "]" * 100_000)


class TestKeys(ValidateTestCase):
    def test_validate_request_missing_top_level_key_invalid(self):
        for key in base():
            with self.subTest(key=key):
                request = base()
                del request[key]
                self.assert_invalid(request)

    def test_validate_request_unknown_top_level_key_invalid(self):
        request = base()
        request["extra"] = 1
        self.assert_invalid(request)

    def test_validate_request_version_keys_exact(self):
        for key in ("id", "parents"):
            with self.subTest(missing=key):
                request = base()
                del request["versions"][1][key]
                self.assert_invalid(request)
        request = base()
        request["versions"][0]["text"] = "x"
        self.assert_invalid(request)

    def test_validate_request_missing_card_key_invalid(self):
        for key in ("id", "version", "supersedes", "requires", "conflict_group", "tokens", "covers"):
            with self.subTest(key=key):
                request = base()
                del request["cards"][1][key]
                self.assert_invalid(request)

    def test_validate_request_unknown_card_key_invalid(self):
        request = base()
        request["cards"][0]["weight"] = 1
        self.assert_invalid(request)
        request = base()
        request["cards"][1]["weight"] = 1
        self.assert_invalid(request)

    def test_validate_request_card_text_optional(self):
        request = base()
        self.assertNotIn("text", request["cards"][0])
        self.assertIn("text", request["cards"][1])
        self.assert_valid(request)


class TestIdentifiers(ValidateTestCase):
    GOOD = ("Z", "A9", "x" * 64, "a.b_c:d-e", ".", "-", ":", "_", "0")
    BAD = ("", "x" * 65, "café", "a\n", "a b", "a/b", " a", "a\t", "а", "a\x00", "a,b")

    def with_id(self, kind: str, value: object) -> dict:
        request = base()
        if kind == "version":
            request["versions"].append({"id": value, "parents": []})
        elif kind == "card":
            request["cards"].append(card(value, "v0"))  # type: ignore[arg-type]
        elif kind == "feature":
            request["features"][value] = 1
        else:
            request["cards"][0]["conflict_group"] = value
        return request

    def test_validate_request_good_identifier_valid(self):
        for kind in ("version", "card", "feature", "group"):
            for value in self.GOOD:
                with self.subTest(kind=kind, value=value):
                    self.assert_valid(self.with_id(kind, value))

    def test_validate_request_bad_identifier_invalid(self):
        for kind in ("version", "card", "feature", "group"):
            for value in self.BAD:
                with self.subTest(kind=kind, value=value):
                    self.assert_invalid(self.with_id(kind, value))

    def test_validate_request_non_string_identifier_invalid(self):
        for kind in ("version", "card", "group"):
            for value in (1, True, ["a"], {"a": 1}):
                with self.subTest(kind=kind, value=value):
                    self.assert_invalid(self.with_id(kind, value))
        self.assert_invalid(self.with_id("version", None))
        self.assert_invalid(self.with_id("card", None))

    def test_validate_request_namespaces_are_separate(self):
        request = base()
        request["versions"].append({"id": "same", "parents": []})
        request["cards"].append(card("same", "same", conflict_group="same", covers=["same"]))
        request["features"]["same"] = 1
        self.assert_valid(request)

    def test_validate_request_reference_in_wrong_namespace_invalid(self):
        request = base()
        request["head"] = "a"
        self.assert_invalid(request)
        request = base()
        request["mandatory"] = ["v0"]
        self.assert_invalid(request)
        request = base()
        request["cards"][0]["covers"] = ["a"]
        self.assert_invalid(request)


class TestVersions(ValidateTestCase):
    def test_validate_request_version_count_bounds(self):
        request = base()
        request["versions"] = [{"id": f"n{i}", "parents": []} for i in range(96)]
        request["cards"] = []
        request["mandatory"] = []
        request["contradictions"] = []
        request["head"] = "n0"
        self.assert_valid(request)
        request["versions"].append({"id": "n96", "parents": []})
        self.assert_invalid(request)
        request["versions"] = []
        self.assert_invalid(request)

    def test_validate_request_single_version_valid(self):
        self.assert_valid({**base(), "versions": [{"id": "v0", "parents": []}], "cards": [], "head": "v0",
                           "mandatory": [], "contradictions": []})

    def test_validate_request_parent_count_bounds(self):
        request = base()
        request["versions"] += [{"id": f"p{i}", "parents": []} for i in range(9)]
        request["versions"].append({"id": "kid", "parents": [f"p{i}" for i in range(8)]})
        self.assert_valid(request)
        request["versions"][-1]["parents"].append("p8")
        self.assert_invalid(request)

    def test_validate_request_duplicate_version_id_invalid(self):
        request = base()
        request["versions"].append({"id": "v1", "parents": []})
        self.assert_invalid(request)

    def test_validate_request_duplicate_parent_invalid(self):
        request = base()
        request["versions"][3]["parents"] = ["v1", "v1"]
        self.assert_invalid(request)

    def test_validate_request_unknown_parent_invalid(self):
        request = base()
        request["versions"][3]["parents"] = ["nope"]
        self.assert_invalid(request)

    def test_validate_request_self_parent_invalid(self):
        request = base()
        request["versions"][0]["parents"] = ["v0"]
        self.assert_invalid(request)

    def test_validate_request_version_cycle_invalid(self):
        request = base()
        request["versions"][0]["parents"] = ["v3"]
        self.assert_invalid(request)
        request = base()
        request["versions"] += [{"id": "x", "parents": ["y"]}, {"id": "y", "parents": ["x"]}]
        self.assert_invalid(request)

    def test_validate_request_versions_not_topologically_sorted_valid(self):
        request = base()
        request["versions"].reverse()
        self.assert_valid(request)

    def test_validate_request_diamond_version_graph_valid(self):
        request = base()
        request["versions"].append({"id": "m", "parents": ["v3", "v2"]})
        request["cards"].append(card("e", "m", supersedes=["c", "b", "a"]))
        self.assert_valid(request)

    def test_validate_request_version_field_types_invalid(self):
        for versions in ({}, "v0", None, 1, [["v0"]], ["v0"], [None], [{"id": "v0", "parents": None}],
                         [{"id": "v0", "parents": "v0"}], [{"id": "v0", "parents": {}}],
                         [{"id": "v0", "parents": [None]}], [{"id": "v0", "parents": [1]}]):
            with self.subTest(versions=versions):
                request = base()
                request["versions"] = versions
                self.assert_invalid(request)

    def test_validate_request_head_must_be_existing_version(self):
        for head in ("v0", "v1", "v2", "v3"):
            with self.subTest(head=head):
                self.assert_valid({**base(), "head": head})
        for head in ("nope", "", None, 0, ["v0"], {"id": "v0"}):
            with self.subTest(head=head):
                self.assert_invalid({**base(), "head": head})


class TestCards(ValidateTestCase):
    def set_field(self, field: str, value: object, index: int = 3) -> dict:
        request = base()
        request["cards"][index][field] = value
        return request

    def test_validate_request_card_count_bounds(self):
        request = base()
        request["cards"] = [card(f"k{i}", "v0") for i in range(500)]
        request["mandatory"] = []
        request["contradictions"] = []
        self.assert_valid(request)
        request["cards"].append(card("k500", "v0"))
        self.assert_invalid(request)
        request["cards"] = []
        self.assert_valid(request)

    def test_validate_request_cards_container_types_invalid(self):
        for cards in ({}, None, "a", 1, ["a"], [None], [[]], [1]):
            with self.subTest(cards=cards):
                self.assert_invalid({**base(), "cards": cards, "mandatory": [], "contradictions": []})

    def test_validate_request_duplicate_card_id_invalid(self):
        request = base()
        request["cards"].append(card("a", "v2"))
        self.assert_invalid(request)

    def test_validate_request_card_version_must_exist(self):
        self.assert_valid(self.set_field("version", "v2"))
        for value in ("nope", "a", None, 1, ["v0"]):
            with self.subTest(value=value):
                self.assert_invalid(self.set_field("version", value))

    def test_validate_request_tokens_bounds(self):
        for value in (1, 2, 511, 512):
            with self.subTest(value=value):
                self.assert_valid(self.set_field("tokens", value))
        for value in (0, -1, 513, 10**9, "3", None, [3], False):
            with self.subTest(value=value):
                self.assert_invalid(self.set_field("tokens", value))

    def test_validate_request_conflict_group_null_or_identifier(self):
        for value in (None, "wardrobe", "a"):
            with self.subTest(value=value):
                self.assert_valid(self.set_field("conflict_group", value))
        for value in ("", 1, False, [], {}, ["g"]):
            with self.subTest(value=value):
                self.assert_invalid(self.set_field("conflict_group", value))

    def test_validate_request_covers_bounds(self):
        request = base()
        request["features"] = {f"f{i}": 1 for i in range(66)}
        request["cards"][3]["covers"] = [f"f{i}" for i in range(64)]
        self.assert_valid(request)
        request["cards"][3]["covers"].append("f64")
        self.assert_invalid(request)
        self.assert_valid(self.set_field("covers", []))

    def test_validate_request_covers_duplicate_unknown_or_wrong_type_invalid(self):
        for value in (["f1", "f1"], ["nope"], [1], [None], "f1", None, {"f1": 1}, [["f1"]]):
            with self.subTest(value=value):
                self.assert_invalid(self.set_field("covers", value))

    def test_validate_request_card_reference_list_bounds(self):
        for field in ("requires", "supersedes"):
            with self.subTest(field=field):
                request = base()
                request["cards"] += [card(f"o{i}", "v0") for i in range(9)]
                request["cards"][3][field] = [f"o{i}" for i in range(8)]
                self.assert_valid(request)
                request["cards"][3][field].append("o8")
                self.assert_invalid(request)

    def test_validate_request_card_reference_list_duplicate_unknown_or_wrong_type_invalid(self):
        for field in ("requires", "supersedes"):
            for value in (["a", "a"], ["nope"], ["v0"], [1], [None], "a", None, {}, [["a"]]):
                with self.subTest(field=field, value=value):
                    self.assert_invalid(self.set_field(field, value))

    def test_validate_request_forward_card_reference_valid(self):
        request = base()
        request["cards"].reverse()
        self.assert_valid(request)

    def test_validate_request_self_requirement_valid(self):
        self.assert_valid(self.set_field("requires", ["d"]))

    def test_validate_request_requirement_cycle_valid(self):
        request = base()
        request["cards"][0]["requires"] = ["b"]
        request["cards"][1]["requires"] = ["c"]
        request["cards"][2]["requires"] = ["a"]
        self.assert_valid(request)

    def test_validate_request_self_supersede_invalid(self):
        self.assert_invalid(self.set_field("supersedes", ["d"]))

    def test_validate_request_supersede_within_one_version_invalid(self):
        request = base()
        request["cards"].append(card("d2", "v3", supersedes=["d"]))
        self.assert_invalid(request)

    def test_validate_request_supersede_across_unrelated_branches_invalid(self):
        self.assert_invalid(self.set_field("supersedes", ["c"]))
        self.assert_invalid(self.set_field("supersedes", ["b"], index=2))

    def test_validate_request_supersede_descendant_invalid(self):
        self.assert_invalid(self.set_field("supersedes", ["d"], index=0))

    def test_validate_request_supersede_strict_ancestor_valid(self):
        self.assert_valid(self.set_field("supersedes", ["b"]))
        self.assert_valid(self.set_field("supersedes", ["a"]))
        self.assert_valid(self.set_field("supersedes", ["a", "b"]))

    def test_validate_request_supersede_ancestry_independent_of_head_and_array_order(self):
        request = self.set_field("supersedes", ["a"], index=2)
        request["head"] = "v1"
        request["versions"].reverse()
        request["cards"].reverse()
        self.assert_valid(request)

    def test_validate_request_text_length_bounds(self):
        for value in ("", "x" * 2048, "\U0001f3ac" * 2048, "é" * 2048):
            with self.subTest(length=len(value)):
                request = self.set_field("text", value)
                self.assert_valid(json.dumps(request, ensure_ascii=False).encode("utf-8"))
                self.assert_valid(request)
        for value in ("x" * 2049, "\U0001f3ac" * 2049):
            with self.subTest(length=len(value)):
                request = self.set_field("text", value)
                self.assert_invalid(json.dumps(request, ensure_ascii=False).encode("utf-8"))
                self.assert_invalid(request)

    def test_validate_request_text_wrong_type_invalid(self):
        for value in (None, 1, ["x"], {}, True):
            with self.subTest(value=value):
                self.assert_invalid(self.set_field("text", value))

    def raw_with_text(self, literal: bytes) -> bytes:
        """Return request bytes whose card text is the given raw JSON string body."""
        raw = enc(self.set_field("text", "TEXT_PLACEHOLDER"))
        self.assertEqual(raw.count(b'"TEXT_PLACEHOLDER"'), 1)
        return raw.replace(b'"TEXT_PLACEHOLDER"', b'"' + literal + b'"')

    def test_validate_request_text_lone_high_surrogate_escape_invalid(self):
        self.assert_invalid(self.raw_with_text(b"\\ud800"))
        self.assert_invalid(self.raw_with_text(b"a\\ud800b"))
        self.assert_invalid(self.raw_with_text(b"\\udbff"))

    def test_validate_request_text_lone_low_surrogate_escape_invalid(self):
        self.assert_invalid(self.raw_with_text(b"\\udc00"))
        self.assert_invalid(self.raw_with_text(b"a\\udfffb"))

    def test_validate_request_text_reversed_surrogate_pair_escape_invalid(self):
        self.assert_invalid(self.raw_with_text(b"\\udc00\\ud800"))

    def test_validate_request_text_surrogate_pair_escape_valid_and_counts_as_one_character(self):
        pair = b"\\ud83d\\ude00"
        parsed = self.assert_valid(self.raw_with_text(pair))
        self.assertEqual(parsed["cards"][3]["text"], "\U0001f600")
        self.assertEqual(len(parsed["cards"][3]["text"]), 1)
        self.assert_valid(self.raw_with_text(b"x" * 2047 + pair))
        self.assert_valid(self.raw_with_text(pair * 2048))
        self.assert_invalid(self.raw_with_text(b"x" * 2048 + pair))
        self.assert_invalid(self.raw_with_text(pair * 2049))

    def test_validate_request_text_raw_four_byte_utf8_emoji_valid(self):
        emoji = "\U0001f600".encode("utf-8")
        self.assertEqual(len(emoji), 4)
        parsed = self.assert_valid(self.raw_with_text(emoji))
        self.assertEqual(parsed["cards"][3]["text"], "\U0001f600")
        self.assert_valid(self.raw_with_text(emoji * 2048))
        self.assert_invalid(self.raw_with_text(emoji * 2049))


class TestFeaturesBudgetMandatory(ValidateTestCase):
    def test_validate_request_feature_count_bounds(self):
        request = base()
        request["features"] = {f"f{i}": 1 for i in range(1024)}
        self.assert_valid(request)
        request["features"]["f1024"] = 1
        self.assert_invalid(request)
        self.assert_valid({**base(), "features": {}, "cards": [], "mandatory": [], "contradictions": []})

    def test_validate_request_feature_weight_bounds(self):
        for weight in (1, 2, 999, 1000):
            with self.subTest(weight=weight):
                self.assert_valid({**base(), "features": {"f1": weight, "f2": 1}})
        for weight in (0, -1, 1001, "1", None, [1], False, {}):
            with self.subTest(weight=weight):
                self.assert_invalid({**base(), "features": {"f1": weight, "f2": 1}})

    def test_validate_request_features_container_types_invalid(self):
        for features in ([], None, "f1", 1, [["f1", 5]]):
            with self.subTest(features=features):
                self.assert_invalid({**base(), "features": features})

    def test_validate_request_budget_bounds(self):
        for budget in (0, 1, 8191, 8192):
            with self.subTest(budget=budget):
                self.assert_valid({**base(), "budget": budget})
        for budget in (-1, 8193, "10", None, [10], True, {}):
            with self.subTest(budget=budget):
                self.assert_invalid({**base(), "budget": budget})

    def test_validate_request_mandatory_distinct_existing_cards(self):
        for mandatory in ([], ["a"], ["d", "c", "b", "a"]):
            with self.subTest(mandatory=mandatory):
                self.assert_valid({**base(), "mandatory": mandatory})
        for mandatory in (["a", "a"], ["nope"], ["v0"], [1], [None], "a", None, {}, {"a": 1}, [["a"]]):
            with self.subTest(mandatory=mandatory):
                self.assert_invalid({**base(), "mandatory": mandatory})

    def test_validate_request_null_only_as_conflict_group(self):
        for key in base():
            with self.subTest(key=key):
                self.assert_invalid({**base(), key: None})
        for field in ("id", "version", "supersedes", "requires", "tokens", "covers", "text"):
            with self.subTest(field=field):
                request = base()
                request["cards"][1][field] = None
                self.assert_invalid(request)
        request = base()
        request["cards"][1]["conflict_group"] = None
        self.assert_valid(request)


class TestContradictions(ValidateTestCase):
    def with_pairs(self, pairs: object) -> dict:
        return {**base(), "contradictions": pairs}

    def test_validate_request_contradiction_pairs_valid(self):
        for pairs in ([], [["a", "b"]], [["a", "b"], ["b", "c"], ["c", "a"]], [["d", "a"], ["b", "d"]]):
            with self.subTest(pairs=pairs):
                self.assert_valid(self.with_pairs(pairs))

    def test_validate_request_contradiction_inside_group_and_requirement_closure_valid(self):
        request = base()
        request["cards"][0]["conflict_group"] = "g"
        request["contradictions"] = [["a", "b"], ["c", "a"]]
        self.assert_valid(request)

    def test_validate_request_contradiction_pair_shape_invalid(self):
        for pairs in ([["a"]], [["a", "b", "c"]], [[]], ["ab"], [{"a": "b"}], [None], [1], [["a", 1]],
                      [[None, "a"]], [[["a"], "b"]], {}, None, "a", [["a", "b"], "cd"]):
            with self.subTest(pairs=pairs):
                self.assert_invalid(self.with_pairs(pairs))

    def test_validate_request_contradiction_self_pair_invalid(self):
        self.assert_invalid(self.with_pairs([["a", "a"]]))

    def test_validate_request_contradiction_unknown_endpoint_invalid(self):
        for pairs in ([["a", "nope"]], [["nope", "a"]], [["v0", "a"]], [["f1", "a"]]):
            with self.subTest(pairs=pairs):
                self.assert_invalid(self.with_pairs(pairs))

    def test_validate_request_contradiction_duplicate_invalid(self):
        for pairs in ([["a", "b"], ["a", "b"]], [["a", "b"], ["b", "a"]], [["b", "a"], ["c", "d"], ["a", "b"]]):
            with self.subTest(pairs=pairs):
                self.assert_invalid(self.with_pairs(pairs))

    def test_validate_request_contradiction_count_bounds(self):
        request = big_request()
        self.assertEqual(len(request["contradictions"]), 10000)
        self.assert_valid(request)
        request["contradictions"].append(["card0", "card400"])
        self.assert_invalid(request)


class TestStructureCounts(ValidateTestCase):
    """The byte-count caps reject impossible input before parsing and never reject a valid request."""

    # Per text filler: the bytes its cap counts, the cap, and how far below the cap the maximum request may sit.
    # Distinct identifiers need a few non-colon characters, so the colon count cannot reach its bound exactly.
    COUNTED = {
        ",": ((b",",), "_MAX_COMMA_BYTES", 4096),
        "[": ((b"[", b"{"), "_MAX_OPENER_BYTES", 4096),
        "{": ((b"[", b"{"), "_MAX_OPENER_BYTES", 4096),
        ":": ((b":",), "_MAX_COLON_BYTES", 300_000),
        '"': ((b'"',), "_MAX_QUOTE_BYTES", 4096),
    }

    def test_validate_request_contract_maximum_request_valid_for_every_text_filler(self):
        for filler, (counted, cap_name, slack) in self.COUNTED.items():
            with self.subTest(filler=filler):
                request = maximum_request(filler)
                raw = enc(request)
                self.assertLessEqual(len(raw), MAX_BYTES)
                self.assertEqual(validate_request(raw), request)
                # The request sits just under its cap, so the cap is tight as well as safe.
                count = sum(raw.count(byte) for byte in counted)
                cap = getattr(dcp_validate, cap_name)
                self.assertLessEqual(count, cap)
                self.assertLess(cap - count, slack)

    def test_validate_request_contract_maximum_request_pretty_printed_valid(self):
        request = maximum_request(",")
        raw = json.dumps(request, indent=8).encode("utf-8")
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertEqual(validate_request(raw), request)
        padded = b" \n\t\r" * ((MAX_BYTES - len(raw)) // 4) + raw
        self.assertEqual(validate_request(padded), request)

    def test_validate_request_count_above_each_cap_invalid(self):
        for unit in (b",", b"[", b"{", b":", b'"'):
            with self.subTest(unit=unit):
                self.assert_invalid(b'{"cards":' + unit * 6_000_000 + b"}")
        with self.assertRaises(InvalidRequest) as caught:
            validate_request(b'{"cards":[' + b"[]," * 2_000_000 + b"[]]}")
        self.assertIn("more", str(caught.exception))

    def test_validate_request_16_mib_of_tiny_arrays_invalid_under_200_mib_peak_rss(self):
        child = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from dcp_validate import MAX_BYTES, InvalidRequest, validate_request\n"
            "head, tail = b'{\"cards\":[', b'[]]}'\n"
            "raw = head + b'[],' * ((MAX_BYTES - len(head) - len(tail)) // 3) + tail\n"
            "raw += b' ' * (MAX_BYTES - len(raw))\n"
            "assert len(raw) == MAX_BYTES\n"
            "try:\n"
            "    validate_request(raw)\n"
            "    print('valid')\n"
            "except InvalidRequest:\n"
            "    print('invalid')\n"
        )
        started = time.perf_counter()
        done = subprocess.run([sys.executable, "-c", child, str(_ROOT)], capture_output=True, text=True, timeout=30)
        elapsed = time.perf_counter() - started
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "invalid")
        # ru_maxrss is in bytes on macOS and in kilobytes on Linux.
        unit = 1 if sys.platform == "darwin" else 1024
        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * unit
        self.assertLess(peak, 200 * 1024 * 1024)
        self.assertLess(elapsed, 5.0)


class TestErrorsAndPerformance(ValidateTestCase):
    def test_validate_request_reason_never_echoes_request_text(self):
        marker = "ZZmarkerZZ"
        requests = []
        request = base()
        request["head"] = marker
        requests.append(request)
        request = base()
        request["cards"][0]["covers"] = [marker]
        requests.append(request)
        request = base()
        request[marker] = 1
        requests.append(request)
        request = base()
        request["contradictions"] = [["a", marker]]
        requests.append(request)
        for request in requests:
            with self.assertRaises(InvalidRequest) as caught:
                validate_request(enc(request))
            self.assertNotIn(marker, str(caught.exception))

    def test_validate_request_does_not_mutate_or_reorder(self):
        request = base()
        request["cards"].reverse()
        request["versions"].reverse()
        expected = copy.deepcopy(request)
        result = validate_request(enc(request))
        self.assertEqual(result, expected)
        self.assertEqual(list(result), list(expected))

    def best_seconds(self, raw: bytes) -> float:
        best = float("inf")
        for _ in range(5):
            started = time.perf_counter()
            validate_request(raw)
            best = min(best, time.perf_counter() - started)
        return best

    def test_validate_request_sample_session_valid_under_100_ms(self):
        candidates = [_ROOT / "director_session.json", _ROOT / "resources" / "director_session.json"]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            self.skipTest("director_session.json is not present in this tree")
        raw = path.read_bytes()
        validate_request(raw)
        self.assertLess(self.best_seconds(raw), 0.1)

    def test_validate_request_limit_sized_request_under_100_ms(self):
        raw = enc(big_request())
        self.assertGreater(len(raw), 400_000)
        validate_request(raw)
        self.assertLess(self.best_seconds(raw), 0.1)

    def test_module_exposes_binding_interface(self):
        self.assertEqual(dcp_validate.MAX_BYTES, 16 * 1024 * 1024)
        self.assertTrue(issubclass(InvalidRequest, Exception))


if __name__ == "__main__":
    unittest.main()
