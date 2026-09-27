I'll look up the official TypeSafe and OpenRouter docs, plus recent posts, for the current Jev model, request schema, limits, pricing, and Python packages.Official docs list Jev 1.13 as current. Next I’ll pull the API reference, changelog, retention policy, and package docs so the schema and limits are quoted rather than inferred.**Jev 1.13.0 is still the only public model.** Official docs, OpenRouter, and recent posts show no `jev-1.14` or `2.x`. Question types remain `noul`, `choice`, and `score`. There is no temperature, seed, streaming, or decisions batch API in the published schemas.

## (A) Model and changelog — official

TypeSafe’s [Models](https://docs.typesafe.ai/models) page (indexed 2026-09-22) lists one model:

| | |
| --- | --- |
| Versioned ID | `jev-1.13.0` |
| Price | **$42 / billion input tokens** ($0.042 / million). Output tokens are free. |
| Rate limits | 250,000 tokens/second and 1,200 requests/minute. Over either limit: `429`. SDKs retry and honor `retry-after`. |
| Context | **64k tokens** for state plus all questions; **32k** for state plus the single longest question. |
| Input | Text only: string, JSON object, or array of text. No image, audio, or video. |

Aliases: `jev-latest` and `jev-preview` both point at `jev-1.13.0`. The page says there is **no preview build**. The response `model` field is the versioned ID. `GET /v1/models` lists aliases (`name`, `description`, `release_date`); versioned IDs are accepted even if absent from that list.

The same page warns that rate limits “can change without notice.” There is **no model changelog** beyond that page. [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) (last reviewed 2026-09-17) says many failure modes “will be fixed in later versions,” which implies later versions are not shipped. Launch post: [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev), 15 Sep 2026 (Diogo Almeida).

OpenRouter ([model page](https://openrouter.ai/typesafe/jev-1.13), released 18 Sep 2026; [Jev guide](https://openrouter.ai/docs/guides/community/jev), indexed 2026-09-24): `typesafe/jev-1.13`, alias `~typesafe/jev-latest`, **32,000-token** context (narrower than TypeSafe’s 64k combined budget), $0.042 / $0 per million. Responses name a dated snapshot, e.g. `typesafe/jev-1.13-20260917`.

## (A) TypeSafe System One schema

`POST https://api.typesafe.ai/v1/systemone` — [API reference](https://docs.typesafe.ai/api), indexed 2026-09-20. Bearer `TYPESAFE_API_KEY`.

**Request (required `state`, `model`, `questions`):**

```json
{
  "state": "Help! My payouts have been failing for 3 days.",
  "model": "jev-latest",
  "questions": {
    "is_urgent": { "type": "noul", "instructions": "Does this convey urgency?" }
  }
}
```

- `state`: string | object | array.
- `questions`: map. The key is not sent to the model. Each question has `type` and `instructions` (string | object | array).
- **Noul:** optional `criteria.true` / `criteria.false`.
- **Choice:** required `criteria` map, description or `null`. **“You can have a maximum of 255 options per Choice.”**
- **Score:** required ordered `criteria` array. **“at least two levels; the API accepts up to 10.”**

**Response:** required `model`, `answers`, `usage.input_tokens`, `usage.output_tokens`. **No `id`, `cost`, or `confidence` on noul.** Request id is the `x-typesafe-request-id` header, exposed as `SystemOneResponse.request_id` ([responses](https://docs.typesafe.ai/sdk/python/api/types/responses), retrieved 2026-09-27).

| Answer | Fields |
| --- | --- |
| noul | `type`, `noul` (0–1) |
| choice | `type`, `choice`, `probabilities` (sum to 1), `confidence` |
| score | `type`, `score` (probability-weighted; can fall between levels), `legend`, `probabilities`, `confidence` |

[Confidence](https://docs.typesafe.ai/confidence) (retrieved 2026-09-27): derived from the distribution, not a separate sample. Noul has none. The docs do **not** publish the exact formula; a three-option demo uses `(n × peak − 1) / (n − 1)`.

Errors: 401, 422, 429, 529. No `temperature`, `seed`, `stream`, or abstain field appears in this reference.

## (A) OpenRouter Decisions schema

`POST https://openrouter.ai/api/alpha/decisions` — [OpenAPI](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request), retrieved 2026-09-27. Discriminator is only `noul` | `choice` | `score`.

**Request required:** `model`, `state`, `questions`. Optional: `session_id` (≤256, not sent to the provider), `user` (≤256), `provider` (routing, including `zdr`), `trace`.

**Response required:** `model`, `answers`, `usage.input_tokens`, `usage.output_tokens`. Optional: `id` (example `gen-dec-…`), `provider`, `usage.cost` (USD). Choice `confidence` and `probabilities` are **optional** in this schema; score `confidence`, `legend`, and `probabilities` are optional. Noul is only `type` + `noul`. Score `criteria` here has `minItems: 1`, which is looser than TypeSafe’s “at least two.” The OpenAPI does **not** restate the 255-option cap.

TypeSafe-shaped calls: `POST https://openrouter.ai/api/v1/systemone` ([Jev guide](https://openrouter.ai/docs/guides/community/jev), 2026-09-24). SDK `base_url="https://openrouter.ai/api"` maps `jev-1.13` → `typesafe/jev-1.13` and `jev-latest` → `~typesafe/jev-latest` ([usage](https://docs.typesafe.ai/sdk/python/usage), indexed 2026-09-26).

## (A) What is not in the API

| Asked feature | What the docs actually say |
| --- | --- |
| Multi-label, ranking, abstain types | Not question types. Multi-label is several nouls. Ranking is Choice probabilities or per-candidate questions ([skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion), [re-ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe), indexed 2026-09-22). Abstain is an app threshold on `confidence` or top probability ([choice consistency cookbook](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook), 2026-09-22). |
| Calibration knob | Training method is RLCD ([Models](https://docs.typesafe.ai/models)). No request field. |
| temperature / seed / determinism | Absent. Cookbooks vary calls with a throwaway `uid` in state because repeats are not identical. |
| Max questions per call | **No numeric cap found.** Bound is the token budget. Fan-out is one POST, questions in parallel ([fan-out](https://docs.typesafe.ai/patterns/fan-out)). |
| Batch endpoint / streaming | Not in the System One or Decisions operations. Response is one JSON body. |
| Max state bytes | **Not published.** OpenRouter can return 413. |

## (A) Retention and ZDR

- [Models](https://docs.typesafe.ai/models): “Jev is not trained on customer requests or responses.” ZDR is **enterprise**, via sales@typesafe.ai ([Legal](https://docs.typesafe.ai/legal), indexed 2026-09-24).
- [Privacy policy](https://typesafe.ai/legal/privacy-policy), last updated **19 Nov 2025**: will not train or fine-tune on Input, and will not disclose Input except to service providers. Retention of personal data is “as long as reasonably necessary” — **no prompt TTL**.
- [DPA](https://typesafe.ai/legal/data-processing), **24 Apr 2026**: retain customer personal data as long as necessary for the service.
- [Master customer agreement](https://typesafe.ai/legal/mca), **23 Sep 2026**: no obligation to store Customer Data; it may be deleted at any time. **Telemetry** (logs, hashes, summary statistics and classifications, metrics) may be processed **in perpetuity**, including to improve the services. That is narrower than “we keep nothing.”
- OpenRouter [provider logging](https://openrouter.ai/docs/guides/privacy/provider-logging) (page fetched 2026-09-27): **TypeSafe = zero retention, does not train.** OpenRouter itself does not store prompts unless logging or product-improvement opt-in is on ([data collection](https://openrouter.ai/docs/guides/privacy/data-collection)). Decisions requests can set `provider.zdr: true` ([ZDR](https://openrouter.ai/docs/guides/features/zdr), indexed 2026-09-17).

## (A) Python packages

**`typesafe-sdk`** (import `typesafe_sdk`), Python ≥ 3.10. Docs changelog [v0.7.2 (2026-09-26)](https://docs.typesafe.ai/sdk/python/changelog): adds an `http2` extra. PyPI’s listing and the repo `pyproject.toml` still showed **0.7.1** (21 Sep 2026) when fetched — treat 0.7.2 as documented, not confirmed on the index. Earlier: 0.7.1 key check; 0.7.0 (18 Sep) **msgspec → pydantic** and `response_model`; 0.6.0 Score criteria became a sequence; 0.5.7 first public release.

Main surface ([sync client](https://docs.typesafe.ai/sdk/python/api/clients/sync), [questions](https://docs.typesafe.ai/sdk/python/api/types/questions)):

- `TypeSafeClient` / `AsyncTypeSafeClient`: `system_one(state, questions, *, model, retry, timeout, extra_headers, extra_body, response_model)`, `models.list()`, `close()`.
- Questions: `Noul`, `Choice`, `Score`, `NoulCriteria`; dict forms `NoulModel`, `ChoiceModel`, `ScoreModel`.
- Answers: `SystemOneResponse` (`.answers`, `.nouls`, `.choices`, `.scores`, `.request_id`), `NoulAnswer`, `ChoiceAnswer`, `ScoreAnswer`, `Usage`.
- Also `RetryPolicy`, `ListModelsResponse`, `ModelMetadata`, and `TypeSafe*` errors. Default model env: `TYPESAFE_DEFAULT_MODEL=jev-latest`. Default base: `https://api.typesafe.ai`.

**`langchain-typesafe`**: PyPI **0.0.1a3** (20 Sep 2026); 0.0.1a1 was 17 Sep ([PR #40542](https://github.com/langchain-ai/langchain/pull/40542)). [LangChain docs](https://docs.langchain.com/oss/python/integrations/providers/typesafe): `TypeSafeClassifier` is a `Runnable`. **Current API passes both `state` and `questions` to `invoke`**; older builds set `questions` on the constructor. Exports used in the docs: `Choice`, `Noul`, `Score`, `TypeSafeClassifier`. Response mirrors the SDK (`nouls` / `choices` / `scores`, `model`, `usage`, `request_id`). POSTs `{base_url}/v1/systemone` (default `https://api.typesafe.ai`). LangChain’s skill file calls `0.0.1a3` alpha and the class `@beta` ([langgraph-decision-models skill](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/langgraph-decision-models/SKILL.md)).

## (B) Practitioners

- [sebastianbugal/jev](https://github.com/sebastianbugal/jev/blob/main/jev/reference/decisions-api.md), checked live **18 Sep 2026**: `POST /api/v1/alpha/decisions` is 404; pinned build `typesafe/jev-1.13-20260917`; do not retry 400/401/402/403/413.
- [@Sion_Smith](https://x.com/Sion_Smith/status/2103758168949915703), **26 Sep 2026**: “no batch endpoint”; packed 20 lines × 7 questions per call on `typesafe/jev-1.13`.
- No dated post from TypeSafe or OpenRouter announces `jev-1.14` or `jev-2`. A 27 Sep post that only says “JEV 2.0” ([@YG49229860](https://x.com/YG49229860/status/2104022642365956402)) is not a release. “Jev Router” posts (26 Sep) describe OpenRouter **routing that uses Jev**, not a new weight.

## (C) Inference

`jev-latest` can move without a client change, so production thresholds should pin `jev-1.13.0` (TypeSafe) or `typesafe/jev-1.13-20260917` (OpenRouter). The 64k vs 32k context figures are different products’ published budgets, not evidence of two model weights. Enterprise ZDR is a contract add-on; the default MCA still allows telemetry to be kept and used to improve the service.