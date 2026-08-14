## Summary

<!-- What changed and why. -->

## Test plan

- [ ] `./scripts/verify-repository.sh`
- [ ] `make verify-host` (or `make verify` for release/packaging/container changes)
- [ ] ROS / API / console checks if those surfaces changed
- [ ] No fabricated benchmarks or event-specific language introduced

## Safety / claims check

- [ ] Uses deadline-aware / control-hold / fail-closed language where relevant
- [ ] Does not claim hard real-time, functional safety, or actuator authority
