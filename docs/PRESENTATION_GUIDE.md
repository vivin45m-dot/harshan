# How to present FoodTrace

Written for an audience that wants plain answers, not buzzwords. Read it out loud
a couple of times; don't memorise it word for word.

---

## 1. The one sentence to open with

> "Every company that buys food has to guess how much will arrive next month. Normal
> forecasting software gives one number and never says when that number is a bad guess.
> My project gives the number **and** tells you whether to trust it, using real
> government data."

Say this first, before any slide with a diagram. Review 1 went badly because the panel
didn't know what problem was being solved. Give them the problem in the first 30 seconds,
and nothing technical yet.

---

## 2. Explain the problem with an everyday example

**The weather forecast.**

> "If the weather app says 'it will rain tomorrow', that's one kind of forecast. If it
> says '70% chance of rain', that's more useful, because you know how sure it is. Food
> companies today get the first kind. They get '4,000 tonnes of lettuce next month',
> with no idea if that's a solid number or a wild guess."

Then say why it matters:

> "The guess is usually worst exactly when it matters most: when there's a recall or a
> food-poisoning outbreak. A plain forecast looks just as confident then as on a normal
> day. People plan stock, money and loans on a number that may be wrong."

---

## 3. The two kinds of "not sure" (the heart of the project)

This is the idea the panel must take away. Use the doctor example:

> "A doctor can be unsure for two different reasons.
> **One:** flu season is just unpredictable; some years are bad, some aren't. That's
> nobody's fault; it's natural variation.
> **Two:** the doctor has never seen this patient's condition before. Here the honest
> answer is 'I need more information'."

Map it to the project:

| Doctor | My project | What the user should do |
|---|---|---|
| Flu season varies | **Aleatoric** uncertainty: demand for this food naturally goes up and down | Keep some extra stock |
| Never seen this case | **Epistemic** uncertainty: the model hasn't seen enough data like this | Don't trust the number; check the supplier |

> "Normal forecasting mixes these two together, or ignores both. My model separates them,
> in one step, for every food, every month."

On the dashboard this becomes three simple labels: **Reliable**, **Volatile**,
**Unreliable**.

---

## 4. What I actually did (say it as five plain steps)

Keep each step to one or two sentences.

1. **Collected real data from three government sources.**
   - US food imports every month, January 2016 to July 2026, from the United Nations.
   - Every FDA food recall.
   - Every CDC food-poisoning outbreak.

   Nothing is made up.
2. **Connected them.** Each "supply node" is one food from one country, such as "lettuce from
   Mexico". That gives 73 nodes: 23 foods from 30 countries. Each recall and outbreak is linked
   to the food it concerns.
3. **Built a tamper-proof record (the blockchain part).** Every import figure, recall and
   outbreak is locked into a chain of blocks, one block per month. If anyone changes even one
   number later, the system catches it and shows exactly which month was changed.
4. **Built and trained the forecasting model.** It predicts next month's imports and tells
   you both kinds of uncertainty. I compared it against five other methods, including
   the standard statistical one (SARIMA) and the usual deep-learning way of getting
   uncertainty (MC-dropout).
5. **Tested two questions scientifically.**
   - **Question 1:** do suppliers with better paperwork get more reliable forecasts?
   - **Question 2:** does the model get "nervous" before a recall happens?

The dashboard is where you **see** all of this. It comes last.

---

## 5. "Isn't this just a dashboard?" (answer it before they ask)

Bring this up yourself, right after step 5. Use the car example:

> "A car's dashboard shows speed and fuel. But nobody says a car *is* its dashboard;
> the engine is what does the work. My dashboard is the same: it's the window. The work
> is underneath it."

Then list what is underneath. Point to these on a slide:

| Part | What it does | Can a dashboard do this? |
|---|---|---|
| **Data pipeline** | Downloads 3 government datasets, cleans them, links recalls to foods, checks each recall record against the FDA's own traceability rule (5 checks) | No |
| **Machine-learning model** | A neural network I trained myself that outputs a forecast **plus** two kinds of uncertainty | No |
| **Five comparison models** | Proves my model is actually better, not just different | No |
| **Blockchain ledger** | 127 blocks and about 11,500 real records, each block locked with a hash; any edit is detected | No |
| **Scientific testing** | Accuracy scores, calibration checks, and statistical tests with p-values | No |
| **20 automated tests** | Check that the chain catches tampering, that the maths is right, that the API returns valid forecasts | No |
| **Dashboard** | Shows all of the above to a non-technical user | This is the only "dashboard" part |

Closing line for this section:

> "If you removed the dashboard, the project would still produce forecasts, still catch
> tampering, and still give the same results; you'd just read them as numbers instead of
> charts. If you removed everything else, the dashboard would be empty."

**Prove it live (30 seconds, very convincing):** open a terminal and run the tests:

