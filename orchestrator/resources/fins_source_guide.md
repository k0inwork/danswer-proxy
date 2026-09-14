# FINS Source Guide — how to browse the fins3 sources

This document is the source map for virtual sources accessible through the
`fins3://` URL scheme. It explains what lives behind these URLs, how the
domain objects relate, and how to navigate. It is static: the fins3 sources
are read-only and do not change while you work.

## 1. Naming conventions

- `FILE_<path>.txt` — a real file from the workspace disk
  (e.g. `FILE_src_auth_py.txt` mirrors `src/auth.py`).
- `SOURCE_<url>.txt` — a document rendered from a virtual fins3 source
  (e.g. `SOURCE_fins3_db_eurobank_EBBG.Acceptance_ED_PURCHASE.txt`).
- `TOP_FOLDER_<dir>.txt` — the workspace tree map (this project's disk
  layout). It is the companion to this guide: the tree shows *what files
  exist on disk*, this guide shows *what fins3 sources exist and how to
  browse them*.

## 2. The fins3 URL grammar

Every fins3 document is identified by a uniform `(source, url)` pair:

| URL | Content |
|---|---|
| `fins3://db/<host>/<schema>/<event>` | Pseudocode of one booking event, resolved on the host's live database (inheritance applied) |
| `fins3://git/<ref>/<schema>/<event>` | The same event as defined in a VCS revision (`/` in refs is encoded `~`, e.g. `release~2`) |
| `fins3://runs/<run-id>.md` | A run log document |

Examples:

- `fins3://db/eurobank/EBBG.Acceptance_ED/PURCHASE`
- `fins3://git/release~2/EBBG.Acceptance_ED/PURCHASE`
- `fins3://runs/2026-09-14T10-12-33.md`

The `source` part of the URL selects the backend: `db` resolves events
through the schema inheritance chain on a bank host; `git` and `file`
kinds read one schema file (an event name that exists in several schemas
needs the `schema` qualifier).

## 3. Domain model — how the objects relate

- **Host = one bank.** Each host (e.g. `eurobank`) serves one institution.
  Start here: list hosts, then schemas on a host.
- **Booking schemas (`BOOK_SCHEMA`)** define the chart of accounts, party
  roles, booking events, condition indexes and condition value sets.
- **Inheritance chains.** A schema inherits from parent schemas (types range
  from "Roles, Accounts" only up to "Instructions, Conditions Idxs, Roles,
  Accounts"). Inherited events and elements are visible on the child schema;
  `std.*` schemas typically carry the financial logic, bank-specific schemas
  carry condition values.
- **Events** are the booking instruction documents (pseudocode): sequenced
  instructions that calculate amounts and post to accounts. Naming
  conventions: `CALL-*` = internal sub-events (always executed last),
  `R-*` = reversals, `A-*` = authorizations. The events visible on a schema
  include inherited ones; each event is *defined* in exactly one schema of
  the chain.
- **Products (`PROD_OFFERINGS`)** are templates in the Product Offering
  Facility. Each has a `prod_class` and an owner (`POF_OWNER` = the book
  owner/institution). A product maps to the booking schema used for its
  bookings (`prod_class` → schema).
- **Agreements** are instantiated from products: the product's booking schema
  and condition configuration are the blueprint for an agreement. Agreements
  may override condition values per agreement.
- **Conditions** are fees/rates/rules, identified by condition indexes
  (`cond_<idx>`, e.g. `cond_1001`), grouped by purpose, with value sets per
  schema (`effectiveDate`, currency, min/base/max amounts, rates) and
  optional per-agreement overrides. An index resolves through the
  inheritance chain: `relation` is `chain` (defined on the schema or an
  ancestor), `descendant` (defined on a schema inheriting it, named in
  `via`), or `other`.

### Relationship diagram

```
POF_OWNER (owner/bank)
  └─ PRODUCTS (prod_class)  ──map──▶  BOOK_SCHEMA
AGREEMENT ──instantiated from──▶ PRODUCT
BOOK_SCHEMA ──inherits──▶ parent BOOK_SCHEMA (chain)
BOOK_SCHEMA ──defines──▶ EVENTS (pseudocode)
EVENTS ──use──▶ CONDITION INDEXES ──grouped in──▶ CONDITION VALUE SETS
CONDITIONS ──overridden per──▶ AGREEMENT
```

## 4. Navigation recipes

- **Bank overview**: list hosts → list schemas on a host → list events of a
  schema → read an event's pseudocode.
- **From product to booking logic**: list owners → list products of an
  owner → resolve the product's schema → list that schema's events.
- **Find where an event is really defined**: resolve through the chain
  (`definedIn`/`via` semantics) — the pseudocode URL can be built for the
  defining schema.
- **Fees for a product**: resolve the schema's condition sets, then condition
  values per set.

## 5. Capabilities and limits

- fins3 sources are **read-only** — there are no write tools for them.
- `db` sources resolve inheritance automatically; `git` sources read a
  single revision and cannot enumerate schemas (only events of a known
  schema).
- Freshness is checked per read (etag): a changed source is re-attached
  under the same `SOURCE_*` name automatically. There is no background
  monitoring of fins3 sources.
- Content is attached to the project the first time you read a URL and
  stays available in context afterwards.
