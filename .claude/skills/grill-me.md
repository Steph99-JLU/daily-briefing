# grill-me

Grill the user with targeted questions — one at a time — until every assumption and edge case is on the table. Only then summarize the plan and build.

## When to use

Invoke this skill before implementing any non-trivial feature, change, or task. Especially useful when the request is vague, ambiguous, or touches multiple systems.

## Instructions

When this skill is invoked:

1. Ask the user to briefly describe what they want to build or change (if they haven't already).
2. Work through the decision tree **one question per round**. Do not ask multiple questions at once.
3. Cover these areas in order, skipping any that are clearly irrelevant:
   - **What exactly** should it do? (core behavior, inputs, outputs)
   - **Who** uses it, and how? (user types, entry points, UI vs. API vs. CLI)
   - **Where** does it live? (new file, existing module, new service?)
   - **Data** — what does it read, write, or transform?
   - **Edge cases** — what are the boundary conditions? Empty input? Large input?
   - **Error handling** — what happens when something goes wrong?
   - **Dependencies** — does it rely on external services, libraries, or other parts of the codebase?
   - **Tests** — does it need unit tests, integration tests, or none?
   - **Non-goals** — what is explicitly out of scope?
4. After each answer, decide: is there still an open assumption that could lead to the wrong implementation? If yes, ask the next question. If no, move on.
5. Once all critical questions are answered, output a **structured plan**:

```
## Plan

**Goal:** <one sentence>

**Approach:**
- <step 1>
- <step 2>
- ...

**Edge cases handled:**
- <case 1>
- <case 2>

**Out of scope:**
- <item 1>

**Files to change:**
- <file> — <reason>
```

6. After presenting the plan, ask: "Does this match what you had in mind, or should we adjust anything?"
7. Only start writing code once the user confirms the plan.

## Rules

- One question per message. Never fire a list of questions.
- Stay neutral — do not suggest answers in the question itself.
- If the user's answer reveals a new open question, ask it before moving on.
- If the user says "just do it" or "skip the questions", acknowledge briefly and proceed to planning with your best assumptions, stating them explicitly in the plan.
- The plan comes before the first line of code. Always.
