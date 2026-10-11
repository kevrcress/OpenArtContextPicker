"""Strict validation of a director context request.

Implements the "Input" and "Pairwise contradictions" sections of the request contract. Validation is purely
structural: it never reasons about feasibility, and it completes before any solving starts.
"""

from __future__ import annotations

import json
import re

MAX_BYTES = 16 * 1024 * 1024

_MAX_VERSIONS = 96
_MAX_PARENTS = 8
_MAX_CARDS = 500
_MAX_CARD_REFS = 8
_MAX_TOKENS = 512
_MAX_COVERS = 64
_MAX_TEXT_CHARS = 2048
_MAX_FEATURES = 1024
_MAX_WEIGHT = 1000
_MAX_BUDGET = 8192
_MAX_CONTRADICTIONS = 10000
# Every integer the contract allows fits in four digits; longer literals are rejected before conversion.
_MAX_INT_LITERAL_CHARS = 32

_TOP_KEYS = frozenset(("versions", "cards", "features", "head", "budget", "mandatory", "contradictions"))
_VERSION_KEYS = frozenset(("id", "parents"))
_CARD_REQUIRED_KEYS = frozenset(("id", "version", "supersedes", "requires", "conflict_group", "tokens", "covers"))
_CARD_ALL_KEYS = _CARD_REQUIRED_KEYS | {"text"}

_IDENTIFIER = re.compile(r"[A-Za-z0-9._:\-]{1,64}")
_JSON_WHITESPACE = re.compile(r"[ \t\n\r]*")
_SURROGATE = re.compile("[\ud800-\udfff]")


class InvalidRequest(Exception):
    """The request violates the input contract. str(exc) is a nonempty ASCII reason."""


def _reject_float(_literal: str) -> float:
    raise InvalidRequest("numbers must use integer notation without a fraction or exponent")


def _reject_constant(_literal: str) -> float:
    raise InvalidRequest("non-finite numbers are not allowed")


def _parse_int(literal: str) -> int:
    if len(literal) > _MAX_INT_LITERAL_CHARS:
        raise InvalidRequest("integer literal is too long")
    return int(literal)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise InvalidRequest("duplicate object key")
    return obj


_DECODER = json.JSONDecoder(
    object_pairs_hook=_unique_object,
    parse_float=_reject_float,
    parse_int=_parse_int,
    parse_constant=_reject_constant,
)


def _is_identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER.fullmatch(value) is not None


def _check_keys(obj: dict, required: frozenset[str], allowed: frozenset[str], what: str) -> None:
    keys = obj.keys()
    if not required <= keys:
        raise InvalidRequest(f"{what} is missing a required key")
    if not keys <= allowed:
        raise InvalidRequest(f"{what} has an unknown key")


def _check_int(value: object, low: int, high: int, what: str) -> None:
    if type(value) is not int:
        raise InvalidRequest(f"{what} must be an integer")
    if value < low or value > high:
        raise InvalidRequest(f"{what} is out of range")


def _check_refs(value: object, limit: int | None, known: set[str], what: str) -> None:
    """Check an array of distinct references to existing IDs, with an optional length limit."""
    if type(value) is not list:
        raise InvalidRequest(f"{what} must be an array")
    if limit is not None and len(value) > limit:
        raise InvalidRequest(f"{what} has too many entries")
    if not value:
        return
    for item in value:
        if type(item) is not str:
            raise InvalidRequest(f"{what} entries must be strings")
    unique = set(value)
    if len(unique) != len(value):
        raise InvalidRequest(f"{what} has a duplicate entry")
    if not unique <= known:
        raise InvalidRequest(f"{what} has an unknown reference")


