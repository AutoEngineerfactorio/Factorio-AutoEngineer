local inputs = require("inputs")
local prototypes = {}
for _, name in ipairs(inputs) do
  prototypes[#prototypes + 1] = {
    type = "custom-input",
    name = "autoengineer-human-" .. name,
    key_sequence = "",
    linked_game_control = name,
    consuming = "none"
  }
end
data:extend(prototypes)
