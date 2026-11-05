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
  - decision-model
---

# pplx-decider-v1.1-27b

pplx-decider-v1.1-27b is an update of our
[pplx-decider-v1-27b](https://huggingface.co/perplexity-ai/pplx-decider-v1-27b)
model, that boost the [Decision Index](https://huggingface.co/spaces/multimodalart/jev-decision-index) score from 56.4 to 61.56, now outperforming Jev by more than 3.5 points, while using the same backbone. Most of the gains are driven by the lifting of the causal mask and training on more data, including data from [tasksource](https://github.com/sileod/tasksource).

## Evaluation

| Decision Index category | Jev | pplx-decider-v1-27b | pplx-decider-v1.1-27b |
|---|---:|---:|---:|
| Knowledge | **51.4** | 40.9 | 48.18 |
| Language | 62.0 | 63.5 | **69.45** |
| Retrieval | 55.4 | 54.9 | **61.26** |
| Tools | 75.1 | **79.3** | 78.88 |
| Arts | 37.7 | 39.4 | **44.66** |
| **Overall Decision Index** | 57.9 | 56.4 | **61.56** |


The overall score uses the suite's weighting, not a simple category average.


## Checkpoint format and serving

This is the **native decision-checkpoint layout**: a `Qwen3_5Model` backbone
plus `readout.safetensors` containing a BF16 `[255, 5120]` decision head.
The Transformers class name does not change the base model identity, Qwen3.8-27B.

Use the included inference implementation to preserve the evaluated behavior:

- Full-attention layers use the saved **noncausal** attention mode. The model's
  linear-attention layers retain their native behavior. Default causal inference
  does not reproduce this checkpoint's evaluated setup.
- The supplied `DecisionModel.predict` applies the saved calibration temperature.
  When using logits directly, apply it exactly once and normalize over the valid
  candidates for the current decision.
- This artifact has a separate readout, **not a full-vocabulary `lm_head`**.
  A serving system requiring `Qwen3_5ForConditionalGeneration` needs a separate
  export, mapping readout row `i` into vocabulary row
  `decision_config.json["token_ids"][i]`. Such an export must also preserve the
  attention behavior. If the frontend applies temperature, use the value above.

## Usage

Use Python 3.12+, authenticated Hugging Face access to this private repository,
and a CUDA GPU with room for roughly 49 GiB of weights plus working memory.
Download the repository and install its pinned `requirements.txt` dependencies.

```python
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

checkpoint = Path(snapshot_download("perplexity-ai/pplx-decider-v1.1-27b"))
sys.path.insert(0, str(checkpoint / "source" / "src"))
from autojev.model import DecisionModel, answer

model = DecisionModel(checkpoint, device="cuda")
question = {
    "type": "choice",
    "instructions": "Which team should handle this request?",
    "criteria": {
        "billing": "Charges and refunds",
        "support": "Technical integration errors",
        "sales": "Questions about buying a product",
    },
}
row = {"state": "My integration keeps failing. Please help.", "question": question}
probabilities = model.predict([row])[0]
print(answer(question, probabilities))
```

### Images

Pass images as file paths, PIL images, or `data:image/...;base64` URLs in
`row["images"]`. The processor resizes them **while preserving aspect ratio**.
Each side is rounded to a multiple of 32 px, and the total area is kept between
256×256 (65,536 px) and `max_image_pixels`. Each 32×32 patch costs one visual token,
so an image uses about `width * height / 1024` tokens.

`max_image_pixels` defaults to 2048×2048 (4,194,304 px, ≤4,096 tokens per image).
Larger images are downscaled automatically, so you don't need to resize them
yourself. To lower or raise the cap:

```python
model = DecisionModel(checkpoint, device="cuda", max_image_pixels=1600 * 1000)
```

Keep in mind:

- The text and all images of a decision must fit in `prepare`'s 8,192-token
  limit. Inputs are rejected rather than truncated. With several images per
  decision, lower `max_image_pixels` or downscale the images first.
- Training and the reported evaluation capped images at 512×512 (262,144 px,
  ≤256 tokens). Higher resolutions keep more detail but fall outside the training
  distribution, and they cost more memory and latency. To reproduce the evaluated
  setup exactly, use `max_image_pixels=512 * 512`.
- If you resize images yourself, scale both sides by the same factor
  `min(1, sqrt(max_image_pixels / (width * height)))` to keep the aspect ratio.

`source/src/autojev/model.py` is the evaluated training-run code, with one change:
the image-size cap is now the configurable `max_image_pixels`. It was previously
hardcoded at 512×512 pixels. `release-manifest.json` records file checksums and
checkpoint provenance.


## Acknowledgment
A large part of the gains are thanks to the [tasksource](https://github.com/sileod/tasksource) data. If you also use this data, consider citing the corresponding article

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

Our data pipeline also builds on [Bespoke Nimble](https://github.com/bespokelabsai/nimble)
by Bespoke Labs. The data pipeline of
[pplx-decider-v1-27b](https://huggingface.co/perplexity-ai/pplx-decider-v1-27b) was built
around human-labelled public datasets that we converted into Choice and Noul decisions
with Nimble's converters. v1.1 adds a lot of new data, so Nimble-converted data is now
only a small share of the training set. We also use Nimble's published benchmark subsets,
pinned by record ID and checksum, to keep those benchmark records and related examples
out of training. Nimble is downloaded at a pinned revision when the data is built and is
not redistributed here. If you use this part of the pipeline, please also cite Nimble:

```bibtex
@misc{nimble2026,
  author = {{Bespoke Labs} and Sathiamoorthy, Maheswaran},
  title = {Nimble},
  year = {2026},
  howpublished = {\url{https://github.com/bespokelabsai/nimble}},
  note = {Model: https://huggingface.co/bespokelabs/Bespoke-Nimble-9B}
}
```
