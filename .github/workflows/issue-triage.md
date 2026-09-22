---
description: |
  Triages new otterdog issues: classification, duplicate detection,
  type labels, and a summary comment for maintainers.

on:
  issues:
    types: [opened, reopened]
  workflow_dispatch:
    inputs:
      issue_number:
        description: 'Existing issue number to triage'
        required: true
        type: string
  reaction: eyes

concurrency:
  job-discriminator: ${{ github.event.inputs.issue_number || github.event.issue.number }}

permissions:
  contents: read
  issues: read
  copilot-requests: write

safe-outputs:
  add-labels:
    allowed:
      - bug
      - enhancement
      - question
      - duplicate
      - invalid
      - documentation
      - help wanted
      - good first issue
      - task
      - python
      - javascript
      - github_actions
      - dependencies
    max: 3
  add-comment:
    max: 1

engine: copilot

timeout-minutes: 10
---

Analyze the otterdog issue. If this run was triggered manually (workflow_dispatch), the issue
to analyze is number `${{ github.event.inputs.issue_number }}`, not necessarily the one in the
event payload.

1. Read the title/body, and the repo's available labels.
2. Search for similar/recent issues to detect a duplicate.
3. Classify the type (bug/enhancement/question/task) and apply at most 2 relevant labels
   (plus `documentation`, `python`, `javascript`, `github_actions`, `dependencies` when the
   affected technical area is identifiable).
4. If the issue is clearly a duplicate, apply `duplicate` and cite the original issue number(s).
5. Post a short comment: summary, label(s) applied, and potential duplicates if any.
