vim.g.undotree_WindowLayout = 3
vim.g.undotree_SplitWidth = 40
vim.g.undotree_SetFocusWhenToggle = 1

vim.keymap.set("n", "<leader>u", ":UndotreeToggle<CR>", { desc = "Toggle Undotree" })
