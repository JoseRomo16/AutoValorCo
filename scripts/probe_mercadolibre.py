"""One authenticated probe of the Mercado Libre search API, for ADR 0005.

Option A of `docs/adr/0005-capture-source-after-verification-wall.md` rests on a single
claim nobody has tested: that an access token restores `/sites/MCO/search`. Unauthenticated
it answers `403`, and there are independent reports of the same `403` *with* a valid token
and a registered application. This script turns that into a measurement.

It makes **one** search request. Not a capture, not a sample, and nothing is written to
the lake: the question is whether the endpoint answers at all and whether the fields the
model needs come back with it.

Usage:
    The token never goes in the repository, in a commit, or on the command line — where it
    would land in the shell history. It is read from the environment:

        $env:MERCADOLIBRE_ACCESS_TOKEN = "<token>"   # PowerShell
        uv run python scripts/probe_mercadolibre.py

    Add `--json` to write the full first result to a file for reading at leisure:

        uv run python scripts/probe_mercadolibre.py --json probe.json

    `probe.json` is not committed: it is a raw third-party listing and may carry seller
    fields the project is not allowed to store (Ley 1581). Read it and delete it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

from autovalor.ingest.polite import tls_verification

TOKEN_VAR = "MERCADOLIBRE_ACCESS_TOKEN"

SEARCH_URL = "https://api.mercadolibre.com/sites/MCO/search"
"""Colombia's site. MCO1744 is "Carros, Camionetas y 4x4" under MCO1743, Vehículos."""

WHOAMI_URL = "https://api.mercadolibre.com/users/me"
"""Checked first, and the reason is a measured ambiguity.

A deliberately invalid token makes the search answer `403 {"message": "forbidden"}` — byte
for byte what it answers with no token at all. So a 403 on the search alone cannot tell
"the endpoint is closed to everyone" from "this token is wrong", and those lead to
opposite conclusions in ADR 0005. One request against an endpoint that is known to need
authentication settles it: if the token is accepted here and refused there, the endpoint
is closed, and that is a finding rather than a configuration mistake.
"""

VEHICLE_CATEGORY = "MCO1744"

USER_AGENT = "AutoValorCO-ADR-probe/1.0 (+https://github.com/JoseRomo16/AutoValorCo)"

# What the model actually needs, and where a Mercado Libre item is documented to carry it.
# Attribute ids are checked inside `attributes`, top-level keys directly on the item.
WANTED_TOP_LEVEL = {
    "price": "precio",
    "currency_id": "moneda",
    "permalink": "source_url",
    "id": "listing_id",
}
WANTED_ATTRIBUTES = {
    "VEHICLE_YEAR": "año",
    "KILOMETERS": "kilometraje",
    "BRAND": "marca",
    "MODEL": "modelo",
    "ENGINE_DISPLACEMENT": "cilindrada",
}
WANTED_LOCATION = {
    "state": "departamento",
    "city": "ciudad",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the first result verbatim here (not for committing; see the module docstring)",
    )
    parser.add_argument(
        "--category",
        default=VEHICLE_CATEGORY,
        help=f"category to search (default {VEHICLE_CATEGORY}, cars in Colombia)",
    )
    return parser.parse_args(argv)


