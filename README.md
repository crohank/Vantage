# Vantage

Finds what changed in a company's SEC filings, and whether anyone noticed.

Every claim resolves to a verbatim span in a specific document. A finding that
cannot quote its source is dropped before it reaches you, at runtime and in CI.

```
NVDA, FY2025 to FY2026, 200 findings in 6.2s, 77 rated high materiality.

  [ADDED] Risk Factors, 0.99
  "Governments and regulators are also considering, and in certain cases,
   have imposed restrictions on the hardware, software, and systems used to
   develop frontier foundation models and generative AI. For example, the
   EU AI Act became effective on August 1, 2024..."
  0001045810-26-000021, chars 68,779 to 70,299 of 114,443
```

## Why diffs rather than opinions

The obvious version of this product asks a model what it thinks of a stock.
That output has no ground truth, so the best available evaluation is a model
grading another model on a 1 to 5 scale, and the honest answer to "how do you
know it is right?" is that you do not.

Diffing inverts it. Both documents are on disk, so whether the system found
the paragraph that was added is decidable by string alignment. That single
property is what makes the rest of the system measurable.

The design rule that follows:

> **Location is deterministic. Explanation is generative.**

A mechanical aligner finds the changed paragraph. The model only classifies
and explains a change that has already been located. The model is never asked
to find anything, so it is never in a position to invent one.

## What it does

| Engine | Question | Ground truth |
|---|---|---|
| **Diff** | What language changed between the two most recent annual filings? | Yes, both documents are held |
| **Novelty** | Has this filer ever used this phrase before? | Yes, EDGAR full-text search back to 2001 |
| **Peer** | Did the rest of the sector add the same language this quarter? | Yes, same |
| **Attention** | Is anyone discussing it? | No, scored and labelled as discussion volume |

The interesting quadrant is a material change nobody is talking about.

## Measured

Numbers below are produced by `uv run python -m vantage.eval.run_diff_eval`
and the test suite, not written by hand.

**Diff engine**, against a golden set built by applying known edits to real
filing sections, so the expected output is derived rather than labelled.
60 cases:

| | |
|---|---|
| Precision | 95.9% |
| Recall | 89.0% |
| F1 | 92.3% |
| Citation validity | 100%, 526 of 526 |

| Change type | Recall |
|---|---|
| Added | 120/120 |
| Removed | 116/119 |
| Reworded | 72/76 |
| Moved | 52/59 |

The confusion matrix is printed by the same command and rendered on the
`/metrics` page. The errors are mostly `moved` scored as `added`, which is
the expected failure: a paragraph that moves and is edited at the same time
stops being recognisable as the same paragraph.

**Citation validity** is a hard gate rather than a score. Every emitted span
must slice out of the stored section text byte for byte. This is enforced in
`finalize` at runtime and asserted in CI; a finding that fails is discarded,
not down-ranked.

**Trajectory**, scored per request kind: required nodes, nodes forbidden for
that kind, repeat detection, a step budget, and the rule that the generative
step must run after verification. This caught `finalize` and
`explain_findings` each running twice on the full path, which also billed
the model twice. Measured after the fix: a diff request takes 2.0s against
a full request's 6.3s, which is the conditional routing earning its keep.

**Coverage**: 202 offline tests, no network, no model calls.

**Ingest**: Item 1A for NVDA is 114,443 characters and is diffed whole.

## Architecture

```
          FastAPI
             |
        LangGraph
             |
    resolve_company
             |
     ingest_filings
         /        \
    run_diff    measure_attention
        |             |
   run_novelty        |
        |             |
    run_peer          |
         \           /
          finalize  (drops findings whose spans do not resolve)
```

`run_diff` and `measure_attention` run concurrently and merge through state
reducers. Routing is conditional on what was asked, so a diff-only request
does not pay for novelty, peers or attention.

Progress reaches the browser over SSE from the graph's own `astream_events`,
so the node names in the UI are the real ones.

