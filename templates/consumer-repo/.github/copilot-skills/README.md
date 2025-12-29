# Copilot Skills

This folder contains skill definitions that help GitHub Copilot perform tasks consistently and avoid common mistakes.

## Structure

Skills are numbered for load order:

- `00-core-skills.md` - Meta-skills and fundamental patterns
- `01-ci-debugging.md` - CI failure analysis and fixes
- `02-github-operations.md` - Safe GitHub workflows

## How Skills Work

Skills are markdown files that Copilot reads as context. They define:

1. **Triggers** - When to apply the skill
2. **Steps** - What to do
3. **Patterns** - Common issues and fixes

## Adding New Skills

1. Create a new file: `{NN}-{skill-name}.md`
2. Include a clear trigger condition
3. Add step-by-step instructions
4. Include common failure patterns

## Skill Template

```markdown
# Skill: {Name}

**Trigger**: {When to use this skill}

## Steps

1. Step one
2. Step two

## Common Patterns

| Symptom | Cause | Fix |
|---------|-------|-----|
| ... | ... | ... |
```

## Local vs Synced Skills

- **Synced** (this folder): Skills that apply to all repos
- **Local** (`.github/copilot-skills-local/`): Repo-specific skills

Skills in this folder are synced from the Workflows repo to all consumer repos.
