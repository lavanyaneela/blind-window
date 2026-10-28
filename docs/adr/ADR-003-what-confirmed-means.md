# ADR-003: what "confirmed" means, and why monitoring needs its own operating point

Status: accepted

## Context

Every headline in this repository moves when the operating point moves, so the
operating point is a decision, not a default. "Confirmed" here means: a
one-sided two-sample comparison of accuracy proportions, baseline window
against post-onset window, rejects at alpha 0.05, and the tool only agrees to
run that test on a day when its power against the operator's target drop
reaches 0.80.

## Decision

Three parts, each with its reason.

**Unpaired, two-sample, by construction.** The baseline and the post-onset
windows score different requests. This is the opposite of a fixed evaluation
suite (which scores the same cases before and after and is a paired design);
treating this stream as paired would be wrong in the flattering direction.
The pooled-variance one-sided z test is the standard arithmetic for exactly
this shape, and the suite pins its behaviour on constructed streams where the
truth is known.

**Power gates the right to answer, alpha gates the answer.** The refusal (exit
code 2) fires when the minimum detectable drop at the asked day exceeds the
target drop. Without that gate, a day-one "no regression at alpha 0.05" is
vacuously true against any realistic drop and reads as an acquittal. The gate
is what makes exit code 1 mean something: when the tool says no, it had the
power to say yes.

**A monitoring operating point is not an experiment operating point.** An A/B
test guards a one-shot decision, so it buys low alpha with a fixed horizon. A
monitor asks the same question every day for the life of the model: its real
false positive rate is per-question, compounding across days, and its miss cost
is measured in served predictions, not in a delayed launch. The defaults here
(alpha 0.05, power 0.80, one-sided toward harm) are therefore stated as
per-question rates in the report, both are flags, and the blind window is
recomputed from whatever the operator chooses. A team alarmed by daily
compounding should tighten alpha and watch the window stretch: on the default
stream the 2 point question is already not answerable **until day 50.5**, and
tightening moves that date outward. That trade is the point of printing it.

## Consequences

- The minimum detectable drop is solved by bisection from the normal
  approximation, with both samples recounted as labels mature. The suite
  asserts monotonicity in sample size and in alpha.
- Sequential-testing corrections (spending functions, always-valid inference)
  are deliberately out: they change the arithmetic of the gate, not the
  existence of the window, and they belong in the same future iteration as the
  rollback controller. The README's future work names them implicitly through
  the delay estimator; a reviewer who raises alpha spending is right, and the
  answer is that every correction makes the published windows longer, never
  shorter, so the committed numbers are a floor.
