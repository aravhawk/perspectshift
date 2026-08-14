# Requests upstream control logic to hold or degrade.
# Does not claim that a physical stop occurred and does not command actuators.
std_msgs/Header header
bool request_active
string reason_code
string trace_id
uint8 health_state
builtin_interfaces/Time first_active_timestamp
uint64 sequence_id
string summary
