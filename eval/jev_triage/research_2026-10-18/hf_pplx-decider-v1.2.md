---
license: apache-2.0
base_model: Qwen/Qwen3.8-27B
base_model_relation: finetune
library_name: pytorch
pipeline_tag: text-classification
tags:
  - classification
  - multimodal
  - custom-code
  - decider
---

# pplx-decider-v1.2

pplx-decider-v1.2 is the next version of our
[pplx-decider-v1.1-27b](https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b) decision model, on the same
Qwen3.8-27B backbone. Two things changed: the request format and the training data.

**Joint request format.** v1.1 answered one question per forward pass, reading out the last token. This model reads a
whole request in **one sequence**: the state, then every question. Each question gets its own readout, at a marker
token placed right after that question's options. As a result, answering several questions about the same state costs
about as much as answering one, and the questions can inform each other (see
[When to group questions](#when-to-group-questions)).

**Training data.** We also reworked the data substantially. Part of that work brings the model in domain for some
Decision Index tasks: several benchmarks ship official training splits, and models that train on them gain markedly on
those benchmarks, so we now include these splits (decontaminated against the test sets) to make comparisons on the
board fair. We did not optimize for that alone. We added a large amount of other decision data, tracked every
benchmark for regressions as we went, and measured progress outside the Decision Index as well: on decision tasks
held out from all training and on independent decision benchmarks, the model improves over v1.1.

This checkpoint handles both text and images (up to 1.6 MP). It combines several training runs through model souping
(weight averaging), chosen as the best compromise across all our evaluations rather than on any single benchmark.

## Evaluation

| Decision Index 0.3 (public) | pplx-decider-v1.1-27b | pplx-decider-v1.2, joint requests | pplx-decider-v1.2, one question per request |
|---|---:|---:|---:|
| Knowledge | 51.8 | **56.3** | 55.3 |
| Language | 67.5 | **72.8** | 71.9 |
| Retrieval | 61.2 | **68.4** | 68.1 |
| Tools | 79.1 | 84.4 | **85.4** |
| Arts | 47.3 | **56.2** | **56.2** |
| **Overall Decision Index** | 62.30 | **68.09** | 67.75 |

The overall score uses the suite's weighting, not a simple category average. We report two ways of sending the
suite's requests. **Joint requests:** all of a request's questions share one sequence (a request is split only when it
exceeds the length limit, see [Limits](#limits)). **One question per request:** every question is sent alone with its
state, as v1.1 always does. The two differ only on the 9 benchmarks whose requests carry several questions: grouping
helps when the questions are facets of one decision and hurts when they are competing candidates (see
[When to group questions](#when-to-group-questions)). On the other 28 benchmarks the scores are the same.

| Vision Decision Index 0.3 (public, images up to 1.6 MP) | pplx-decider-v1.1-27b | pplx-decider-v1.2 |
|---|---:|---:|
| **Overall** | 73.22 | **77.43** |

## Usage

Requirements: Python 3.12+ and a CUDA GPU with room for about 52 GiB of BF16 weights plus working memory.
The repository is private: authenticate with a Hugging Face token that has access to it.
Download the repository and install `requirements.txt`. That file pins torch, transformers, safetensors, pillow,
torchvision and huggingface-hub. The [fast path](#fast-path) also needs `requirements-fast.txt`.

```python
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

checkpoint = Path(snapshot_download("perplexity-ai/pplx-decider-v1.2"))
sys.path.insert(0, str(checkpoint / "source" / "src"))
from pplx_decider import Decider

decider = Decider.from_pretrained(checkpoint, device="cuda")
response = decider.decide({
    "state": "My integration keeps failing with a 401 since we rotated our API key. Please help.",
    "questions": {
        "team": {
            "type": "choice",
            "instructions": "Which team should handle this request?",
            "criteria": {
                "billing": "Charges and refunds",
                "support": "Technical integration errors",
                "sales": "Questions about buying a product",
            },
        },
        "urgent": {"type": "noul", "instructions": "Is the customer blocked right now?"},
        "frustration": {"type": "score", "criteria": ["calm", "mildly annoyed", "frustrated", "angry"]},
    },
})
print(response["answers"]["team"]["choice"], response["answers"]["urgent"]["noul"])
```

`decide` accepts one request and returns one response. Given a list of requests, it returns a list of responses in
the same order. The source can also be installed as a package: `pip install ./source` (or
`pip install "./source[fast]"`).

### Request schema

```python
{
  "state": str | dict | list,            # the context to classify; non-strings are serialized as JSON
  "questions": {                         # 1 or more questions, answered from the same state
    "<id>": {
      "type": "choice" | "noul" | "score",
      "instructions": str | None,        # optional; default "Choose the best matching option."
      "criteria": ...,                   # see below
    },
  },
  "images": [path | "data:image/...;base64,..." | PIL.Image],   # optional
}
```

| Type | `criteria` | Answer |
|---|---|---|
| `choice` | `{option_name: description or None}`, 1 to 255 options | `choice`, `probabilities` (per option), `confidence` |
| `noul` | optional `{"true": description, "false": description}` | `noul` = P(true) |
| `score` | list of 2 to 255 level descriptions, lowest first | `score` (expected level index), `probabilities`, `legend`, `confidence` |

The options are shown to the model in the order you give them, under the answer codes `A`, `B`, ... Each response
looks like `{"answers": {"<id>": {...}}, "usage": {"input_tokens": int, "output_tokens": 0, "sequences": int}}`.
`input_tokens` counts every non-padding position the request used, including the template and image positions.
`sequences` is 1 unless the request had to be split. Requests that do not follow the schema raise
`pplx_decider.RequestError` before any computation.

`decider.logits(requests)` returns the raw readout logits of each question's valid options, before temperature.
For ranking, use the logit margin `true - false` of a `noul` question: unlike probabilities, it does not saturate
into ties.

## When to group questions

All questions in a request share one sequence. Full attention is noncausal, so every question attends to the state
and to every other question. This changes the answers. Grouping helps when the questions are **facets of one
decision**, and hurts when they are **independent candidates** competing for the same judgement:

| Task | Questions | Joint vs one question per request |
|---|---|---:|
| SATA-Bench (select all that apply) | one per option | **+11.3** |
| ACOS (aspect-category sentiment) | one per category | **+7.8** |
| PhishNChips | facets of one message | **+5.1** |
| BFCL (function calling) | one per candidate call | −1.1 |
| BRIGHT (reasoning-intensive retrieval) | one per candidate document | −2.9 |
| ToolRet (tool retrieval) | one per candidate tool | −4.8 |

(Decision Index task scores, points; the other Decision Index tasks have one question per request, so both modes
give the same score.)

**Reranking depends on whether the candidates are related.** BEIR, nDCG@10, 8 candidate documents per request
against one per request:

| Candidates | Datasets | 8 per request vs 1 per request |
|---|---|---:|
| related: comparing them is informative | HotpotQA (multi-hop) | **+2.1** |
| | CQADupStack, Quora (duplicate questions) | **+1.7**, +0.4 |
| independent passages | FiQA, NQ, MS MARCO, Climate-FEVER | −0.2 to −0.4 |
| | NFCorpus, SciFact, FEVER, DBpedia-Entity | −0.7 to −1.2 |
| similar candidates competing for the same judgement | ArguAna (counter-arguments), TREC-COVID | −2.8, −2.9 |
| **all 13 datasets (macro)** | | −0.5 |

Our recommendations:

- **Put related questions in one request**: several attributes of the same item, multi-label "select all that
  apply" decisions, or the steps of a routing decision. One request is also much cheaper than N separate ones.
- **Score independent candidates in separate requests** (for example one request per (query, document) pair, as in
  v1.1), or in small chunks if the cost matters more than the last point of accuracy. The fast path packs many
  small requests efficiently, so separate requests stay cheap. Group candidates only when comparing them helps
  (multi-hop evidence, duplicate detection). When in doubt, use one candidate per request: it is never more than
  about 0.4 points worse, while grouping can cost about 3.
- Question IDs are not shown to the model, but question order is (questions are numbered). Put the context the
  questions need in the state, not in another question.

## Temperature and calibration

`decision_config.json` stores the temperature fitted on held-out calibration data (1.382 for this
checkpoint). `decide` applies it exactly once, then normalizes a softmax over each question's valid options only.
`decide(..., temperature=t)` overrides it. When you use `logits` directly, divide by the saved temperature before the
softmax, and do not include the unused codes. It was fitted in the joint format, on data separate from
the development set. On the development set (1,497 questions) it gives accuracy
91.3%, ECE 0.014 and Brier 0.134 (without temperature: ECE 0.033, Brier 0.137). On decision datasets held out from
all training, probabilities remain somewhat over-confident (ECE about 0.05), as for every model we measured,
though less so than v1.1.

## Images

Images go in `images`. They are placed before the text of the request, and every question can see them. Each image is
resized (aspect ratio kept) to at most `max_pixels` pixels: **1,638,400 (1.6 MP)**, as saved in
`decision_config.json`. Smaller images keep their size (minimum 65,536 pixels). A 1.6 MP image uses about 1,600 sequence positions, so several large
images count toward the [length limit](#limits). Pass `max_pixels=` to `from_pretrained` to change the cap. The
checkpoint was trained and evaluated at its saved value.

## Fast path

`Decider.from_pretrained(..., fast=True)` concatenates whole requests into one padding-free sequence per forward
pass, with several readouts per request. The requests stay independent:

- full attention uses varlen FlashAttention restricted to each request;
- the linear-attention state and the short convolution restart at every request boundary;
- positions restart at 0 for each request, and image requests keep their own M-RoPE positions.

On top of packing, the default `FastOptions()` compiles whole decoder layers with `torch.compile`. It also pads each
pack to a static size bucket (2k, 4k, 8k, 16k or 32k tokens) with filler sequences and replays CUDA graphs. The last
layer is computed only at the marker positions.

Requirements: CUDA, `flash-linear-attention` (`requirements-fast.txt`), and torch ≥ 2.10 for
`torch.nn.attention.varlen`. The FlashAttention kernel ships with torch, so no `flash-attn` build is needed.

```python
from pplx_decider import Decider, FastOptions

decider = Decider.from_pretrained(checkpoint, fast=True)   # = FastOptions()
decider.warmup()                                         # compile every bucket now (about 1 minute)
responses = decider.decide(requests)                     # a list is packed and tokenized in a background thread

# throughput only (large batches): one static 32k shape, a single compilation
decider = Decider.from_pretrained(checkpoint, fast=FastOptions(buckets=(32768,)))
# no compilation at all (e.g. quick experiments): packing only
decider = Decider.from_pretrained(checkpoint, fast=FastOptions(compile=None, cuda_graphs=False))
```

The fast path returns the same results as the reference path up to BF16 noise. On 300 Decision Index requests
(2,324 questions), argmax agreement is 99.8% and mean |Δp| is 0.002. On BEIR reranking (40 queries × 100
candidates), the per-query Spearman correlation with the reference is 0.9988. That is the same size as the variation
of the reference path itself: batched vs one request per call gives 99.8% and mean |Δp| 0.0017, and two runs in
separate processes give mean |Δp| 0.0005. The default path (`fast=False`) runs the unmodified Transformers model on
left-padded batches. With one request per call, it reproduces the evaluated implementation to within 3e-7.

Throughput on one GB200 (bf16, requests/s; ratios against the reference path):

| Path | Decision Index requests | Reranking requests | Vision requests (1.6 MP) |
|---|---:|---:|---:|
| Reference (padded, length-sorted batches) | 9.1 | 27.1 | 8.0 |
| Packing, no padding (`compile=None, cuda_graphs=False`) | 9.1 (1.00×) | 28.0 (1.03×) | |
| + compile norms/MLP/conv (`compile="sub"`) | 12.9 (1.42×) | 46.2 (1.71×) | |
| + whole-layer compile (`compile="layer"`) | 18.0 (1.99×) | 52.3 (1.93×) | 12.0 (1.50×) |
| + static 32k packs, CUDA graphs (`buckets=(32768,)`) | 20.9 (2.31×) | 55.5 (2.05×) | |
| + last-layer pruning | 21.2 (2.33×) | 56.0 (2.07×) | 15.3 (1.90×) |
| + FP8 matmuls (`fp8=True`, off by default) | 24.9 (2.74×) | 67.3 (2.49×) | |
| **Default `fast=True`** (buckets 2k to 32k, pruning) | 19.8 (2.18×) | 56.2 (2.08×) | 14.4 (1.79×) |

The Decision Index requests average 1,050 tokens and range from 1 to 64 questions. The reranking requests are
one (query, document) pair each, averaging 437 tokens. Packing alone barely helps, because the reference path
already sorts requests by length before batching. The gains come from compilation and CUDA graphs. The vision
encoder runs uncompiled, so image requests gain less.

**Latency.** Static 32k packs suit large batches, but a single small request still pays for a full 32k pack
(about 1.2 s). The default bucketed mode pads only to the next bucket. It answers a single Decision Index request in
96 ms (median), against 131 ms for the reference path, at about 93% of the static throughput. Use
`FastOptions(buckets=(32768,))` for offline throughput only.

**FP8** (`FastOptions(fp8=True)`) quantizes the decoder matmuls to rowwise-scaled float8. It is faster, but its
probabilities move away from the reference: argmax agreement 99.4%, mean |Δp| 0.006 (max 0.24), and reranking Spearman 0.995, against 99.8%, 0.002 and 0.9988 for the bf16 fast path. It also modifies the loaded model in place, so every
call on that `Decider` uses FP8. It is off by default. Validate it on your own task before using it.

## Limits

- **Options:** 1 to 255 per question (2 to 255 for `score`). The answer codes are single tokens, and the readout
  head has 255 rows.
- **Length:** `max_length` defaults to 262,144 tokens per sequence, the backbone's position limit. **Training used
  sequences up to about 32k tokens.** Longer requests still run as one sequence, but we have only spot-checked them:
  retrieving one fact from a long log works up to about 243k tokens (P(correct) above 0.999 at every depth tested),
  with peak GPU memory of about 95 GiB on the reference path and 107 GiB on the fast path, and 3 minutes (reference) or
  2 minutes (fast) per 243k-token request on one GB200. Validate beyond 32k on your own task, or pass
  `max_length=32768` to stay within the training range. When a request exceeds `max_length`, its questions are
  split in halves, recursively, and every chunk keeps the full state and images. A single question that does not fit raises `pplx_decider.LengthError`
  before anything runs. Inputs are never truncated. `usage.sequences` reports the number of chunks. A split request
  is no longer fully joint, so prefer shorter states.
- **Questions per request:** no fixed cap. The length limit is the only constraint.
- **Batching:** the reference path groups requests into left-padded batches of at most `batch_tokens` padded tokens
  (default 32,768). The fast path packs up to 32,768 tokens per forward pass.

## Checkpoint format and serving

This is the native decision-checkpoint layout: a `Qwen3_5Model` backbone plus `readout.safetensors`, a BF16
`[255, 5120]` decision head. The Transformers class name does not change the base model identity, Qwen3.8-27B.
`joint_config.json` declares the request protocol (`version: 3`, `joint-question-inline-readout-v1`, marker
`<|fim_suffix|>`).

- Full-attention layers are **noncausal** over the whole request. The linear-attention layers keep their native
  causal behavior. Default causal inference does not reproduce this checkpoint.
- The readout is applied at each `<|fim_suffix|>` marker, one per question, not at the last token. Literal special
  tokens in user content are neutralized before tokenization, so user text cannot create markers.
- This artifact has a separate readout, **not a full-vocabulary `lm_head`**. A serving system needs both the
  noncausal attention and the per-marker readout. Readout row `i` corresponds to vocabulary row
  `decision_config.json["token_ids"][i]`.

`release-manifest.json` records file checksums.

## Troubleshooting

- **`ImportError: ... flash-linear-attention`**: install `requirements-fast.txt`, or use `fast=False`.
- **Slow first call with `fast=True`**: `torch.compile` and CUDA-graph capture happen on first use of each bucket.
  Call `decider.warmup()` at startup. Pass `buckets=(32768,)` for a single shape, or `compile=None` to skip compiling.
- **Probabilities differ slightly between paths or batch compositions**: expected in BF16
  (mean |Δp| about 0.002, with rare argmax flips on near-ties). Use `fast=False` and one request per call for bit-stable results.
- **`LengthError`**: one question with the state and images exceeds `max_length`. Shorten the state, lower
  `max_pixels`, or raise `max_length` up to the backbone's 262,144 (beyond about 32k tokens, the training length,
  the probabilities are less validated).
- **Questions influence each other**: by design, see [When to group questions](#when-to-group-questions). Use one
  request per question for fully independent answers.
- **Out of memory**: lower `batch_tokens` (reference path) or use smaller buckets / `token_budget` (fast path).
- **Different answers from v1.1-style prompts**: this model expects the joint format built by `pplx_decider`. Do not
  reuse the v1.1 single-question prompt.

## Acknowledgment

A large part of the gains are thanks to the [tasksource](https://github.com/sileod/tasksource) data. If you also use
this data, consider citing the corresponding article

```bibtex
@inproceedings{sileo-2024-tasksource,
    title = "tasksource: A Large Collection of {NLP} tasks with a Structured Dataset Preprocessing Framework",
    author = "Sileo, Damien",
    booktitle = "Proceedings of the 2024 Joint International Conference on Computational Linguistics, Language Resources and Evaluation (LREC-COLING 2024)",
    month = may,
    year = "2024",
    address = "Torino, Italia",
    publisher = "ELRA and ICCL",
    url = "https://aclanthology.org/2024.lrec-main.1361",
    pages = "15655--15684",
}
```
