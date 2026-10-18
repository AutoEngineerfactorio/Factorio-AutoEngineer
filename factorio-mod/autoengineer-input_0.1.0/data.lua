local inputs={}
for _,control in ipairs(require("inputs")) do
    inputs[#inputs+1]={type="custom-input",name="autoengineer-human-"..control,
        key_sequence="",linked_game_control=control,consuming="none"}
end
data:extend(inputs)
