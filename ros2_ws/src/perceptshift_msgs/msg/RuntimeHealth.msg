# Runtime health publication. Control-hold request is advisory to upstream control.
std_msgs/Header header

# Health state constants (soft real-time runtime health, not a certified safe state).
uint8 HEALTH_UNKNOWN=0
uint8 HEALTH_OK=1
uint8 HEALTH_DEGRADED=2
uint8 HEALTH_FAIL_CLOSED=3
uint8 HEALTH_RECOVERING=4
uint8 HEALTH_ERROR=5

uint8 health_state
string reason_code
string summary
string trace_id
string active_profile_id
uint32 eligible_profile_count
bool source_stale
bool control_hold_requested
uint64 process_rss_bytes
uint64 available_memory_bytes
float32 primary_temperature_celsius
bool primary_temperature_valid
bool throttling
bool throttling_valid
uint32 consecutive_inference_failures
uint32 consecutive_deadline_misses
uint64 last_successful_sequence_id
