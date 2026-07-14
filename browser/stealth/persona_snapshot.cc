#include "browseforge/stealth/persona_snapshot.h"

namespace browseforge {
namespace stealth {

namespace {

bool IsRawIPv4Address(const std::string& value) {
  int segments = 0;
  int octet = 0;
  bool has_digit = false;

  for (char c : value) {
    if (c >= '0' && c <= '9') {
      has_digit = true;
      octet = octet * 10 + (c - '0');
      if (octet > 255) {
        return false;
      }
      continue;
    }
    if (c != '.' || !has_digit) {
      return false;
    }
    segments++;
    octet = 0;
    has_digit = false;
  }
  return segments == 3 && has_digit;
}

bool IsValidProxyRegion(const std::string& region) {
  if (region.empty() || region.size() > 64 || IsRawIPv4Address(region)) {
    return false;
  }
  for (char c : region) {
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
        (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.') {
      continue;
    }
    return false;
  }
  return true;
}

bool IsCoherentPlatform(const PlatformIdentity& platform) {
  if (platform.bitness != "64") {
    return false;
  }
  if (platform.os == "windows") {
    return platform.platform == "Win32" && platform.arch == "x86" &&
           platform.platform_ch == "Windows";
  }
  if (platform.os == "macos") {
    return platform.platform == "MacIntel" &&
           (platform.arch == "x86" || platform.arch == "arm") &&
           platform.platform_ch == "macOS";
  }
  if (platform.os == "linux") {
    if (platform.platform_ch != "Linux") {
      return false;
    }
    return (platform.platform == "Linux x86_64" && platform.arch == "x86") ||
           (platform.platform == "Linux aarch64" && platform.arch == "arm");
  }
  return false;
}

}  // namespace

bool PersonaSnapshot::IsComplete() const {
  return schema_version == "1.0" && runtime_id == "browseforge-chromium" &&
         seed != 0 && !persona_id_hash.empty() && !origin_salt_key.empty() &&
         browser.family == "chromium" && browser.major > 0 &&
         !browser.full_version.empty() && !browser.user_agent.empty() &&
         !platform.os.empty() && !platform.arch.empty() &&
         !platform.platform.empty() && !platform.platform_ch.empty() &&
         !platform.bitness.empty() && !locale.timezone.empty() &&
         !locale.locale.empty() &&
         !locale.accept_language.empty() && hardware.hardware_concurrency > 0 &&
         hardware.device_memory_gb > 0 && screen.width > 0 &&
         screen.height > 0 && screen.avail_width > 0 && screen.avail_height > 0 &&
         screen.device_scale_factor > 0 && screen.color_depth > 0 &&
         !gpu.vendor.empty() && !gpu.renderer.empty() && !webrtc.mode.empty() &&
         storage.quota_mb > 0;
}

bool PersonaSnapshot::IsCoherent() const {
  if (!IsComplete()) {
    return false;
  }
  if (screen.avail_width > screen.width || screen.avail_height > screen.height) {
    return false;
  }
  if (!IsCoherentPlatform(platform)) {
    return false;
  }
  if (!webrtc.proxy_region.empty() && !IsValidProxyRegion(webrtc.proxy_region)) {
    return false;
  }
  return true;
}

}  // namespace stealth
}  // namespace browseforge
