#ifndef BROWSEFORGE_STEALTH_PERSONA_RESOLVER_H_
#define BROWSEFORGE_STEALTH_PERSONA_RESOLVER_H_

#include <string>

#include "base/types/expected.h"
#include "browseforge/stealth/persona_snapshot.h"

namespace base {
class Value;
}

namespace browseforge {
namespace stealth {

enum class PersonaError {
  kMissingConfig,
  kInvalidJson,
  kIncompletePersona,
  kIncoherentPersona,
};

class PersonaResolver {
 public:
  PersonaResolver();
  PersonaResolver(const PersonaResolver&) = delete;
  PersonaResolver& operator=(const PersonaResolver&) = delete;
  ~PersonaResolver();

  base::expected<PersonaSnapshot, PersonaError> ResolveFromJson(
      const std::string& json) const;
  base::expected<PersonaSnapshot, PersonaError> ResolveFromValue(
      const base::Value& value) const;
};

}  // namespace stealth
}  // namespace browseforge

#endif  // BROWSEFORGE_STEALTH_PERSONA_RESOLVER_H_