- **Backend**: Python 3.12, FastAPI, LangGraph, Pydantic v2.
- **Frontend**: React 18, TypeScript, Tailwind, shadcn/ui. 1,900 lines, with
  every API type generated from the backend's OpenAPI schema.
- **Tests**: 255 offline, plus a live suite that hits EDGAR and Hacker News.

## Data sources

All free. No paid tier is required to run this.

| Source | Terms |
|---|---|
| EDGAR submissions, company facts, full-text search, filing RSS | No key, 10 req/sec, real User-Agent required |
| Hacker News via Algolia | No key |
| Bluesky (AT Protocol) | Free |
| Reddit | Free for non-commercial use, 100 QPM |
| Finnhub, Marketaux, Google News RSS | Free tiers |

X is not supported. Its free tier was discontinued for new developers in
February 2026 and reads are now billed per post.

Attention sources sit behind one interface and degrade independently. The
product works with none of them configured; it reports which were available
and flags that the score understates when some were not.

## Running it

Needs Python 3.12 and Node 20.

```bash
cd backend && uv sync
cp ../.env.example ../.env   # SEC_EDGAR_USER_AGENT is the only required value
uv run uvicorn vantage.api.app:app --reload
```

```bash
cd frontend && npm ci && npm run dev
```

Then open http://127.0.0.1:5173 and enter a ticker. `/metrics` shows the
diff engine's scores.

Only `SEC_EDGAR_USER_AGENT` is needed for the diff, novelty and peer engines.
Without an LLM key the findings come back unexplained, and the response says
so rather than quietly omitting it.

`SEC_EDGAR_USER_AGENT` must be a real contact string, which is SEC fair-access
policy. Everything else is optional: without `MONGODB_URI` the graph uses an
in-memory checkpointer and says so, and without the attention keys the
corresponding sources report themselves unavailable.

## Evaluation

```bash
uv run python -m vantage.eval.run_diff_eval          # the gate, offline
uv run pytest tests/test_trajectory.py -q            # path specs, offline
uv run pytest tests -q                               # 255 tests, offline
uv run pytest tests -q -m live                       # hits EDGAR and HN
```

The gate runs on every pull request and fails the build when recall drops
below the thresholds in `vantage/eval/thresholds.json`.

The golden set is generated, not hand-labelled. `vantage/eval/mutate.py`
takes a real filing section, applies a known set of edits, and the resulting
edit script is the expected output. Hand-labelling one 70,000 character Item
1A is a day of work; this produces hundreds of cases for the cost of compute.

The honest limitation of that approach is that synthetic edits are not real
editorial changes. It measures whether the aligner recovers a known edit
script, which is necessary but not sufficient for the engine being useful on
a real year-over-year comparison.

## Known limitations

- **Attention baselines run hot.** Real chatter is bursty, so variance
  exceeds the Poisson assumption and z-scores from the count-only path are
  inflated.
- **A flat baseline cannot alert.** With zero variance the z-score is forced
  to 0, which the logistic squash turns into attention 0.5, capping the gap
  score below the alert threshold. Pinned by a test.
- **Sentiment comes only from Marketaux**, and only from at most three
  articles per response on the free tier. Finnhub's sentiment endpoint is
  premium. Hacker News, Bluesky and Reddit contribute volume but no
  sentiment, rather than an invented score.
- **Moved paragraphs are the weakest change type** at 52/59, and the misses
  land in `added`.
- **Only 10-K to 10-K comparisons.** Comparing across forms is refused
  outright, because item numbering differs and the diff would be noise.
- **Reddit requires manual API approval** since self-serve registration
  closed in late 2025, so it may be unavailable to you.

## Not included

There is no vector store, no embedding model and no reranker. Section
alignment is structural, and adding semantic retrieval where exact alignment
already works would be decoration. The one place it would genuinely earn its
place is matching heavily reworded paragraphs that the aligner currently
scores as a removal plus an addition.

## License

MIT. See [LICENSE](LICENSE).

Research and educational use. Nothing here is investment advice, and the
system deliberately expresses no opinion about any security.
