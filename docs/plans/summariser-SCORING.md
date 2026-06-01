# Summariser scoring — reading the R/B/F scorecard, and locating "good vs great"

> Companion to the [G10 benchmark](./summariser-G10.md) / [CR1](./summariser-CR1.md). It explains
> what each automated score *is*, how each can be gamed and what balances it, why the absolute
> numbers look low, and — the real question — **how to turn an uninterpretable `0.12` into a
> position on the bad→good→great spectrum.**

## 0. The one thing to internalise

We do **not** score against a gold *summary* (we rejected fabricated gold). We score each generated
summary against the **full real source text it distilled**. ROUGE/BLEU/F1 were designed to compare
two texts of *similar length and intent* — a candidate summary vs a reference summary. Using them
against the **whole source** changes what the numbers mean and **caps them far below the 0.7–0.8
you'd expect** for a same-length reference. So the raw value is a **relative screen**, not an
absolute grade. (For calibration: even against a real gold summary, SOTA *abstractive* ROUGE-L on
CNN/DailyMail is ~0.40, not 0.7+.)

## 1. The three metrics — what each captures, its failure mode, how it's gamed, what balances it

| Metric | Captures | Structural failure mode | Gamed by… | …caught by |
|--------|----------|-------------------------|-----------|-----------|
| **ROUGE-L** (LCS, f-measure) | Longest common *subsequence* — overlap that respects ordering (reads as fluency/structure). | f-measure is **recall-dominated**: recall = LCS / len(**source**). Source is 10–50× the summary, so recall (and thus f) is tiny **by construction** — a high score would mean the "summary" is nearly source-length. | **Copying long verbatim spans** from the source. | **BLEU** doesn't rise much from one long span (n-gram precision saturates); **compression ratio** exposes a copy (ratio → 1 = no summarisation). |
| **BLEU** (n-gram precision + brevity penalty) | How much of the summary's **wording is present in the source** → a grounding / anti-hallucination signal. | **Penalises good abstraction**: a faithful *paraphrase* uses words not literally in the source → low BLEU even when the summary is excellent. Brittle to exact n-grams. | **Extracting verbatim phrases** (parroting). | **ROUGE-L recall** stays low if you only parrot a few phrases; **compression** + **embedding cosine** catch parroting that ignores the rest. |
| **F1** (token-set overlap) | Bag-of-words **content coverage** — did the summary mention the right things, order-agnostic. | **Ignores order and structure**; rewards keyword presence over coherent prose. | **Keyword stuffing** (dump salient source nouns). | **ROUGE-L** (needs ordered overlap, not a word bag); **compression** (a keyword dump is long & unreadable); **embedding cosine** + human review (coherence). |

**The scorecard logic (why three, not one):** the three metrics pull in different directions, so a
summary that *games* one is exposed by another. A verbatim copy spikes ROUGE-L but the **compression
ratio** betrays it. A paraphrase tanks BLEU but holds F1/ROUGE-L. Keyword-stuffing lifts F1 but not
ROUGE-L. **No single cheap trick wins all three plus compression** — which is exactly why we read
them *together* as a vector, never one in isolation. The current data shows this working: reground's
BLEU (~0.05) is 4× strict's (~0.013) — it stays closer to source wording — while ROUGE-L/F1 move
less, i.e. reground trades a little fluency-overlap for materially more grounding.

## 2. The missing number — compression ratio (and the theoretical ceiling)

Your intuition is correct and it's the key to interpretation. Define:

```
compression_ratio = len(summary_tokens) / len(source_tokens)      # e.g. 0.04 = summary is 4% of source
```

Because recall-based overlap can cover **at most** the fraction of the source you actually include,
the compression ratio is (approximately) the **theoretical ceiling on ROUGE-L recall** — and thus on
its f-measure. So a raw `ROUGE-L = 0.12` at `compression_ratio = 0.15` is using **~80% of its
achievable headroom**, which is *strong*; the same `0.12` at ratio `0.5` would be weak. We will emit:

```
rouge_l_normalised = rouge_l / theoretical_ceiling(compression_ratio)   # "% of achievable"
```

This converts the uninterpretable absolute into a **fraction of what is even possible at this
compression level** — the first real step toward "are we good?".

## 3. Locating "good vs great" — anchoring the spectrum

A single number is meaningless without **anchors** that bracket the band. We add three reference
points, scored by the *same* function against the *same* source, so our summaries can be placed:

1. **Floor — `random`/`boilerplate`**: a length-matched random slice of source words (or a fixed
   generic sentence). Anything that can't beat this is noise.
