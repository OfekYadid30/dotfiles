vim.g.no_cecutil_maps = 1

local ansi_enabled = false

local function toggle_ansi()
  if ansi_enabled then
    vim.cmd("syntax off | syntax on")
    ansi_enabled = false
    print("ANSI highlighting OFF")
  else
    vim.cmd("AnsiEsc")
    ansi_enabled = true
    print("ANSI highlighting ON")
  end
end

vim.keymap.set("n", "<leader>wc", toggle_ansi, { desc = "Toggle ANSI color highlighting" })
