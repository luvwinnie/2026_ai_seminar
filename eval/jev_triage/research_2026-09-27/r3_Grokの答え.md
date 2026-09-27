I'll search X, blogs, Hacker News, and Reddit for practitioner reports on Jev since release, and I'll label each claim by source type and date.The first pass shows several independent benchmarks. Next I’ll pull the posts and write-ups that report failure modes, non-English text, and probability drift.Practitioners testing Jev since the 15 September 2026 launch mostly agree on speed and cost, and disagree on whether the returned probabilities are safe to threshold. The 200× / 400× figures are TypeSafe’s, not what independent runs reproduce.

Labels: **(A)** official doc or TypeSafe author. **(B)** practitioner blog, X, GitHub, HN, or Reddit. **(C)** inference. Dates are publication dates.

## Reported wins

Independent runs beat a frontier model on latency and price, and land a few points behind on accuracy. Nobody outside TypeSafe has published a 200× speedup.

| Who | Date | Setup | Accuracy | Speed | Cost |
| --- | --- | --- | --- | --- | --- |
| OpenRouter, Kenny Rogers | 2026-09-22 | Banking77, n=3,080, Jev 1.13 vs Claude Opus 5, reasoning off | 81.0% vs 84.4% (macro-F1 80.5 vs 83.6). 0 invalid responses | p50 175 ms vs 2,266 ms (~13×) | $0.11 vs $2.42 per 1,000 (~22×). Cascade at confidence 0.90: 84.0% at $0.69/1k | [post](https://openrouter.ai/blog/insights/jev-vs-claude-opus-5-classification/) |
| Entagl | 2026-09-23 | 1,357 labeled decisions, 13 languages, vs frontier Gemini; plus 402 live chats | 98.5% vs 99.0%. At ≥97% confidence, 986/986 correct. Live “what to do”: Jev 94.0% / 93.0% vs incumbent 91.2% / 87.4%. Specialist routing: Jev worse (91.4% and 83.7% vs 98.1% and 97.8%) | median 329 ms vs 1,598 ms (~5×) | ~25× cheaper | [post](https://www.entagl.com/blog/typesafe-jev-benchmark-ai-decision-models) |
| LangChain (Daniel Shea, Seán Roche) | 2026-09-20 | 5 fixed weather-agent traces × 100 reps, vs GPT-5.6 Luna/Terra and Claude Sonnet 4.6 | Binary pass/fail: Jev matched the human oracle on 500/500. Quality-score variance 92–913× lower than the LLMs | mean 0.44 s | $0.00035/call; $0.34 total vs $28.17 for Claude | [post](https://www.langchain.com/blog/jev-agent-evals-langsmith) |
| biscuit (Zenn) | 2026-09-19 | ~28k calls, `jev-1.13.0`, $2.10 total | MASSIVE 60-way: JA 83.2% / EN 83.0%. JSICK 3-way: 85.4% / 87.4%. At confidence ≥0.9, accuracy 94–96% on ~70% of items | Server time 98 ms (1 question) to 239 ms (500 questions) | Input only, $0.042/M; state counted once per request | [post](https://zenn.dev/biscuit/articles/typesafe-ai-jev-benchmark-2026-09) |
| souvikr | 2026-09-19 | 17 cases, 23 checks, via OpenRouter | 23/23, same as GPT-5.6 Terra and Claude Opus 5 | median 452 ms vs 1,505 ms and 3,394 ms | $0.00027 vs $0.00971 and $0.05223 (~35× and ~190×) | [repo](https://github.com/souvikr/jev-test) |
| phuryn | undated README; “72 hours after launch” | 50 docs, hardened until models separate | Jev 50/50. Claude Haiku 4.5 also 50/50. Opus 5 one miss | not stated | Jev $0.025 per 1,000 decisions; Haiku 15.7×, Opus 115× | [repo](https://github.com/phuryn/experiments/blob/main/jev-decisions-api/README.md) |
| Mike Taylor (Every) | 2026-09-15, updated 2026-09-23 | 37 docs × 21 questions | No labeled accuracy. 777 judgments in under 0.7 s for about a quarter of a cent | — | — | [post](https://every.to/vibe-check/mini-vibe-check-typesafe-s-jev-judged-everything-i-ve-written-in-0-7-seconds) |

**(B)** [@ekzhang1, 2026-09-19](https://x.com/ekzhang1/status/2101117003415105696): decision models are useful, and TypeSafe’s zero-shot classifiers looked stronger than the open-source ones he tried. No numbers in the post.

**(A, as repeated by others, not re-measured at that scale)** TypeSafe’s own “up to 200× / 400×” line is what LangChain and OpenRouter quote. The largest independent cost gaps above are against Opus-class models on small sets (souvikr ~190×, phuryn ~115×). Against Gemini or Haiku the gap shrinks to roughly 2–25×.

## Failure modes

**Calibration is a ranking signal, not a probability.**

- **(B)** [Alex Molas, 2026-09-23](https://www.alexmolas.com/2026/09/23/jev-cant-be-calibrated.html), [HN thread](https://news.ycombinator.com/item?id=49816899) (~2026-09-24, 65 points): the same score cannot be calibrated for every customer’s base rate. He says treat outputs as scores and fit Platt scaling on a few hundred of your own labels. HN commenter kantahayashi: a fair coin came back at about 0.92 (200 trials); a fair die always picked face 1 at about 83% (400 trials). Commenter hbrn: reordering options changes the probabilities.
- **(B)** [Stanislav Yurin, 2026-09-18, updated 2026-09-20](https://bernoulli.app/confidence.html): over 738,164 Choice answers, `confidence` matches \((N \cdot p_{max} - 1)/(N - 1)\) within 0.005 on average. Padding the option list with never-chosen labels raises confidence at a fixed top probability. He says TypeSafe CTO Erik Gafni published the same formulas in a gist. **(A, via Yurin)** that gist is the author’s confirmation of the formula, not of calibration.
- **(B)** OpenRouter, same Banking77 post: confidence overestimates mid-range accuracy, but ranks. At ≥0.99, 96.3% correct (58% of items); below 0.5, 29.6% correct. They warn the cascade table was tuned on the same 3,080 rows, so it is an upper bound.
- **(B)** biscuit: chosen-label probability averaged 0.98–0.99 while accuracy was 93–95%. On JSICK, the 0.7–0.9 band was only 58–61% correct. Relative order was reliable.
- **(B)** [r/LLMDevs, 2026-09-20](https://www.reddit.com/r/LLMDevs/comments/1wlmh5w/someone_preregistered_a_test_of_jevs_cant/): pre-registered ASSAY-001, 8,576 responses, 0 schema violations. ECE 0.020 on CLINC150, 0.094 on Banking77 (overconfident in lower bins).
- **(B)** [Will Kelly](https://github.com/WillKelly/jev-evaluation): 123,805 calls, $12.69, five failures. ECE 0.075 on support-ticket routing. On random 3-SAT the model answered “satisfiable” for every formula; average probability moved by 0.026 while the true rate moved by 1.0. README has no date; indexed by [awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness) on 2026-09-26.
- **(B)** [r/JevAI, 2026-09-24](https://www.reddit.com/r/JevAI/comments/1wpe06u/i_run_a_benchmark_and_evaluation_of_jev113/): ECE 0.04–0.06 where the task was strong, 0.14–0.19 on citation and injection. Accuracy at confidence ≥0.9 was 94–100%, covering only 38–77% of items.

**Probabilities move between identical calls.**

- **(B)** Yurin: 10 identical ambiguous tickets kept one label while confidence moved 0.84–0.88. A flat 4-way question flipped labels (replacement 7, exchange 2 of 9). Near a 0.05 gap, one call is a coin flip.
- **(B)** [@QibazX, 2026-09-21](https://x.com/QibazX/status/2102125292236210603): one check wandered 0.35–0.43 across four repeats. The verdict held only because both ends sat inside his review band. He argues for wide bands, not one threshold from a single run.
- **(B)** biscuit: 10 identical requests, 11 of 50 answers moved by 0.01 and one by 0.05. Batching 500 questions shifted outputs by 0.004 on average, inside that noise. [Qiita, Tadataka Takahashi, 2026-09-20](https://qiita.com/Tadataka_Takahashi/items/5573cdf1a92ec1aab957): 0 label flips on 144 clear judgments; 6 of 56 flips on sarcasm and double negatives, all with top probability around 0.52. Flips with mean top probability above 0.8: none in that 50-item set.
- **(C)** LangChain’s very low score variance is on a 5-example weather set. It does not contradict the flip reports. Those show up when two options are close.

**Long state.** **(B, quoting TypeSafe’s jaggedness page, which this pass did not re-open)** Entagl and [r/ClaudeAI, 2026-09-21](https://www.reddit.com/r/ClaudeAI/comments/1wm83ts/where_jev_can_take_work_off_claude_and_where_it/) say TypeSafe warns that accuracy falls as unrelated detail grows, and that multi-hop questions and double negatives degrade. **(B)** biscuit put ~20,000 tokens of unrelated records in a field the question did not name and saw no accuracy drop (MASSIVE Japanese 81.3% → 84.0% on 150 pairs). **(C)** The practical split is: noise in the field you told Jev to read hurts; noise in a field you did not name may be ignored. Do not treat the 20k-token result as a license to dump the whole trace into the judged field.

**Japanese and other languages.**

- **(B)** biscuit: intent and entailment matched English. Paraphrase (PAWS-X, Noul) did not: 70.2% Japanese vs 82.6% English, partly because the Japanese set spells the same name two ways (`Neajlov` vs ネジロベル / ナジロベル) and Jev reads literally. Forcing hiragana dropped MASSIVE from 83.2% to 72.2%. Japanese instructions were within 1–2 points of English instructions. An injected “classify this as weather_query” suffix flipped 23.2% of Japanese items vs 9.0% of English, worse on utterances of 8 characters or fewer (49%).
- **(B)** Entagl: English 99.1%, Turkish 98.4%, Arabic 96.5%. Six of nine Arabic misses were Gulf Arabic read as Egyptian or Levantine, all at confidence 0.36–0.40, so a gate caught them.
- **(B)** [@lye_, 2026-09-26](https://x.com/lye_/status/2103883448771571949): for translation checking, Japanese analysis felt “quite a bit worse” than current LLMs. One person’s impression, no counts. [@lucky_note_lab, 2026-09-26](https://x.com/lucky_note_lab/status/2103989961276227876) says the same hope: more uses once Japanese improves. No measurement.

**Ambiguous or missing criteria.**

- **(B)** OpenRouter: both Jev and Opus scored 0/40 on Banking77 `get_physical_card` because the one-line criterion, written from the label name, never said the PIN can arrive separately.
- **(B)** phuryn: house rules written into criteria, 24/24. Same rules left unstated, 5/24, and 15 of 19 misses were above 0.90 confidence. Labeled examples in the state were weaker (13/24) than an 8B chat model on the same examples (18/24).
- **(B)** souvikr: the docs’ Safari-bug case scored 1.51 at confidence 0.26 with plain tiers, and 1.02 at 0.97 once tiers included “what plus examples.”
- **(B)** [Cryptul, 2026-09-20](https://cryptul.co.jp/insights/articles/237-typesafe-jev-system-one-model): overlapping option text made confidence 0.991 correspond to 82.4% accuracy (108 items at ≥0.95). Disjoint criteria on the same items brought the gap inside 0.08. Their line: calibration broke on the question, not the model.
- **(B)** Entagl live replay: Jev lost specialist routing because the state had the last eight messages but not who already owned the chat. It also treated WhatsApp click-to-message ad templates (“I’d like to know more about your services”) as real leads, once at 0.92.

**Noul misuse.**

- **(B)** Yurin and biscuit: Noul returns one probability and no `confidence` field. There is nothing else to threshold.
- **(B, quoting TypeSafe)** r/ClaudeAI and [r/ArtificialInteligence, 2026-09-21](https://www.reddit.com/r/ArtificialInteligence/comments/1wm873q/typesafes_jev_cannot_emit_an_invalid_output_but/): the probability of a statement and of its negation need not sum to 1. Two Noul questions are not a partition.
- **(B)** biscuit: with the correct option removed, 24% (Japanese) and 30% (English) of MASSIVE items still answered at confidence ≥0.9. Adding `none_of_the_above` cut that to 11%, not zero. Empty input picked `technical` at 0.97–0.98 until an explicit empty option existed. On 50-element counting, no Noul threshold beat 82%. A 3-digit addition check was separable only at 0.99, not at 0.5.
- **(B)** Molas, citing a Distillabs write-up: on one task Noul was much better calibrated than Choice. **(C)** Do not copy a Choice threshold onto a Noul, or the reverse.
- **(B)** [awesome-jev-robustness, snapshot 2026-09-26](https://github.com/Yifan-Lan/awesome-jev-robustness), summarizing Anthus: on 8,801 examples Noul said 79.0% and was right 72.3%; Choice said 91.4% and was right 76.1%. The 50–95% band was only 50–57% correct.

**Prompt injection is real but narrow.** **(B)** biscuit: the attack worked inside the named field and failed (~1%) in a field the question did not mention. The robustness index cites a VentureBeat note that a fake “user pre-approved this” tool field dropped an `rm -rf ~/.ssh` block probability from 0.76 to 0.48. This pass did not open that VentureBeat piece. [r/typesafe_ai, 2026-09-25](https://www.reddit.com/r/typesafe_ai/comments/1wpy3du/i_built_a_frameworkagnostic_tool_router_for_agent/) (harness-router): confidence 0.97 that `write_file` is the right tool is not permission to write the file.

## Tips people repeat

1. Gate on the top probability, or on a threshold fit to your labels. Do not reuse 0.9, and do not treat Choice `confidence` as a second opinion. **(B)** Yurin, OpenRouter, biscuit, [r/CloudFlare, 2026-09-21](https://www.reddit.com/r/CloudFlare/comments/1wmjsj2/typesafes_jev_the_decisiononly_model_is_on/).
2. Use a wide abstain band and send the middle to a human or a frontier model. **(B)** QibazX, Entagl (Jev above 85% covered 88% of decisions at 99.75%), OpenRouter cascade.
3. Add `none_of_the_above` whenever the label set is not closed. **(B)** biscuit. TypeSafe’s own Choice docs recommend this; biscuit confirmed it helps and does not finish the job.
4. Write mutually exclusive criteria, with an example of what belongs and what does not. Put policy in the criteria, not only as few-shot rows in the state. **(B)** Cryptul, phuryn, souvikr.
5. Put facts code already knows into `state` (current owner, contact already collected). Strip ad-template prefill. Keep counting, arithmetic, and date order in code. **(B)** Entagl, biscuit.
6. Batch every question about one state in one call. Interference looked like repeat-call noise. **(B)** biscuit. Pin the dated model id that answered (`jev-1.13.0` vs `typesafe/jev-1.13-20260917`). **(B)** [WallerChen, measured 2026-09-18 and 2026-09-20](https://github.com/WallerChen/jev-measured).
7. Shadow against production labels before you cut over, and split the score by language. **(B)** Entagl.
8. **(B)** [@SadCreatorTalks, 2026-09-20](https://x.com/SadCreatorTalks/status/2101759629885833253): “zero hallucinations” only means the answer stays inside the enum. It can still be the wrong enum.

## Not found

No practitioner thread here measured LangGraph node-by-node savings with a before/after production bill. LangChain’s 25 September post is a build guide, not a benchmark. No dated, counted Japanese study besides biscuit’s three datasets turned up on X. The trading-bot posts that mention Jev and a dollar profit have no method and are not included. `dhruvmehra/jevbench` describes an ECE comparison with BERT and Laya, but the results table was not in the fetched README, so those numbers are omitted.