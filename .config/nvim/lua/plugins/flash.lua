local flash = require("flash")

flash.setup({
  modes = {
    search = { enabled = false },
    char = { enabled = false },
    treesitter = { enabled = false },
  },
  keys = {},
})

vim.keymap.set({ "n", "x", "o" }, "<leader>jj", function()
  flash.jump()
end, { desc = "Flash jump (new search)" })

vim.keymap.set({ "n", "x", "o" }, "<leader>jh", function()
  flash.treesitter()
end, { desc = "Flash Treesitter jump" })

vim.keymap.set({ "n", "x", "o" }, "<leader>jk", function()
  flash.jump({ continue = true })
end, { desc = "Flash repeat last search" })
