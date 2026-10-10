local ok, markview = pcall(require, "markview")
if not ok then
  return
end

markview.setup({
  preview = {
    modes = { "n", "v" },
  },

  options = {
    conceal = false,
    auto_start = false,
  },

  performance = {
    throttle = 50,
  },

  markdown_inline = {
    emoji_shorthands = {
      enable = false,
    },
    images = {
      enable = false,
    },
  },
})

vim.keymap.set("n", "<leader>wm", "<cmd>Markview Toggle<CR>", { desc = "Toggle Markview" })
