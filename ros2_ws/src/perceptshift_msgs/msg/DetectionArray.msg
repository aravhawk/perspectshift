# Normalized detection output for one processed frame.
std_msgs/Header header
string trace_id
string profile_id
uint64 sequence_id
uint32 source_width
uint32 source_height
Detection[] detections
float32 adapter_confidence
bool confidence_valid