def describe_coverage(item: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return ``(field, where it was looked for, value or MISSING)`` for every needed field.

    The point of the probe is not that the endpoint answers but that it answers *usefully*.
    An API that omits engine displacement would be a regression against today's title
    parsing, so every field is reported rather than summarised into a yes or no.
    """
    found: list[tuple[str, str, str]] = []

    for key, label in WANTED_TOP_LEVEL.items():
        value = item.get(key)
        found.append((label, key, "MISSING" if value is None else str(value)[:70]))

    location = item.get("address") or item.get("seller_address") or {}
    for key, label in WANTED_LOCATION.items():
        nested = location.get(key)
        if isinstance(nested, dict):
            nested = nested.get("name")
        shown = nested if nested else location.get(f"{key}_name")
        found.append((label, f"address.{key}", "MISSING" if not shown else str(shown)[:70]))

    attributes = {
        attribute.get("id"): attribute.get("value_name")
        for attribute in item.get("attributes", [])
        if isinstance(attribute, dict)
    }
    for key, label in WANTED_ATTRIBUTES.items():
        value = attributes.get(key)
        found.append((label, f"attributes.{key}", "MISSING" if value is None else str(value)[:70]))

    return found


def check_token(client: httpx.Client, headers: dict[str, str]) -> bool:
    """Return whether the token is accepted at all, printing what was seen."""
    try:
        response = client.get(WHOAMI_URL, headers=headers)
    except httpx.HTTPError as error:
        print(f"could not check the token: {type(error).__name__}: {error}")
        return False

    if response.status_code == httpx.codes.OK:
        print(f"token accepted by {WHOAMI_URL} (HTTP 200) — it is a working token.")
        return True

    print(f"token REFUSED by {WHOAMI_URL}: HTTP {response.status_code} {response.text[:200]}")
    print("Fix the token before reading anything into the search result: an invalid token")
    print("produces the same 403 the search gives anonymously, so the probe would be")
    print("inconclusive rather than negative.")
    return False


def report(response: httpx.Response, *, json_path: Path | None) -> int:
    """Print what the ADR needs and return the process exit code."""
    print(f"HTTP {response.status_code} {response.reason_phrase}")

    try:
        payload = response.json()
    except ValueError:
        print(f"body (not JSON): {response.text[:500]}")
        return 1

    if response.status_code != httpx.codes.OK:
        print(f"body: {json.dumps(payload, ensure_ascii=False)[:800]}")
        print()
        print("=> Option A is CLOSED: a working token does not restore the search endpoint.")
        print("   Record this status and body in ADR 0005 and keep the capture paused.")
        return 1

    results = payload.get("results") or []
    total = payload.get("paging", {}).get("total")
    print(f"results in this page: {len(results)}   total matching: {total}")
    if not results:
        print()
        print("=> Answered 200 but returned nothing. Not a usable source as queried;")
        print("   try another category before concluding anything.")
        return 1

    print()
    print(f"{'field':<14} {'read from':<32} value")
    print("-" * 78)
    missing: list[str] = []
    for label, where, value in describe_coverage(results[0]):
        print(f"{label:<14} {where:<32} {value}")
        if value == "MISSING":
            missing.append(label)

    print()
    if missing:
        print(f"=> 200, but these are MISSING: {', '.join(missing)}.")
        print("   Weigh each one in ADR 0005 before adopting A; a missing cilindrada is a")
        print("   regression against the current title parsing, not a detail.")
    else:
        print("=> 200 with every field the model needs. Option A is viable: record this in")
        print("   ADR 0005 and open an implementation block for it.")

    if json_path is not None:
        json_path.write_text(json.dumps(results[0], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFirst result written to {json_path} — read it and delete it (Ley 1581).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the probe and return a process exit code."""
    args = parse_args(argv)

    token = os.environ.get(TOKEN_VAR, "").strip()
    if not token:
        print(f"{TOKEN_VAR} is not set. See the usage note in this file's docstring.")
        print("The token is read from the environment on purpose: never commit it, and")
        print("never pass it as an argument, where it would land in the shell history.")
        return 2

    params = {"category": args.category, "limit": "1"}
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}

    try:
        # tls_verification honours AUTOVALOR_USE_SYSTEM_CERTS, which this machine needs:
        # the local network intercepts TLS and plain certifi verification fails.
        with httpx.Client(verify=tls_verification(), timeout=30.0, follow_redirects=True) as client:
            if not check_token(client, headers):
                return 2
            print()
            print(f"GET {SEARCH_URL}?category={args.category}&limit=1  (with Bearer token)")
            print()
            response = client.get(SEARCH_URL, params=params, headers=headers)
    except httpx.HTTPError as error:
        print(f"the request itself failed: {type(error).__name__}: {error}")
        print("A transport failure is not an answer about the endpoint. Fix this first.")
        return 1

    return report(response, json_path=args.json)


if __name__ == "__main__":
    sys.exit(main())
