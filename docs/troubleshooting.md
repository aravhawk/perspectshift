# Troubleshooting

| Symptom | Checks |
|---------|--------|
| Configure fails | `bundle_path` set and exists; integrity verify; permissions |
| Control-hold always active | Eligible profiles? Core linked? Deadline/memory gates? |
| Malformed image rejected | Encoding/step/data length; see reason codes |
| Mutation service unavailable | `enable_mutation_services` |
| Power/temperature unavailable | Provider disabled or sysfs missing — expected with reason codes |
| Doctor warnings on macOS | Production target is Ubuntu Arm64 + ROS Jazzy |

Collect `perceptshift doctor --json` and health messages when filing bug reports. Do not attach proprietary models.
