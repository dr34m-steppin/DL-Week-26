# Architecture

## Core loop

```text
Professor uploads course doc
  -> AI builds skill map + quiz bank
  -> Professor validates/approves (HITL gate)
  -> Student takes quiz
  -> Auto-grade + update mastery/risk/snapscore
  -> Student sees next actions + asks tutor
  -> Professor monitors risk and grading decisions
```

## Why this design

- Separates retrieval context from decision logic
- Keeps recommendations explainable via topic-level signals
- Keeps high-impact decisions under professor control
- Works in hackathon constraints while extendable to enterprise stack

## Mapping to judge criteria

- Actionable personalization: topic-specific next actions
- Explainability: citation + formulas + override notes
- Real-world viability: supports repeated loops over time
- HITL: required in 4 professor checkpoints
