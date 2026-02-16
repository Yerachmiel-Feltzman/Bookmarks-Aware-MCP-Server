---
name: project-board
description: Track project features and progress like a Jira board. Use when starting feature work, checking project status, or updating task progress. Always read the board before implementing features.
---

# Project Board - Task Tracking

This skill manages the project's feature board. The board lives in [board.md](board.md).

## Before Starting Work

**Always read [board.md](board.md) first** to understand:
- What's already done
- What's in progress (don't duplicate work)
- What's prioritized next

## Board Structure

Tasks are organized in columns by status:

| Status | Meaning |
|--------|---------|
| `done` | Completed and working |
| `in-progress` | Currently being worked on |
| `todo` | Ready to start, prioritized |
| `backlog` | Future work, not yet prioritized |

## Priority Levels

| Priority | Meaning |
|----------|---------|
| `P0` | Critical - must do next |
| `P1` | Important - high value |
| `P2` | Nice-to-have - lower priority |

## Updating the Board

### When starting a task
1. Move the task from `backlog` or `todo` to `in-progress`
2. Only one task should be `in-progress` at a time per feature area

### When completing a task
1. Move from `in-progress` to `done`
2. Add completion date if significant

### When discovering new work
1. Add to `backlog` with appropriate priority
2. Include a brief description

## Task Format

```markdown
- [STATUS] P#: Task title - Brief description
```

Example:
```markdown
- [todo] P1: Unit tests - Add pytest with coverage for all modules
```

## Board Maintenance Rules

1. **Keep it current**: Update status as you work
2. **One in-progress**: Avoid too many concurrent tasks
3. **Clear descriptions**: Others should understand at a glance
4. **No duplicates**: Check before adding new tasks
5. **Promote when ready**: Move from backlog to todo when prioritized
