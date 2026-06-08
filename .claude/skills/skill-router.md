# skill-router

You are a skill dispatcher. Your job: given what the user wants to accomplish, identify the right skill(s), explain what each does, and tell them exactly how to invoke them — in the right order.

## When to use

Run this at the start of any session when you are unsure which skill fits, or want to make sure you are using the best tool for the job.

## Instructions

1. Ask the user: **"What do you want to accomplish in this session?"** (if they haven't already said)
2. Analyse their goal and match it to one or more skills from the catalogue below.
3. Output a short recommendation block:

```
## Recommended skill(s)

1. /skill-name — one sentence on why this fits right now
   → invoke with: /skill-name

2. /skill-name — (if a second step is needed)
   → invoke with: /skill-name
```

4. If multiple skills chain together naturally (e.g. plan → break down → build), show them as a numbered sequence with a brief "then" between each step.
5. If the goal is unclear, ask one clarifying question before recommending.
6. Never recommend more than 3 skills per session. Force-rank if needed.

---

## Skill catalogue

### Planning & requirements
| Skill | Use when |
|---|---|
| `/grill-me` | You have a rough idea and need to stress-test it before touching code |
| `/grill-with-docs` | Same as grill-me, but you want decisions reflected in CONTEXT.md / ADRs |
| `/to-prd` | You want to turn a goal into a written Product Requirements Document |
| `/to-issues` | You have a plan or PRD and want it broken into GitHub issues |
| `/prototype` | You want to explore options before committing — UI mockup or logic spike |

### Engineering quality
| Skill | Use when |
|---|---|
| `/tdd` | You are about to write a new module and want to do it test-first |
| `/improve-codebase-architecture` | The codebase feels tangled; you want ranked refactor opportunities |
| `/request-refactor-plan` | You know one area needs a refactor and want a safe, step-by-step plan |
| `/design-an-interface` | You need to design an API or module boundary before implementing |
| `/ubiquitous-language` | Names and terms are inconsistent across the codebase |
| `/setup-pre-commit` | You want automated quality gates before every commit |
| `/git-guardrails-claude-code` | You want Claude blocked from running destructive git commands |

### Diagnosis & review
| Skill | Use when |
|---|---|
| `/diagnose` | Something is broken or regressed and you need root-cause analysis |
| `/zoom-out` | You are deep in a rabbit hole and need perspective on the bigger picture |
| `/triage` | You have a backlog of issues and need to prioritise |
| `/review` | You want a code review of current changes |
| `/qa` | You want a quality-assurance pass before shipping |

### Writing & docs
| Skill | Use when |
|---|---|
| `/edit-article` | You have a draft article that needs tightening |
| `/writing-shape` | You want to plan the structure of a piece before writing it |
| `/writing-beats` | You have a structure and want to flesh out the key beats |
| `/writing-fragments` | You have fragments/notes and want to weave them into a draft |
| `/scaffold-exercises` | You want to turn content into exercises or a workshop |

### Session management
| Skill | Use when |
|---|---|
| `/handoff` | You are ending a session and want to preserve context for the next one |
| `/caveman` | You want ultra-compressed, token-efficient responses |
| `/write-a-skill` | You want to create a new custom skill |

---

## Common chains

**"I have a vague idea and want to ship it properly"**
`/grill-me` → `/to-prd` → `/to-issues`

**"I want to build a new feature test-first"**
`/grill-me` → `/design-an-interface` → `/tdd`

**"The codebase is a mess and I want to clean it up"**
`/zoom-out` → `/improve-codebase-architecture` → `/request-refactor-plan`

**"I want to write and publish an article"**
`/writing-shape` → `/writing-beats` → `/edit-article`

**"Something is broken and I don't know why"**
`/diagnose` → `/tdd` (add regression test after fix)
