# Profile switch event with evidence summary.
std_msgs/Header header
string trace_id
string from_profile_id
string to_profile_id

# Switch reason constants.
uint8 REASON_STARTUP=0
uint8 REASON_DEADLINE=1
uint8 REASON_QUALITY=2
uint8 REASON_RESOURCE=3
uint8 REASON_CONFIDENCE=4
uint8 REASON_MANUAL_PIN=5
uint8 REASON_RECOVERY=6
uint8 REASON_FAIL_CLOSED=7
uint8 REASON_POLICY=8

uint8 reason_code
string reason_detail
uint64 effective_sequence_id
string evidence_summary
bool manual
