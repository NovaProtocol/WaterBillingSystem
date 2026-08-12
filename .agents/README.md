# .agents — Agent Workspace

This directory holds reference material, scripts, and configuration for AI agents working on the WaterBillingSystem codebase. Everything here is gitignored — it's for agent use only, not part of the shipped project.

## Structure

```
.agents/
├── README.md              ← This file. Start here.
├── index.md               ← Table of contents for all reference files
├── reference/             ← Topic-based codebase reference files
│   ├── project-overview.md
│   ├── authentication.md
│   ├── database-schema.md
│   ├── billing-pricing.md
│   ├── staff-portal.md
│   ├── rest-api.md
│   ├── meter-reading-app.md
│   ├── nfc-security.md
│   ├── background-worker.md
│   ├── deployment-workflow.md
│   ├── docker-deployment.md
│   └── testing.md
└── scripts/               ← Utility scripts for remote tasks
    ├── docker.sh           ← Remote Docker commands via SSH
    └── README.md           ← How to use the scripts
```

## How to use

1. Read `index.md` to find the reference file relevant to your task
2. Read the specific reference file(s) for deep context
3. Use `scripts/docker.sh` for remote Docker operations when needed
