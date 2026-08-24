# ProxyHub Documentation

> Index updated: 2026-08-24

The documentation is divided into two areas. Directory and file names use English only; document content may remain Chinese.

## Backlog

Documents that describe current problems and future optimization work:

| Document | Purpose |
|---|---|
| [backlog/known-issues.md](backlog/known-issues.md) | 当前已知问题、优先级、影响和验收标准 |
| [backlog/architecture-improvements.md](backlog/architecture-improvements.md) | 当前软件和文件结构评估、后续结构优化建议 |
| [backlog/structure-refactor-plan.md](backlog/structure-refactor-plan.md) | 当前待确认的结构重构实施方案 |

## Archive

Historical design documents, API plans, implementation plans, and progress snapshots are stored under [`archive/`](archive/). They provide background but do not represent the current implementation status.

## Maintenance Rules

1. New problems go into `backlog/known-issues.md` using consecutive `KI-xxx` identifiers.
2. Structural improvement proposals go into `backlog/architecture-improvements.md`.
3. Completed items remain documented with completion date, commit, and verification result.
4. Superseded plans and historical snapshots are moved to `archive/` instead of being deleted.