2. **Baseline — `lead-N`**: the first *N* characters of the source (the classic extractive "lead"
   baseline). **Beating lead is the bar for "the model is doing real work."** Lead is a famously
   *hard* baseline for news; for dev sessions it should be weaker, so we should clear it comfortably.
3. **Ceiling — `oracle-extractive`**: a greedy, ROUGE-maximising extract of the same length — the
   **best score any extractive summary of this budget could achieve** against this source. This is
   the realistic top of the band given the compression level.

Our position on **[lead → oracle]** is the answer to your question:

| Where the model lands | Reading |
|---|---|
| ≤ lead | below median — not doing real distillation |
| between lead and the midpoint | **fair** |
| above the midpoint, approaching oracle | **good** |
| at/above oracle (only possible via *abstraction* the lexical metric can't see) | **great** — and the lexical score is now actively *underselling* it (go to §4) |

## 4. The honest ceiling of lexical scoring — and what to add

Every metric in §1 is **lexical** (surface overlap). The research is blunt: these correlate poorly
with human judgement for open-ended generation, *because* a great abstractive summary deliberately
*diverges* in surface form. So past the oracle band, lexical scores stop discriminating "good" from
"great." To answer "good or great?" defensibly we should add, in priority order:

| Method | Reference-free? | Interpretable 0–1? | Cost / catch | Verdict |
|--------|:---:|:---:|--------------|---------|
| **Compression-normalised R/B/F + lead/oracle anchors** (§2–3) | ✅ | ✅ (% of achievable) | trivial, deterministic | **Add now** — turns our existing numbers into a located score |
| **Embedding cosine** (summary vs source) | ✅ | ✅ | cheap; we already have local embedders (`muninn_embed`, `nomic-embed`, `bge-large`) | **Add** — captures paraphrase grounding that BLEU misses |
| **NLI faithfulness** (SummaC-style: is each summary claim entailed by source?) | ✅ | ✅ (proportion) | needs an NLI model; targets hallucination specifically | Consider — strong on factuality |
| **LLM-as-classifier — BINARY only** (is this summary faithful to the source? yes/no; or A-vs-B preference) | ✅ | ✅ as a *proportion* (% faithful) | judge-model dependency + bias | Optional, coarse pre-screen of the human gate |
| ~~LLM-as-judge numeric scale (1–5)~~ | — | ✗ | — | **Rejected** — see note below |
| Gold reference summaries | ❌ | ✅ | reintroduces the fabricated-gold problem | Rejected (no honest gold) |

> **A numeric LLM-judge scale (1–5) is rejected — it is not evidence-based.** LLM Likert ratings are
> poorly calibrated, have low inter-rater reliability, and show scale/position biases: a "3.7/5"
> implies an interval scale the model never grounds, so it is pseudo-quantitative, not a measurement.
> The only honest LLM-judge use is **binary classification** (faithful / not-faithful, or pairwise
> A-vs-B), which the model *can* decide and which aggregates to a real proportion. Even then it is a
> coarse pre-screen — the binding decision is the human gate (T10.7), which is itself binary
> (PROCEED / ABANDON).

Researched sources: OpenAI summarization-eval cookbook; QuestEval (arXiv 2103.12693); contrastive
reference-free quality (arXiv 2010.01781); reference-quality/ref-free study (arXiv 2410.10867); AWS
LLM-summarisation-eval guide.

## 5. The recommended scorecard (what a row should report)

For each summary, emit the **vector**, not a single number:

```
lexical:     rouge_l, bleu, f1                      (relative screen)
context:     compression_ratio, rouge_l_normalised  (% of achievable)
anchors:     lead_combined, oracle_combined         (the band this row sits in)
semantic:    embed_cosine                           (paraphrase-aware grounding)
faithful?:   binary faithful/not (→ % faithful)     (optional, coarse — NOT a 1–5 scale)
speed:       seconds
```

Then "are we good or great?" reads off three things at once: **(a)** above lead and how close to
oracle (band position), **(b)** high embed-cosine with *low* BLEU = strong *abstractive* grounding
(the best outcome the lexical metrics hide), **(c)** the human taste verdict (T10.7) — a binary
PROCEED/ABANDON, optionally pre-screened by a binary faithfulness classifier, never a fabricated
numeric judge score. Any one metric alone is gameable or misleading; the **vector** is not.

## 6. Plan

This methodology is tracked as **[CR4](./summariser-CR4.md)** (scoring scorecard + calibration):
implement compression ratio + normalisation, the lead/oracle anchors, and embedding cosine —
optionally a *binary* faithfulness classifier, never a numeric judge scale — then re-run the
4-project last-week matrix across the expanded model panel so every strategy×model row carries the
full, *located* scorecard instead of a bare lexical triple.
