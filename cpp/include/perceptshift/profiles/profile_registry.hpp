#pragma once

#include "perceptshift/profiles/profile.hpp"

#include <string>
#include <unordered_map>
#include <vector>

namespace perceptshift::profiles {

class ProfileRegistry {
public:
  bool add(Profile profile);
  [[nodiscard]] Profile* find(const std::string& id);
  [[nodiscard]] const Profile* find(const std::string& id) const;
  [[nodiscard]] std::vector<Profile*> all();
  [[nodiscard]] std::vector<const Profile*> all() const;
  [[nodiscard]] std::size_t size() const noexcept { return profiles_.size(); }

private:
  std::unordered_map<std::string, Profile> profiles_;
};

} // namespace perceptshift::profiles
