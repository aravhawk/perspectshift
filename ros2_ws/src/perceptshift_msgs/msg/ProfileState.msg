# Per-profile lifecycle and eligibility state.
std_msgs/Header header
string profile_id
string label

# Profile lifecycle constants.
uint8 LIFECYCLE_UNLOADED=0
uint8 LIFECYCLE_LOADED=1
uint8 LIFECYCLE_WARMED=2
uint8 LIFECYCLE_ACTIVE=3
uint8 LIFECYCLE_INELIGIBLE=4
uint8 LIFECYCLE_FAILED=5

uint8 lifecycle_state
bool active
bool eligible
string[] rejection_reason_codes
string certified_quality_metric
float32 certified_quality_value
float32 predicted_latency_bound_ms
float32 recent_p99_ms
uint64 peak_rss_attestation_bytes
string provider_summary
builtin_interfaces/Time manual_pin_expiry
bool manual_pin_active
