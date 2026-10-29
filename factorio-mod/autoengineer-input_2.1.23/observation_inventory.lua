-- AutoEngineer read-only observation API - inventory.
--
-- The inventory observation reads the player's character main inventory. It
-- never inserts, removes or moves a stack.
--
-- The shape matches what the dashboard has always consumed: the aggregated
-- item list, the individual slots of the first 200 slots, the capacity and
-- the truncation flag.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

-- The bounds the dashboard has always accepted.
local MAX_SLOTS = 200
local MAX_SCANNED_SLOTS = 2000
local MAX_AGGREGATED_ITEMS = 64

local function observe_inventory()
    local player, character = observation.observed_player()
    if not player or not character then
        return observation.unavailable("no_connected_player_with_character")
    end

    local inventory = character.get_inventory(defines.inventory.character_main)
    if not inventory then
        return observation.unavailable("no_character_inventory")
    end

    -- The aggregated item list and the individual slots.
    local items = {}
    local lookup = {}
    local slots = {}
    local truncated = false
    local capacity = #inventory

    for index = 1, math.min(#inventory, MAX_SCANNED_SLOTS) do
        local stack = inventory[index]
        if stack.valid_for_read then
            local quality = stack.quality and stack.quality.name or "normal"
            if index <= MAX_SLOTS then
                slots[#slots + 1] = {
                    slot = index,
                    name = stack.name,
                    quality = quality,
                    count = stack.count,
                }
            end
            local key = stack.name .. ":" .. quality
            local item = lookup[key]
            if item then
                item.count = item.count + stack.count
            elseif #items < MAX_AGGREGATED_ITEMS then
                item = { name = stack.name, quality = quality, count = stack.count }
                lookup[key] = item
                items[#items + 1] = item
            else
                truncated = true
            end
        end
    end
    if #inventory > MAX_SCANNED_SLOTS then
        truncated = true
    end

    return observation.ok({
        tick = game.tick,
        inventory = items,
        inventory_available = true,
        capacity = capacity,
        slots = slots,
        slots_truncated = #inventory > MAX_SLOTS,
        truncated = truncated,
    })
end

observation.HANDLERS.inventory = observe_inventory
