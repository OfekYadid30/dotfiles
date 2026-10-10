
local harpoon = require("harpoon")
local session = require("core.session")

local function get_session_root()
  return session.get_root() or vim.loop.cwd()
end

harpoon:setup({
  settings = {
    save_on_toggle = true,
    sync_on_ui_close = true,

    key = function()
      return get_session_root()
    end,

    save_file = function()
      local cwd = get_session_root()
      local key = cwd:gsub("[/:\\]", "_")
      return string.format("%s/harpoon_%s.json", vim.fn.stdpath("data"), key)
    end,
  },
})


vim.keymap.set("n", "<leader>aa", function()
  harpoon:list():add()
end, { desc = "Harpoon: Add file (end)" })

vim.keymap.set("n", "<leader>aA", function()
  harpoon:list():prepend()
end, { desc = "Harpoon: Add file (start)" })

vim.keymap.set("n", "<leader>af", function()
  harpoon.ui:toggle_quick_menu(harpoon:list())
end, { desc = "Harpoon: Toggle quick menu" })

vim.keymap.set("n", "<leader>ac", function()
  local list = harpoon:list()
  if list:length() == 0 then
    vim.notify("Harpoon: list already empty", vim.log.levels.INFO)
    return
  end

  list:clear()
  harpoon:sync()

  if harpoon.ui and harpoon.ui.bufnr and vim.api.nvim_buf_is_valid(harpoon.ui.bufnr) then
    vim.api.nvim_buf_set_lines(harpoon.ui.bufnr, 0, -1, false, {})
  end
end, { desc = "Harpoon: Clear all files" })

vim.keymap.set("n", "<leader>ah", function()
  harpoon:list():select(1)
end, { desc = "Harpoon: Select file 1" })
vim.keymap.set("n", "<leader>aj", function()
  harpoon:list():select(2)
end, { desc = "Harpoon: Select file 2" })
vim.keymap.set("n", "<leader>ak", function()
  harpoon:list():select(3)
end, { desc = "Harpoon: Select file 3" })
vim.keymap.set("n", "<leader>al", function()
  harpoon:list():select(4)
end, { desc = "Harpoon: Select file 4" })

vim.api.nvim_create_autocmd("FileType", {
  pattern = "harpoon",
  callback = function(args)
    vim.keymap.set("n", "<C-c>", function()
      require("harpoon").ui:toggle_quick_menu()
    end, { buffer = args.buf, silent = true, desc = "Harpoon: Close menu" })
  end,
})
