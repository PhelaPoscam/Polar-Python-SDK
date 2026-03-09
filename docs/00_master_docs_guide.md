# Documentation Master Guide

Single source of truth for documentation organization, historical reorganization notes, and current canonical doc entry points.

## 1. Canonical Documentation Layout

Use this structure as authoritative:

```text
docs/
├── README.md                    # docs entry index
├── 00_master_docs_guide.md      # this file
├── contributing.md              # contribution workflow
└── nuanic/
    ├── README.md                # Nuanic entry index
    └── 00_master_guide.md       # unified Nuanic technical guide
```

## 2. Scope of Each Doc

- `docs/README.md`: quick navigation for contributors and users.
- `docs/00_master_docs_guide.md`: project-level documentation structure, migration notes, and ownership.
- `docs/contributing.md`: contribution policy and engineering conventions.
- `docs/nuanic/README.md`: short landing page for Nuanic documentation.
- `docs/nuanic/00_master_guide.md`: all Nuanic setup, CLI/API usage, packet details, analysis, and troubleshooting.

## 3. Consolidated Reorganization Notes

This section preserves key details previously split between project organization and reorganization files.

### 3.1 Intent of Reorganization
- Reduce documentation duplication and path drift.
- Remove split guidance where multiple files described the same workflows.
- Keep one operational guide per domain (project-level, Nuanic-level).

### 3.2 Old-to-new documentation mapping
- `docs/project_organization.md` -> merged into this file and `docs/nuanic/00_master_guide.md`.
- `docs/REORGANIZATION.md` -> merged into this file.
- `docs/nuanic/*.md` multi-file set -> merged into `docs/nuanic/00_master_guide.md`.
- `docs/nuanic/troubleshooting/*.md` -> merged into `docs/nuanic/00_master_guide.md` under troubleshooting and historical notes.

### 3.3 Preserved historical context
The previous docs included timeline-specific statements such as:
- script path migration from `scripts/ble/*` to `scripts/*_cli.py`.
- architecture snapshots from exploratory and production phases.
- contradictory troubleshooting states during ring connection and EDA verification.

All of that context is retained in the Nuanic master guide in clearly labeled historical sections, rather than distributed across many files.

## 4. Documentation Maintenance Rules

1. Add new operational instructions to the relevant master guide first.
2. Keep index files (`docs/README.md`, `docs/nuanic/README.md`) short and link-focused.
3. Avoid creating topic files that duplicate command usage, packet mappings, or troubleshooting checklists already in master guides.
4. If historical contradictions exist, document them in a "Historical Notes" section rather than separate status files.
5. Update root `README.md` links whenever docs paths change.

## 5. Ownership and Update Workflow

When docs change:
1. Update domain master guide.
2. Update index README links.
3. Remove now-redundant files after link verification.
4. Ensure root `README.md` has no broken references.

## 6. Validation Checklist

Before finalizing doc updates:
- All links in `docs/README.md` resolve.
- All links in `docs/nuanic/README.md` resolve.
- Root `README.md` links point to existing docs.
- No duplicated command sections across multiple docs.
- No stale references to removed files.
