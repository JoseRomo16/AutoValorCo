# ADR 0005 - Where the listings come from after the verification wall

- Status: **proposed** — the owner decides between A, B and C below
- Date: 2026-11-01

## Context

The weekly capture of **2026-10-26 collected nothing**. Every request to
`tucarro.com.co` answered `302` towards
`mercadolibre.com.co/gz/account-verification`: the site asked for account
verification instead of serving search pages. Zero cars, zero motorcycles, no bronze
written, and the run went red on "Upload capture" (`if-no-files-found: error`) rather
than on the thing that actually happened. **The last good capture is 2026-10-19**, so
the lake holds four captures, 2026-09-30 to 2026-10-19.

The code side of that is fixed in this same change: `VerificationWallError` is detected
on the redirect chain, the capture stops at the first wall without retrying, whatever was
already swept is written, and the run exits `3` so the workflow reports "bloqueado"
instead of a failure. That makes a blocked week **cost one request and leave a clear
summary**. It does not answer the question this ADR is for: where the listings come from
from now on.

What is **not** on the table, and this is a project rule rather than an unexplored option:
no proxies, no rotating user-agents or IPs, no headless browser to clear the check, no
session cookies, no captcha solving. The wall is the site saying no, and the answer is to
stop asking, not to ask differently.

### The wall is tied to the IP, not to the project

Already diagnosed and recorded in `docs/STATUS.md`: the same URLs that answer `302` to the
verification screen from GitHub Actions answer **`200` from a residential IP** (or a `301`
to the newer `/bogota-dc` shape, which the client already follows), and parse 48 cards per
page. So this is a block on datacenter address ranges, not a URL template that went stale
and not a ban on this project. That single fact is what makes option C below exist, and it
is also why a residential proxy — which would be the obvious technical fix — is doubly
excluded: it is paid, and it is exactly the evasion the rule above forbids.

### What depends on the answer