```bash
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

"20 passed" appears. Then open `artifacts\results.json` and show that the numbers on the
dashboard come straight from that file. That shows the dashboard is only displaying
results the rest of the system produced.

---

## 6. The results: say them simply and honestly

| Plain-language claim | The number behind it |
|---|---|
| "My model was the most accurate of the six methods." | Error score (MASE) 0.773; lower is better, and anything under 1 beats the simple "same as last year" guess |
| "When my model says '90% sure', it's right about 90% of the time. The others claimed 90% but were right less often." | Mine 91.8%, MC-dropout 87.6%, SARIMA 83.5% |
| "Better paperwork did **not** make forecasts more reliable." | p = 0.48 (no real difference) |
| "The model's doubt did go up before recalls, a bit more often than not." | Higher before 57% of 245 recalls, p = 0.010; sensitive to how recalls are matched |

**The 90% example is your strongest point.** Explain it like this:

> "If a weather app says '90% chance of rain' a hundred times, it should rain about 90 of
> those times. If it only rains 80 times, the app is overconfident. My model's 90% was
> right 91.8% of the time: honest. The standard statistical method's 90% was right only
> 83.5% of the time: overconfident."

**If a result didn't work out, say so plainly.** Old-school examiners respect this:

> "Question 1 came out negative: better paperwork didn't mean better forecasts. I'm
> reporting that rather than hiding it, because a negative result is still a result. It
> tells companies that filling in forms isn't enough; traceability needs richer data to
> show value."

---

## 7. Live demo (3 minutes, practise this exact path)

1. **Supply map.** "Each dot is one food from one country. Green means the forecast can be
   trusted, orange means demand is naturally jumpy, red means don't trust it."
2. **Click a red dot,** then click again to open it.
   - "Here's the forecast with its range. The red dashed lines are real FDA recalls."
   - "This lower chart is the model's doubt over time."
3. **Evaluation page.** Point only at the accuracy table and the calibration chart (the
   "90% means 90%" idea). Skip the rest unless asked.
4. **Ledger page.** This is the moment people remember.
   - Say: "Watch: I'll secretly change one recall record."
   - Click **Tamper**. The banner turns red: "Chain broken, block #126".
   - Say: "It caught it immediately and tells me exactly which month."
   - Click **Restore**.

Before the demo, start the app with `run.ps1` and open the map once, so it has loaded.

---

## 8. Questions they are likely to ask, with short answers

**"Where is the blockchain? Is it real?"**
> "Yes, it's a working blockchain I built: real SHA-256 hashing and proof of work, the same
> basic method Bitcoin uses, storing real records. It isn't connected to a public network
> like Bitcoin, because the goal is tamper detection for one organisation's records, not a
> currency."

**"Is the data real?"**
> "All of it. UN Comtrade for imports, the FDA's openFDA service for recalls, the CDC for
> outbreaks. Anyone can download the same data with my scripts and get the same results."

**"Why imports and not shop sales?"**
> "Store-level sales data for named food products isn't public. The well-known Walmart
> dataset hides product names, so you can't link it to recalls. US imports are public,
> named by food and by country, and they line up with FDA recalls."

**"Why does the data start in 2016?"**
> "The UN only publishes import weights in kilograms from 2016. Before that there are only
> dollar values, and dollars would mix price changes into demand."

**"What is new here?"**
> "Three things together: forecasts that separate the two kinds of doubt in one step,
> tested on real food data with recalls; a tamper-proof record of every input; and an
> actual measured test of whether traceability improves reliability. Earlier work does
> these separately, or only argues for them without measuring."

**"What does 'verified' mean if companies don't publish blockchain data?"**
> "I used the FDA's own traceability rule, FSMA 204. It lists the details a food record
> must contain: lot code, date, quantity, where it was shipped, and the company's address.
> A recall record with all five counts as verified. Only 13.5% of real recall records had
> all five."

**"Why is your model better than SARIMA?"**
> "Slightly more accurate (0.773 against 0.794), but the real difference is honesty: its
> uncertainty ranges are correct, SARIMA's are too narrow. SARIMA is overconfident."

**"Who would use this?"**
> "A food importer planning stock, a food-safety team watching for trouble, a bank deciding
> whether to lend to a supplier. Each needs to know when not to trust a number."

**"What would you do next?"**
> "Get real supplier-level traceability data, which would give Question 1 a fairer test.
> Also check the recall matching by hand, and turn the 'doubt' score into a risk price
> for lenders."

---

## 9. Words to avoid, and what to say instead

| Instead of… | Say… |
|---|---|
| "Normal-Inverse-Gamma distribution" | "the model outputs four numbers that describe how sure it is" |
| "epistemic / aleatoric" (on their own) | "the model doesn't know" / "demand is naturally jumpy". Use the technical word only after the plain one |
| "Merkle root, nonce" | "a fingerprint of the month's records, locked into the chain" |
| "MASE" | "an error score where anything under 1 beats the simple guess" |
| "p-value" | "the chance this is just luck; under 0.05 means probably not luck" |
| "leverages, robust, state-of-the-art" | leave them out |

---

## 10. Suggested running order (12–15 minutes)

| Minutes | What |
|---|---|
| 0–1 | The one-sentence problem (section 1) and the weather example (section 2) |
| 1–3 | Two kinds of "not sure" (section 3) |
| 3–6 | Five steps of what you did (section 4) |
| 6–8 | "Not just a dashboard" table, plus the 30-second test run (section 5) |
| 8–11 | Results, said simply and honestly (section 6) |
| 11–14 | Live demo, ending on the tamper moment (section 7) |
| 14–15 | Limitations and future work, then thank them |

Finish on this line:

> "So the project doesn't just predict demand. It tells you when the prediction can't be
> trusted, and it can prove that the data behind it hasn't been changed."
