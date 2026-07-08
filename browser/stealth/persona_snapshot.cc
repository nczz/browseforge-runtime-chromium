#include "browseforge/stealth/persona_snapshot.h"

namespace browseforge {
namespace stealth {

bool PersonaSnapshot::IsComplete() const {
  return schema_version == "1.0" && runtime_id == "browseforge-chromium" &&
         seed != 0 && !persona_id_hash.empty() && !origin_salt_key.empty() &&
         browser.family == "chromium" && browser.major > 0 &&
         !browser.full_version.empty() && !browser.user_agent.empty() &&
         !platform.os.empty() && !platform.arch.empty() &&
         !platform.platform.empty() && !platform.platform_ch.empty() &&
         !locale.timezone.empty() && !locale.locale.empty() &&
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
  if (platform.os == "windows" && platform.platform != "Win32") {
    return false;
  }
  if (platform.os == "macos" && platform.platform != "MacIntel") {
    return false;
  }
  if (platform.os == "linux" && platform.platform != "Linux x86_64") {
    return false;
  }
  return true;
}

}  // namespace stealth
}  // namespace browseforge
