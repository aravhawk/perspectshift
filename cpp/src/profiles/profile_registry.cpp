#include "perceptshift/profiles/profile_registry.hpp"

namespace perceptshift::profiles {

bool ProfileRegistry::add(Profile profile) {
  if (profile.profile_id.empty() || profiles_.count(profile.profile_id) != 0) {
    return false;
  }
  profiles_.emplace(profile.profile_id, std::move(profile));
  return true;
}

Profile* ProfileRegistry::find(const std::string& id) {
  auto it = profiles_.find(id);
  return it == profiles_.end() ? nullptr : &it->second;
}

const Profile* ProfileRegistry::find(const std::string& id) const {
  auto it = profiles_.find(id);
  return it == profiles_.end() ? nullptr : &it->second;
}

std::vector<Profile*> ProfileRegistry::all() {
  std::vector<Profile*> out;
  out.reserve(profiles_.size());
  for (auto& [_, p] : profiles_) {
    out.push_back(&p);
  }
  return out;
}

std::vector<const Profile*> ProfileRegistry::all() const {
  std::vector<const Profile*> out;
  out.reserve(profiles_.size());
  for (const auto& [_, p] : profiles_) {
    out.push_back(&p);
  }
  return out;
}

} // namespace perceptshift::profiles
