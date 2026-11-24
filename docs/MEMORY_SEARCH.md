# Memory versus search experiments

GEOSITION measures unassisted brand recall separately from visibility with live search available. The first release runs paired Gemini API requests and produces JSON, terminal, and standalone HTML evidence reports. It is available through `geo benchmark experiment`; hosted dashboard collection is not enabled by this release.

Memory share is a proxy for model knowledge without retrieval. It does not identify training sources. Search-enabled answers can combine model knowledge and search results, and enabling search does not prove the model used it.

## Create a frozen experiment

Use your own customer questions without brand, product, alias, or domain names. Target and competitor identities are used only for scoring and leakage checks. They are never added to the provider request.

```bash
geo benchmark experiment create geositionai.com \
  --brand "GEOSITION AI" --alias GEOSITION \
  --model gemini-2.5-flash \
  --prompts-file examples/memory-search/prompts.json \
  --repetitions 3 --max-requests 30 \
  --output experiment.json
```

This command makes no network requests. It freezes prompt IDs/text/locale, model, generation settings, repetitions, and configuration hashes. Locale fields record requested values; this collector does not enforce country or certify effective language/region. An optional `--competitors-file competitors.json` accepts a JSON list such as `[{"name":"Example Rival","domain":"rival.example","aliases":["Rival Product"]}]`. Add each tracked product name as an alias. Prompts containing any tracked identity are rejected.

The example questions are a starting point, not a representative customer sample. The default output limit is 1,024 tokens per request; use `--max-output-tokens` if your chosen model needs more. Truncated answers are excluded from valid-answer rates.

## Collect one measurement wave

Configure `GEMINI_API_KEY` in your environment, then run:

```bash
geo benchmark experiment run --experiment experiment.json --output baseline.json
```

This command makes paid generation requests. It first checks the selected model's advertised `generateContent` availability. Google model metadata does not certify search support; unsupported search requests are recorded as failures without changing the model or removing the tool. Confirm account/model search support before a pilot.

Unassisted requests contain one fresh user prompt and no retrieval tools, system instructions, cached content, files, or prior conversation. Search-enabled requests use the same prompt/settings plus Google Search. Conditions alternate in order between prompts/repetitions. The returned model version is retained, and different versions are never paired together.

Each attempt is checkpointed in `baseline.json`. Raw provider responses are saved separately under `baseline.artifacts/`, with distinct filenames for every condition and trial. `baseline.report/` contains `memory-search.json` and `memory-search.html`. The canonical file records the local artifact base; raw artifact references may instead be remote URIs if the existing artifact backend is configured. Keep canonical files and artifacts together when sharing evidence and review customer data before sharing.

Existing canonical output files are preserved. Re-running a partially collected file is rejected; use the original frozen experiment and a new output path to start another wave. The original attempts remain available for inspection.

`--max-requests` is an upfront generation-request limit. There are no automatic retries. `--max-output-tokens` bounds each request's generated output. Optional `--max-total-tokens` stops subsequent requests after observed provider token usage reaches the limit; the final request can cross it. Missing usage stops further calls when that budget is configured. Search query counts and token usage are reported, but these controls are not a hard monetary or search-call spend cap.

## Read the results

```bash
geo benchmark experiment report --input baseline.json --output-dir reviewed-report
```

Report generation is offline. Per provider, surface, returned model version, and tracked brand, the report shows:

- Brand mentions and conservative explicit recommendations.
- Owned-domain citations with provider-supported answer spans.
- Observed search use, unknown search use, and search-backed brand references.
- Raw outcome counts, valid answer counts, prompt counts, failure/refusal/empty statuses, unclassified observations, and missing trials.
- Search-minus-unassisted differences using complete prompt/trial pairs, with prompt-cluster bootstrap intervals when at least two prompts are available.
- Raw artifact references, retrieved sources, citation spans, and classification evidence for every answer.

Rates are percentages, averaged equally over prompts. For example, a prompt with two successful trials does not outweigh another prompt with one successful trial. Denominators include valid nonempty answers in the assigned condition; failures, refusals, and empty/truncated answers are reported separately. Brand rates can add to more than 100% because an answer can mention multiple brands.

Search-use rates use only answers where search use is known and show their known/unknown counts. In `generateContent`, missing grounding metadata is treated as unknown search use, not proof of no search. Search-backed reference rates count observed provider-supported brand mentions over all valid answers; they do not attribute every sentence to search. Retrieved chunks without claim support are kept as retrieved sources, not citations. URLs invented or merely written by the model do not establish retrieval.

Recommendation classification recognizes explicit English/French verbs and excludes negated sentences. It is a conservative rule, not a general semantic judge; implied preferences and other languages require evidence review. A third-party citation can support a brand recommendation without citing the brand's own domain. Provider redirect URLs are preserved without fetching them; unresolved domains can undercount owned-domain citations.

Small repeated samples are exploratory. Unassisted recall can vary between requests even without a model update; search has no guaranteed indexing timeline. Treat a condition difference as an observed experimental result, not an exact split of training knowledge and retrieved knowledge.

## Compare later waves

Reuse the same frozen experiment with a new output path:

```bash
geo benchmark experiment run --experiment experiment.json --output followup.json
geo benchmark experiment compare --before baseline.json --after followup.json --output comparison.json
```

Comparison rejects changed prompts, generation settings, models, repetitions, or tracked identities. It compares only matching valid prompt/trial/condition/returned-version slots and reports unmatched observations. No matched model version yields unavailable comparison, not a zero gain. Before/after movement is an association, not proof a website change caused it.

Canonical experiment JSON and benchmark exports retain the manifest and all attempts. Importing those records into an existing benchmark attaches a `memory_search_experiment` evidence artifact to the run; `BenchmarkStore.get_evidence_artifacts()` and benchmark rehydration return it. Existing benchmark scores keep their current meaning; use the experiment report for the two separate visibility tracks. Legacy records and opaque browser/tracker observations without explicit matching controls remain unclassified.

## Provider references

Implementation uses the existing `generateContent` endpoint and its byte-indexed grounding support segments, rather than interpreting a different API's response format. Checked 2026-11-14:

- [GenerateContent API and response schema](https://ai.google.dev/api/generate-content): grounding chunks, supports, search queries, returned model version, and usage.
- [Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search): discretionary search behavior and supported models.
- [Model metadata](https://ai.google.dev/api/models): advertised generation methods. Search capability still requires an account-specific pilot.
