#include "perceptshift/host/raspberry_pi_telemetry.hpp"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>

#if defined(__linux__)
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace perceptshift::host {
namespace {

#if defined(__linux__)
Result<std::string> run_vcgencmd(const char* arg) {
  int pipefd[2];
  if (::pipe(pipefd) != 0) {
    return Err<std::string>(ErrorCode::TelemetryUnavailable, "pipe failed for vcgencmd");
  }
  const pid_t pid = ::fork();
  if (pid < 0) {
    ::close(pipefd[0]);
    ::close(pipefd[1]);
    return Err<std::string>(ErrorCode::TelemetryUnavailable, "fork failed for vcgencmd");
  }
  if (pid == 0) {
    ::close(pipefd[0]);
    ::dup2(pipefd[1], STDOUT_FILENO);
    ::dup2(pipefd[1], STDERR_FILENO);
    ::close(pipefd[1]);
    const char* argv[] = {"vcgencmd", arg, nullptr};
    ::execvp("vcgencmd", const_cast<char* const*>(argv));
    _exit(127);
  }
  ::close(pipefd[1]);
  std::string out;
  std::array<char, 256> buf{};
  ssize_t n = 0;
  while ((n = ::read(pipefd[0], buf.data(), buf.size())) > 0) {
    out.append(buf.data(), static_cast<std::size_t>(n));
    if (out.size() > 4096) {
      break;
    }
  }
  ::close(pipefd[0]);
  int status = 0;
  ::waitpid(pid, &status, 0);
  if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
    return Err<std::string>(ErrorCode::TelemetryUnavailable, "vcgencmd failed");
  }
  while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) {
    out.pop_back();
  }
  return Ok(std::move(out));
}
#endif

} // namespace

Result<RaspberryPiTelemetry> read_raspberry_pi_telemetry() {
  RaspberryPiTelemetry tel;
#if defined(__linux__)
  std::ifstream model("/proc/device-tree/model");
  if (model) {
    std::string m((std::istreambuf_iterator<char>(model)), std::istreambuf_iterator<char>());
    while (!m.empty() && m.back() == '\0') {
      m.pop_back();
    }
    if (m.find("Raspberry Pi") != std::string::npos) {
      tel.is_raspberry_pi = true;
      tel.model = m;
    }
  }
  std::ifstream rev("/proc/device-tree/system/linux,revision");
  if (!rev) {
    rev.open("/proc/cpuinfo");
  }
  if (tel.is_raspberry_pi) {
    auto temp = run_vcgencmd("measure_temp");
    if (temp) {
      // temp=45.6'C
      const auto& s = temp.value();
      const auto eq = s.find('=');
      const auto c = s.find("'C");
      if (eq != std::string::npos && c != std::string::npos && c > eq + 1) {
        try {
          tel.temperature_c = std::stod(s.substr(eq + 1, c - eq - 1));
        } catch (...) {
        }
      }
    }
    auto throttled = run_vcgencmd("get_throttled");
    if (throttled) {
      const auto& s = throttled.value();
      const auto eq = s.find('=');
      if (eq != std::string::npos) {
        try {
          const auto raw = static_cast<std::uint32_t>(std::stoul(s.substr(eq + 1), nullptr, 0));
          RaspberryPiThrottleFlags f;
          f.raw = raw;
          f.under_voltage_now = (raw & (1u << 0)) != 0;
          f.freq_capped_now = (raw & (1u << 1)) != 0;
          f.throttled_now = (raw & (1u << 2)) != 0;
          f.soft_temp_limit_now = (raw & (1u << 3)) != 0;
          f.under_voltage_occurred = (raw & (1u << 16)) != 0;
          f.freq_cap_occurred = (raw & (1u << 17)) != 0;
          f.throttling_occurred = (raw & (1u << 18)) != 0;
          f.soft_temp_limit_occurred = (raw & (1u << 19)) != 0;
          tel.throttle = f;
        } catch (...) {
        }
      }
    }
    tel.status = "ok";
  } else {
    tel.status = "unavailable";
    tel.reason_code = "NOT_RASPBERRY_PI";
  }
#else
  tel.status = "unavailable";
  tel.reason_code = "RASPBERRY_PI_TELEMETRY_LINUX_ONLY";
#endif
  return Ok(std::move(tel));
}

} // namespace perceptshift::host