def _parse(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise InvalidRequest("input exceeds 16 MiB")
    text = raw.decode("utf-8", errors="strict")
    if text.startswith("﻿"):
        raise InvalidRequest("input must not start with a byte order mark")
    start = _JSON_WHITESPACE.match(text).end()
    if start == len(text):
        raise InvalidRequest("input is empty")
    if text[start] != "{":
        raise InvalidRequest("input must be one JSON object")
    request, end = _DECODER.raw_decode(text, start)
    if _JSON_WHITESPACE.match(text, end).end() != len(text):
        raise InvalidRequest("unexpected data after the JSON object")
    if type(request) is not dict:
        raise InvalidRequest("input must be one JSON object")
    return request


def _check_versions(versions: object) -> tuple[dict[str, int], list[int]]:
    """Validate the version graph.

    Returns:
        The index of every version ID, and per version index a bitmask of its strict ancestors.
    """
    if type(versions) is not list:
        raise InvalidRequest("versions must be an array")
    if not 1 <= len(versions) <= _MAX_VERSIONS:
        raise InvalidRequest("versions count is out of range")
    index: dict[str, int] = {}
    for version in versions:
        if type(version) is not dict:
            raise InvalidRequest("version must be an object")
        _check_keys(version, _VERSION_KEYS, _VERSION_KEYS, "version")
        version_id = version["id"]
        if not _is_identifier(version_id):
            raise InvalidRequest("version id is not a valid identifier")
        if version_id in index:
            raise InvalidRequest("duplicate version id")
        index[version_id] = len(index)
    known = set(index)
    count = len(versions)
    children: list[list[int]] = [[] for _ in range(count)]
    pending = [0] * count
    for position, version in enumerate(versions):
        parents = version["parents"]
        _check_refs(parents, _MAX_PARENTS, known, "version parents")
        pending[position] = len(parents)
        for parent in parents:
            children[index[parent]].append(position)
    ancestors = [0] * count
    ready = [position for position in range(count) if pending[position] == 0]
    done = 0
    while ready:
        position = ready.pop()
        done += 1
        inherited = ancestors[position] | (1 << position)
        for child in children[position]:
            ancestors[child] |= inherited
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    if done != count:
        raise InvalidRequest("version graph has a cycle")
    return index, ancestors


def _check_features(features: object) -> set[str]:
    if type(features) is not dict:
        raise InvalidRequest("features must be an object")
    if len(features) > _MAX_FEATURES:
        raise InvalidRequest("features count is out of range")
    for feature_id, weight in features.items():
        if _IDENTIFIER.fullmatch(feature_id) is None:
            raise InvalidRequest("feature id is not a valid identifier")
        if type(weight) is not int:
            raise InvalidRequest("feature weight must be an integer")
        if weight < 1 or weight > _MAX_WEIGHT:
            raise InvalidRequest("feature weight is out of range")
    return set(features)


def _check_cards(cards: object, version_index: dict[str, int], ancestors: list[int], feature_ids: set[str]) -> set[str]:
    if type(cards) is not list:
        raise InvalidRequest("cards must be an array")
    if len(cards) > _MAX_CARDS:
        raise InvalidRequest("cards count is out of range")
    card_version: dict[str, int] = {}
    for card in cards:
        if type(card) is not dict:
            raise InvalidRequest("card must be an object")
        _check_keys(card, _CARD_REQUIRED_KEYS, _CARD_ALL_KEYS, "card")
        card_id = card["id"]
        if not _is_identifier(card_id):
            raise InvalidRequest("card id is not a valid identifier")
        if card_id in card_version:
            raise InvalidRequest("duplicate card id")
        version = card["version"]
        if type(version) is not str or version not in version_index:
            raise InvalidRequest("card version is not an existing version id")
        card_version[card_id] = version_index[version]
        group = card["conflict_group"]
        if group is not None and not _is_identifier(group):
            raise InvalidRequest("card conflict_group must be null or an identifier")
        _check_int(card["tokens"], 1, _MAX_TOKENS, "card tokens")
        _check_refs(card["covers"], _MAX_COVERS, feature_ids, "card covers")
        if "text" in card:
            text = card["text"]
            if type(text) is not str:
                raise InvalidRequest("card text must be a string")
            if len(text) > _MAX_TEXT_CHARS:
                raise InvalidRequest("card text is too long")
            if _SURROGATE.search(text):
                raise InvalidRequest("card text contains a lone surrogate")
    card_ids = set(card_version)
    for card in cards:
        _check_refs(card["requires"], _MAX_CARD_REFS, card_ids, "card requires")
        supersedes = card["supersedes"]
        _check_refs(supersedes, _MAX_CARD_REFS, card_ids, "card supersedes")
        if supersedes:
            card_id = card["id"]
            own_ancestors = ancestors[card_version[card_id]]
            for older in supersedes:
                if older == card_id:
                    raise InvalidRequest("card supersedes itself")
                if not (own_ancestors >> card_version[older]) & 1:
                    raise InvalidRequest("card supersedes a card whose version is not a strict ancestor")
    return card_ids


def _check_contradictions(contradictions: object, card_ids: set[str]) -> None:
    if type(contradictions) is not list:
        raise InvalidRequest("contradictions must be an array")
    if len(contradictions) > _MAX_CONTRADICTIONS:
        raise InvalidRequest("contradictions count is out of range")
    seen: set[tuple[str, str]] = set()
    for pair in contradictions:
        if type(pair) is not list or len(pair) != 2:
            raise InvalidRequest("contradiction must be an array of two card ids")
        first, second = pair
        if type(first) is not str or type(second) is not str:
            raise InvalidRequest("contradiction endpoints must be strings")
        if first not in card_ids or second not in card_ids:
            raise InvalidRequest("contradiction has an unknown card id")
        if first == second:
            raise InvalidRequest("contradiction pairs a card with itself")
        seen.add((first, second) if first < second else (second, first))
    if len(seen) != len(contradictions):
        raise InvalidRequest("duplicate contradiction pair")


def _validate(raw: bytes) -> dict:
    request = _parse(raw)
    _check_keys(request, _TOP_KEYS, _TOP_KEYS, "request")
    version_index, ancestors = _check_versions(request["versions"])
    feature_ids = _check_features(request["features"])
    card_ids = _check_cards(request["cards"], version_index, ancestors, feature_ids)
    head = request["head"]
    if type(head) is not str or head not in version_index:
        raise InvalidRequest("head is not an existing version id")
    _check_int(request["budget"], 0, _MAX_BUDGET, "budget")
    _check_refs(request["mandatory"], None, card_ids, "mandatory")
    _check_contradictions(request["contradictions"], card_ids)
    return request


def validate_request(raw: bytes) -> dict:
    """Parse and validate one request.

    Args:
        raw: The raw request bytes exactly as read from stdin.

    Returns:
        The request as plain dict/list/str/int/None values exactly as parsed.

    Raises:
        InvalidRequest: The request violates the input contract. No other exception escapes.
    """
    try:
        return _validate(raw)
    except InvalidRequest:
        raise
    except UnicodeDecodeError:
        raise InvalidRequest("input is not valid UTF-8") from None
    except RecursionError:
        raise InvalidRequest("input is nested too deeply") from None
    except json.JSONDecodeError:
        raise InvalidRequest("input is not valid JSON") from None
    except MemoryError:
        raise InvalidRequest("input is too large to process") from None
    except Exception:  # noqa: BLE001 - the interface promises that only InvalidRequest escapes
        raise InvalidRequest("request could not be validated") from None