- **The monthly used-price index** (F3's last open deliverable) needs about six months of
  weekly history and is projected for ~2027-03-29. It is a time series: a gap is a gap.
- **The temporal split** is deferred until there are 3–4 more captures (`docs/STATUS.md`).
  With no new captures it stays deferred indefinitely.
- **The Block 4 retrain** (drop `city`, fix the one-letter BMW/Yamaha models) does not
  depend on this: it deliberately reuses the four existing captures.
- **Department coverage.** The capture sweeps six locations, and gold holds ten
  departments, some with almost nothing (Cauca 1 listing, Meta 2). Widening that is only
  worth planning once the source is settled.

## The two candidates

### A. The official Mercado Libre API

**Measured, not assumed.** Three unauthenticated requests from this machine on
2026-11-01, user-agent `AutoValorCO-ADR-check/1.0`:

| Request | Response |
| --- | --- |
| `GET api.mercadolibre.com/sites/MCO/search?category=MCO1744&limit=1` | `403` · `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}` |
| `GET api.mercadolibre.com/sites/MCO/search?q=toyota%20corolla&limit=1` | `403` · same body |
| `GET api.mercadolibre.com/sites/MCO/categories` | `403` · `{"status":403,"blocked_by":"PolicyAgent","message":"At least one policy returned UNAUTHORIZED.","code":"PA_UNAUTHORIZED_RESULT_FROM_POLICIES"}` |

So **the public search is not open**. The third response is the informative one: it is not
a bot filter or a rate limit but a policy agent refusing an unauthorized caller, which
means a token is required rather than merely recommended.

The next question — does a token actually help? — could not be answered from here, and
that matters more than the 403 above. Multiple independent reports describe
`/sites/{site}/search` returning `403` **with a valid token and a registered
application**, and third-party scraping vendors describe the anonymous endpoint as
retired rather than throttled. At least one public MCP server deprecated its
`search_products` tool citing Mercado Libre's restrictions. None of that is a measurement
this project made, and the only way to turn it into one is to register an application —
which is the decision below, not something to do quietly.

What registering would cost, as far as the documentation goes:

- **Creating the application is free and takes no card.** It needs a Mercado Libre
  account, and in several countries the account holder's data must be complete and
  validated before the DevCenter will create an app at all. Colombia's exact requirement
  is unverified; the account that would own it is a personal one.
- It ties the project's data collection to **a personal Mercado Libre account**, with a
  client id and secret living in this public repository's secrets. That is a different
  risk profile from today's anonymous, polite, read-only scrape: an application can be
  blocked, and a blocked application is attached to a person.
- Terms of use for **redistributing** listing data were not established. The project
  publishes aggregates and a public capture history on the `data` branch (ADR 0004), so
  this is not a detail — it would need reading before a single row is published.
- Whether the vehicle search for MCO returns everything the model needs — price, year,
  mileage, department **and city**, brand, model, engine displacement — could not be
  checked, because every probe 403s. Note that engine displacement is today parsed out of
  the listing title for cars, so an API that returns it as an attribute would be a real
  improvement; an API that omits it would be a regression.
- It **would** plausibly fix department coverage, since a query is not tied to the six
  location slugs the scraper sweeps. "Plausibly" is as far as the evidence goes.

Fitting it into bronze is the cheap part and not a reason to pick it: an API row carries
its own id and a permalink, so `captured_at` and `source_url` keep their meaning, bronze
stays immutable and append-only, and no seller name, phone or e-mail is read or stored
(Ley 1581). A new parser in `ingest/` and a schema mapping is the whole code cost.

### B. Pause the capture

Leave the detection in place, keep the workflows enabled, and let the weekly run cost one
request and report "bloqueado" until the wall comes down or the question is reopened. The
model, the API and the site keep working on the four captures already in the lake —
nothing in production depends on a fresh capture.

What it costs, honestly:

- **The price index slips.** Four captures spanning three weeks is not six months of
  history. The 2027-03-29 projection stops being a date and becomes "six months after
  captures resume". This is the real price of B.
- The temporal split stays deferred.
- The published numbers age. Metodología currently claims the site reads TuCarro
  **once a week**, which stops being true the moment the capture is paused — that text is
  conditioned on this decision and is corrected in Block 8.
- It is reversible at any time and costs nothing to hold, which is the argument for it.
  A weekly blocked run is also a free probe: the first green week tells us the wall is
  gone.

### C. Run the weekly capture from the development machine

The scraper already works from a residential IP — that is how the F1 pilot was collected,
before the capture moved to Actions. `make scrape` followed by `make push-history`
publishes to the `data` branch through exactly the same code path the workflow uses, so
bronze, immutability and provenance are unchanged.

The cost is wall-clock and discipline, and it is smaller than it looks: a full sweep is
six locations × 10 pages × 2 verticals ≈ **120 requests**, at the configured polite pause
of 2–6 s, so roughly **10–15 minutes** once a week on a machine that is already on. It
keeps the history alive, which means the price index keeps its date and the temporal split
stops being deferred.

**The thing to decide is not the cost, it is whether this counts as evasion.** The honest
case that it does not: nothing about the request changes — same code, same identifiable
user-agent, same robots.txt compliance, same pauses, no proxy, no cookies, no browser, no
captcha. It is the scraper run from the machine it was written on, and that machine was
never asked to verify anything. The honest case that it does: the site blocked datacenter
ranges, and running from an address it did not block is, in effect, routing around that
block — the intent test, not the mechanism test.

That judgment is the owner's, and it is the only part of this ADR that is not a
measurement. It also has an ongoing cost B does not: a weekly manual chore that, if
skipped, silently reintroduces the gap this option exists to prevent.

## Decision

**Pending.** Recommendation: **C if the owner judges it is not evasion, otherwise B.**
A stays open either way, and is not recommended now.

On **A**: the point is not that it is bad, it is that it is **unverified**. The one claim
it rests on — that a token restores the search — is exactly the claim the evidence puts in
doubt, and the only way to test it is to register an application against a personal
account. Spending that on a maybe, while nothing in production is broken, is the wrong
order.

Between **C** and **B**: C is the only option that keeps the price index on its date at
zero cost, and that deliverable is the last thing open in F3 — B's real price is losing it
indefinitely. So C wins on consequences, and the only thing that can rule it out is the
intent question above, which is why this is not a recommendation the implementer gets to
make alone. If the answer is B, that is a legitimate outcome and not a failure: the index
slips, everything else keeps working, and a weekly blocked run tells us the moment the
wall lifts.

**What would change the recommendation on A.** A single measurement, not a migration:
register the free application, obtain a token, call `/sites/MCO/search` for category
MCO1744, and record the status and body here. 200 with the fields the model needs makes A
the better option — more departments, no HTML parsing, no wall — and this ADR is revised.
A 403 like the anonymous call closes A for good.

Two things stay true under every option: the one-request-and-stop behaviour is correct
regardless of the source, and nothing here authorises getting around the verification
screen.

## Consequences

Under **B**:

- `capture.yml` and `enrich.yml` stay **enabled**. That is the point of the detection: the
  reason they were disabled by hand before 2026-11-02 was that a blocked run meant 72
  pointless requests and a red run with a misleading cause. Both are now one request and a
  summary.
- `docs/STATUS.md` records 2026-10-26 as blocked and every subsequent week as blocked or
  skipped, so the gap is documented rather than inferred from missing files.
- Metodología stops promising a weekly read and states the date of the data instead
  (Block 8).
- The Block 4 retrain proceeds on the four existing captures, as already planned.
- Re-measuring the band after a future capture is on the deferred list in
  `docs/STATUS.md`, not forgotten.

Under **C**, additionally:

- `capture.yml` keeps its schedule as the probe — one request a week that reports whether
  the wall is still up — and the real capture is `make scrape` plus `make push-history` on
  the development machine. The two do not collide: bronze filenames carry their UTC
  instant and `history push` never overwrites.
- The weekly chore belongs in `docs/STATUS.md` with the date of the last manual capture,
  because a chore that is only in someone's head is a gap waiting to happen.
- Nothing in the code changes. That is the argument for C and also its weakness: there is
  no mechanism making it happen.

Under **A**, additionally:

- A client id and secret become repository secrets, with a documented rotation step, and
  the capture stops being anonymous.
- Terms of use are read and summarised here **before** the first API-sourced row is
  published to the `data` branch.
- Bronze gains a second provenance. `source_url` keeps working, but rows from the API and
  rows from HTML are not interchangeable for anything time-series, and the schema needs a
  column saying which is which — otherwise a change of source looks like a change in the
  market.
- The scraper is not deleted. It is the fallback, and it is also the only thing that can
  confirm the wall ever came down.
