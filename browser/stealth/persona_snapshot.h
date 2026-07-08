#ifndef BROWSEFORGE_STEALTH_PERSONA_SNAPSHOT_H_
#define BROWSEFORGE_STEALTH_PERSONA_SNAPSHOT_H_

#include <stdint.h>

#include <map>
#include <string>
#include <vector>

namespace browseforge {
namespace stealth {

struct BrowserIdentity {
  std::string family;
  int major = 0;
  std::string full_version;
  std::vector<std::string> brands;
  std::string user_agent;
};

struct PlatformIdentity {
  std::string os;
  std::string arch;
  std::string platform;
  std::string platform_ch;
  bool mobile = false;
  std::string bitness;
  std::string model;
};

struct LocaleIdentity {
  std::string timezone;
  std::string locale;
  std::string accept_language;
};

struct HardwareIdentity {
  int hardware_concurrency = 0;
  int device_memory_gb = 0;
};

struct ScreenIdentity {
  int width = 0;
  int height = 0;
  int avail_width = 0;
  int avail_height = 0;
  double device_scale_factor = 0;
  int color_depth = 0;
};

struct GpuIdentity {
  std::string vendor;
  std::string renderer;
  std::string angle_backend;
  std::map<std::string, std::string> webgl_params;
};

struct WebRtcPolicy {
  std::string mode;
  std::string proxy_region;
  bool direct_ip_redaction = false;
};

struct StoragePolicy {
  int quota_mb = 0;
  bool persistent = false;
};

struct PersonaSnapshot {
  std::string schema_version;
  std::string runtime_id;
  uint64_t seed = 0;
  std::string persona_id_hash;
  std::string origin_salt_key;
  BrowserIdentity browser;
  PlatformIdentity platform;
  LocaleIdentity locale;
  HardwareIdentity hardware;
  ScreenIdentity screen;
  GpuIdentity gpu;
  WebRtcPolicy webrtc;
  StoragePolicy storage;

  bool IsComplete() const;
  bool IsCoherent() const;
};

}  // namespace stealth
}  // namespace browseforge

#endif  // BROWSEFORGE_STEALTH_PERSONA_SNAPSHOT_H_
