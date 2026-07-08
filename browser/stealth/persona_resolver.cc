#include "browseforge/stealth/persona_resolver.h"

#include "base/json/json_reader.h"
#include "base/values.h"

namespace browseforge {
namespace stealth {

namespace {

std::string GetString(const base::Value::Dict& dict, const char* key) {
  const std::string* value = dict.FindString(key);
  return value ? *value : std::string();
}

int GetInt(const base::Value::Dict& dict, const char* key) {
  return dict.FindInt(key).value_or(0);
}

bool GetBool(const base::Value::Dict& dict, const char* key) {
  return dict.FindBool(key).value_or(false);
}

const base::Value::Dict* RequireDict(const base::Value::Dict& dict,
                                     const char* key) {
  return dict.FindDict(key);
}

}  // namespace

PersonaResolver::PersonaResolver() = default;
PersonaResolver::~PersonaResolver() = default;

base::expected<PersonaSnapshot, PersonaError> PersonaResolver::ResolveFromJson(
    const std::string& json) const {
  if (json.empty()) {
    return base::unexpected(PersonaError::kMissingConfig);
  }
  absl::optional<base::Value> parsed = base::JSONReader::Read(json);
  if (!parsed || !parsed->is_dict()) {
    return base::unexpected(PersonaError::kInvalidJson);
  }
  return ResolveFromValue(*parsed);
}

base::expected<PersonaSnapshot, PersonaError> PersonaResolver::ResolveFromValue(
    const base::Value& value) const {
  if (!value.is_dict()) {
    return base::unexpected(PersonaError::kInvalidJson);
  }
  const base::Value::Dict& root = value.GetDict();
  const base::Value::Dict* browser = RequireDict(root, "browser");
  const base::Value::Dict* platform = RequireDict(root, "platform");
  const base::Value::Dict* locale = RequireDict(root, "locale");
  const base::Value::Dict* hardware = RequireDict(root, "hardware");
  const base::Value::Dict* screen = RequireDict(root, "screen");
  const base::Value::Dict* gpu = RequireDict(root, "gpu");
  const base::Value::Dict* webrtc = RequireDict(root, "webrtc");
  const base::Value::Dict* storage = RequireDict(root, "storage");
  if (!browser || !platform || !locale || !hardware || !screen || !gpu ||
      !webrtc || !storage) {
    return base::unexpected(PersonaError::kIncompletePersona);
  }

  PersonaSnapshot snapshot;
  snapshot.schema_version = GetString(root, "schema_version");
  snapshot.runtime_id = GetString(root, "runtime_id");
  snapshot.seed = static_cast<uint64_t>(root.FindDouble("seed").value_or(0));
  snapshot.persona_id_hash = GetString(root, "persona_id_hash");
  snapshot.origin_salt_key = GetString(root, "origin_salt_key");
  snapshot.browser.family = GetString(*browser, "family");
  snapshot.browser.major = GetInt(*browser, "major");
  snapshot.browser.full_version = GetString(*browser, "full_version");
  snapshot.browser.user_agent = GetString(*browser, "user_agent");
  snapshot.platform.os = GetString(*platform, "os");
  snapshot.platform.arch = GetString(*platform, "arch");
  snapshot.platform.platform = GetString(*platform, "platform");
  snapshot.platform.platform_ch = GetString(*platform, "platform_ch");
  snapshot.platform.mobile = GetBool(*platform, "mobile");
  snapshot.platform.bitness = GetString(*platform, "bitness");
  snapshot.platform.model = GetString(*platform, "model");
  snapshot.locale.timezone = GetString(*locale, "timezone");
  snapshot.locale.locale = GetString(*locale, "locale");
  snapshot.locale.accept_language = GetString(*locale, "accept_language");
  snapshot.hardware.hardware_concurrency = GetInt(*hardware, "hardware_concurrency");
  snapshot.hardware.device_memory_gb = GetInt(*hardware, "device_memory_gb");
  snapshot.screen.width = GetInt(*screen, "width");
  snapshot.screen.height = GetInt(*screen, "height");
  snapshot.screen.avail_width = GetInt(*screen, "avail_width");
  snapshot.screen.avail_height = GetInt(*screen, "avail_height");
  snapshot.screen.device_scale_factor = screen->FindDouble("dpr").value_or(0);
  snapshot.screen.color_depth = GetInt(*screen, "color_depth");
  snapshot.gpu.vendor = GetString(*gpu, "vendor");
  snapshot.gpu.renderer = GetString(*gpu, "renderer");
  snapshot.gpu.angle_backend = GetString(*gpu, "angle_backend");
  snapshot.webrtc.mode = GetString(*webrtc, "mode");
  snapshot.webrtc.proxy_region = GetString(*webrtc, "proxy_region");
  snapshot.webrtc.direct_ip_redaction = GetBool(*webrtc, "direct_ip_redaction");
  snapshot.storage.quota_mb = GetInt(*storage, "quota_mb");
  snapshot.storage.persistent = GetBool(*storage, "persistent");

  if (!snapshot.IsComplete()) {
    return base::unexpected(PersonaError::kIncompletePersona);
  }
  if (!snapshot.IsCoherent()) {
    return base::unexpected(PersonaError::kIncoherentPersona);
  }
  return snapshot;
}

}  // namespace stealth
}  // namespace browseforge
