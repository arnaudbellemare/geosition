# Heartbeat Tasks

Tasks checked automatically by `memi heartbeat --watch`.

## Every Cycle (30min default)
- [ ] All specs have `purpose` field
- [ ] No atoms composing other specs
- [ ] All component specs have shadcnBase
- [ ] Token coverage: color, spacing, typography, radius exist
- [ ] No specs modified since last generation (drift check)

## Daily
- [ ] Design system backup to .memoire/backups/
- [ ] Spec count report logged

## On Figma Connect
- [ ] Pull latest tokens
- [ ] Diff local vs Figma state
- [ ] Flag unbound color fills
