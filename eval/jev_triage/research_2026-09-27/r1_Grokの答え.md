I'll research how teams are wiring Jev into production as of late September 2026, using only web search, page fetches, and X posts, and I'll tag each claim as official, practitioner-reported, or inference.The launch posts and the LangChain write-up are the main sources. Next I’ll pull the official docs and the named production write-ups so thresholds, graph wiring, and numbers stay tied to a URL.Jev has only been public since **15 September 2026**. What follows is the implementation pattern in the docs and in the first twelve days of write-ups, not a mature production literature. Each claim is tagged **(A)** official doc or original author, **(B)** practitioner report, or **(C)** inference. If a number is missing, it was not found.

## The pattern vendors are teaching (A)

TypeSafe’s design rule is “code owns the workflow; the model only makes narrow, typed decisions.” Control flow, arithmetic, and side effects stay in code. Jev is called only where the input is unstructured and the answer set is closed. One `POST https://api.typesafe.ai/v1/systemone` takes a `state` plus a map of questions and returns **Choice**, **Score**, and/or **Noul** answers in parallel. Source: [How to build with TypeSafe](https://docs.typesafe.ai/concepts/how-to-build-with-system-one) (retrieved 2026-09-27; no page date) and [Models](https://docs.typesafe.ai/models) (same).

Documented seats for that call:

| Seat | Where it is specified |
| --- | --- |
| Router | Confidence-gated routing; LangChain `ModelRouterMiddleware` |
| Classifier | `TypeSafeClassifier`; ticket triage sample |
| Tool gate | `AutoModeMiddleware` on `wrap_tool_call` |
| Guardrail | [LLM guardrails cookbook](https://docs.typesafe.ai/cookbooks/llm_guardrails) (numbers from `jev-1.12`, 2026-08-15) |
| Eval judge | LangSmith decision-model evaluators; Langfuse “Jev as a judge” |
| Reranker | [Re-ranking cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe): one Noul per query–passage, CLERC top-1 5% → 18%, top-10 38% → 62% (`jev-1.12`) |
| Verifier of an LLM | [SDE cascade cookbook](https://docs.typesafe.ai/cookbooks/sde_cascade.md): cheap extract → per-field Noul → escalate to a reasoning model. The how-to guide also decomposes a tool-call trace into atomic Nouls |

Jev is explicitly **not** a chat or coding model. [Coding agents](https://docs.typesafe.ai/introduction/coding-agents) (indexed 2026-09-21) says there is no setting that turns Cursor or Claude Code into a Jev agent.

The same API is reachable without a TypeSafe account as `typesafe/jev-1.13` on `POST https://openrouter.ai/api/alpha/decisions`, or as the TypeSafe SDK pointed at `https://openrouter.ai/api`. [OpenRouter Jev guide](https://openrouter.ai/docs/guides/community/jev) (2026-09-24). Listed price on both sides: **$0.042 / 1M input tokens, output unmetered**. [Models](https://docs.typesafe.ai/models); [OpenRouter model page](https://openrouter.ai/typesafe/jev-1.13) (2026-09-18).

## How LangGraph / LangChain is actually wired (A)

Two official surfaces, both from LangChain.

**Middleware on `create_agent`**, documented at [TypeSafe integrations](https://docs.langchain.com/oss/python/integrations/providers/typesafe) (retrieved 2026-09-27):

- `ModelRouterMiddleware` (`before_agent`, `wrap_model_call`) classifies the latest human message into named `ModelChoice`s and sticks with that model for the run. Probabilities stay in agent state.
- `AutoModeMiddleware` (`wrap_tool_call`) asks a Noul whether a listed tool call is risky. A risky call becomes an error `ToolMessage` and never runs. The docs say this **refuses**; it does **not** ask a person. Pair it with human-in-the-loop middleware if you want approval.
- A custom middleware example classifies messages in `before_agent` and stores the whole `ChoiceAnswer` on state. `before_model` is the hook if you want to reclassify after each tool result.

**A LangGraph, not just middleware**, in [Building Prod with Jev and LangGraph](https://www.langchain.com/blog/building-prod-with-jev-and-langgraph) (Sydney Runkle and Hunter Lovell, **2026-09-25**). Their discovery graph asks three questions per page in one request. Code maps the answers onto routes: not responsive → set aside; PII → an LLM redacts; possible privilege → `interrupt()` into `attorney_review`, then resume. Checkpointing is justified because a rerun might not retrace a model path. They report Jev **5–6× faster than Sonnet on the classification step**, with both runs in LangSmith. The post links a gist and traces; this research did not open that gist, so the conditional-edge source itself was not verified. The blog describes the routes; it does not print `add_conditional_edges`.

Earlier the same authors, [Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev) (**2026-09-17**), show the same middleware and name three early projects without code: Browserbase browser actions, Jarrod Watts’s live trading agent, Ryan Vogel’s email triage. Those two posts were not fetched here.

## Named systems, and what they actually did

**(A) Browserbase Stagehand.** Kyle Jeong, [What is Jev?](https://www.browserbase.com/blog/what-is-jev/) (**2026-09-21**). `act()` marks interactive nodes, Jev picks the action type and the best candidate, and **anything under 0.7 confidence falls back to an LLM**. Early testing: median `act()` **1.97s → 0.46s**. He argues Jev should not be the agent. On X the same day he also reported success **85% → 95.4% across 240 real-site runs** ([thread](https://x.com/kylejeong), posts 2026-09-18). That success rate is not in the blog. An experimental WebMCP PR uses a stricter gate (≥ 0.8 and “none” ≤ 0.2) and reports p50 **301 ms** on a merged request ([stagehand#2988](https://github.com/browserbase/stagehand/pull/2988)); treat that as a PR, not the shipped path.

**(A) OpenRouter Jev Router**, model `typesafe/jev-router`, released **2026-09-25** ([model page](https://openrouter.ai/typesafe/jev-router); [OpenRouter thread](https://unrollnow.com/status/2103610898690855161), 2026-09-25). Before a chat completion, Jev judges difficulty and whether the current model and reasoning effort are enough. It can change effort without switching models, and it switches only when the expected gain beats the cost of losing the cached prompt. On OpenRouter’s own four agent benchmarks: **237/423 tasks vs 130/423** for Auto Router. If the Jev call times out or is invalid, the request **fails**; it does not fall through to another router.

**(A) LangSmith judge experiment.** Daniel Shea and Seán Roche, [Jev-as-a-Judge for Agent Evals](https://www.langchain.com/blog/jev-agent-evals-langsmith) (**2026-09-20**). Five fixed weather-agent traces, 100 repeats, human labels as oracle. Jev matched the binary oracle on **all 500** decisions; quality-score variance **0.0000149** (92–913× lower than the LLM judges). **$0.00035/call**, **0.44s** average, **$0.34 total vs $28.17** for Claude Sonnet 4.6. Repo: [danielgshea/jev-as-a-judge](https://github.com/danielgshea/jev-as-a-judge). They call the test narrow. Access via `langchain-typesafe==0.0.1a2`.

**(A) Langfuse.** [Jev-as-a-judge in Langfuse Evaluators](https://langfuse.com/blog/2026-09-22-running-evals-with-jev) (**2026-09-22**) and [docs](https://langfuse.com/docs/evaluation/evaluation-methods/jev-as-a-judge). A decision-model evaluator maps state from the trace, asks several questions, and writes one score per question. Online rules can score live traffic. Langfuse marks it experimental. The 18 September post shows a user-disagreement Noul as the question shape, not a measured customer deployment.

**(B) GitLoom.** Ahmet Ozisik, [Where Jev worked for us](https://gitloom.ai/blog/jev-in-production) (**2026-09-22**). Four production decisions moved over: PR kind (Choice), review-thread resolved (Choice including `unclear`), query relevance (0–1), and draft guardrails. Rule: **act only above 0.8, otherwise leave the old behavior**. On 60 self-labeled PRs, the sorter was **98.0% correct on the 85% of cases it answered**, vs **88.2%** for the pattern matcher it replaced. Sorting by score failed: once a PR is clearly on-topic, scores pile up at 0.97–0.99 and no longer rank usefulness. Category cost about **six cents per thousand**.

**(B) Drew Dillon, Brief** ([post](https://x.com/drewdil/status/2100684145286684872), **2026-09-17**), one day of production-judge comparisons, ~3,700 calls, median **100–200 ms**, nine server errors. Fixed-list tasks matched or beat their small classifiers (32 call types: 35/36 vs 34/36, ~100× cheaper; Slack buckets 16/16; a 47-case graph-typing set passed their gates, ~65× cheaper and ~15× lower latency). Quality, contradiction, and code-review judgments did not: contradiction detection found **2 of 12**; a Jev-only reviewer found **none of 13** human findings on merged PRs. When Jev was wrong, confidence was usually low; a frontier model was 95% confident on both of its misses.

**(B) OpenRouter’s own Banking77 study**, [Jev vs Claude Opus 5](https://openrouter.ai/blog/insights/jev-vs-claude-opus-5-classification/) (**2026-09-22**): 3,080 utterances, Jev **81.0%** vs Opus 5 **84.4%**, p50 **175 ms** vs **2,266 ms**, **$0.11 vs $2.42 per 1,000**. Confidence ranked accuracy: **96.3%** at ≥ 0.99 (58% of traffic), **29.6%** under 0.5. Sending everything under 0.90 to Opus recovered **84.0%** at **$0.69 / 1,000**.

Not implementations: IrenicTech (**2026-09-21**) counted 21 decision points and said six *would* change, and recommended a shadow run. MI Code (**2026-09-20**) audited five LangGraph agents for seats Jev *could* take. SitePoint (**2026-09-18**) is a tutorial harness (router + tool gate + hard deny-list), not a deployed system.

## Thresholds and abstain (A, with B calibrations)

Official pattern on [Confidence](https://docs.typesafe.ai/confidence) and [Confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing): three bands, and the number depends on the action.

- Choice/Score expose `confidence` (0–1), computed from how peaked `probabilities` is. Noul has **no** confidence field; the probability is the answer. Do not treat a Noul of 0.5 as “medium.”
- Worked policy: under **0.6**, any intent goes to a person; `check_balance` may proceed at 0.6; `approve_transfer` auto-runs only **above 0.85**, otherwise the user confirms. A second sample uses **0.5** as the “don’t guess” floor and **0.9** for the transfer.
- The full triage sample routes to a human if a weighted spam score is between **0.4 and 0.6** or topic confidence is **under 0.75**; quarantine at spam **≥ 0.6**; treat refund/order Nouls as true at **≥ 0.7**.
- [Models](https://docs.typesafe.ai/models): pin `jev-1.13.0` once thresholds are tuned. `jev-latest` can move and change the distribution. Log the `model` field on the response.
- Docs say start conservative and plot confidence against accuracy on your own labels. No universal threshold was found.

**(B)** Stanislav Yurin, [Is Jev confident?](https://bernoulli.app/confidence.html) (**2026-09-18**): confidence is essentially the top probability rescaled by option count, so a threshold tuned on 3 options is not the same number on 20. Run-to-run wobble of about 0.02–0.04 can flip a label when the top two are within ~0.05. AnthusAI’s [Jev-Calibration](https://github.com/AnthusAI/Jev-Calibration) reports isotonic regression cutting ECE from 0.117 to 0.008 on their split; that is their dataset, not TypeSafe’s claim.

## State, criteria, fan-out (A)

From the how-to guide and [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) (last reviewed **2026-09-17**):

- State is nested JSON. Point a question at a field with a backticked path (`support.tickets[0].message`). Send only what that question needs. “Accuracy falls as the state grows with content unrelated to the decision.”
- One judgment per question. Criteria are contrastive objects: `what`, `not_for`, `examples`, same fields on every option.
- Ask every question you might need in **one** request, including ones code may ignore ([speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)). Questions are independent; one answer is not hidden context for the next.
- Combine in code (weighted sum of Nouls, or a classical model on the probabilities). Do not ask Jev to count, compare dates, or do arithmetic. A Noul and its negation are not guaranteed to sum to 1 (published example: 0.72 and 0.47).
- Budgets: **64k** tokens for state plus all questions; **32k** for state plus the longest question. Text only. Rate limits stated as **250,000 tokens/s and 1,200 rpm**, and the models page warns both are moving. “Most queries complete in about 100 ms” is the how-to guide’s figure. A **70–500 ms** range is widely repeated from the launch post; this pass did not open that post, so it is not cited as verified here.

## Batching, caching, fallbacks

**(A) Batching is the documented cost lever.** [Parallel questions](https://docs.typesafe.ai/cookbooks/parallel_questions) (page indexed 2026-09-22, run on `jev-1.12`): 13 questions on one article, **$0.000497 and 0.27s** in one call vs **$0.006090 and 2.71s** as 13 serial calls — **12.2× cheaper, 10.0× faster** — with answers unchanged across five repeats. The state is billed once. `TypeSafeClassifier` is a LangChain runnable, so `.batch()` exists; no separate batch HTTP API was found.

**(A) No Jev prompt cache was found.** Cookbook `JsonCache` is a local replay file for the docs. The skill-suggestion cookbook’s prefix cache is on the **chat** model’s roster, not on Jev. The cache that matters in production writing is OpenRouter’s: switching the downstream chat model throws away the cached conversation, which is why Jev Router tries not to switch.

**(A)/(B) Fallback shape that keeps showing up:** Jev handles the confident closed choice; a frontier model or a person gets the rest (Browserbase 0.7, OpenRouter 0.90 study, TypeSafe’s “route on uncertainty,” LangChain’s privilege interrupt). GitLoom’s fallback is “do what we did before,” not a bigger model. OpenRouter’s router does **not** fail open.

## Monitoring and how people score accuracy

Found:

- LangSmith traces for `TypeSafeClassifier` (decision, token usage, spend) and, per the 25 September post, dedicated views of decision-model inputs and outputs.
- LangSmith [decision-model evaluators](https://docs.langchain.com/langsmith/decision-model-evaluator) (docs dated 2026-09-25): state mapped from the run, grading only in the questions, each question name becomes a feedback key. OpenRouter can be a base URL.
- Langfuse online evaluators, filters, and sampling, with Jev as one evaluator type. That can trend a score. It is not a Jev-specific drift detector.

Not found: a published production setup that tracks drift of Jev’s own decision distribution, or disagreement between Jev and a human reviewer as an ongoing metric. A Langfuse RFC on session-boundary drift (August 2026) predates Jev and does not mention it. TypeSafe says it does not fine-tune on customer traffic ([Models](https://docs.typesafe.ai/models)); adaptation is state, criteria, and code.

Accuracy methods that were actually written down: human labels on a frozen trace set (LangChain, n=5 tasks); a public intent corpus (OpenRouter, Banking77); a small self-labeled set plus an abstain rule (GitLoom, n=60); head-to-head against the incumbent judge on production fixtures (Brief). TypeSafe’s own “200× / 400×” figures are the company’s, cited by LangChain on **2026-09-25** from the [launch post](https://typesafe.ai/blog/introducing-system-one-models-and-jev). Secondary write-ups say those labels are agreement with frontier models, not human ground truth. This pass did not open the evals page, so that label method is **not** confirmed here.

## (C) What this adds up to

The repeated production shape in this two-week window is a **gate in front of a frontier model**, not a replacement: one batched Jev call, atomic questions, contrastive criteria, a pinned model id, a risk-dependent threshold, and an explicit abstain path (human, frontier LLM, or the previous deterministic rule). LangGraph is used as the place those branches and interrupts live; the shipped LangChain code is middleware hooks more often than hand-drawn conditional edges. Ranking, open-ended quality, and “is this good?” are the seats practitioners say failed. Nobody in these sources has published a calibrated threshold you can copy, and nobody has published a Jev drift monitor.