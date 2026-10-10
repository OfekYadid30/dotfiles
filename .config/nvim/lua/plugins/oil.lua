local window_utils = require("core.window_utils")
local session = require("core.session")
local oil = require("oil")

oil.setup({
  default_file_explorer = true,
  experimental_watch_for_changes = true,
  columns = {
    "permissions",
    "size",
    "mtime",
  },
  keymaps = {
    ["<C-h>"] = false,
    ["<C-j>"] = false,
    ["<C-k>"] = false,
    ["<C-l>"] = false,
    ["<C-s>"] = false,
    ["<C-t>"] = false,
    ["<C-p>"] = false,
    ["<C-c>"] = false,
  },
})

vim.keymap.set("n", "<leader>e", "<cmd>Oil<CR>", { desc = "Open File Explorer" })

vim.api.nvim_create_autocmd("FileType", {
  pattern = "oil",
  callback = function(args)
    local buf = args.buf

    vim.keymap.set("n", "gd", function()
      oil.select()
    end, { buffer = buf, desc = "Oil: open entry", silent = true })

    vim.keymap.set("n", "<leader>gd", function()
      local entry = oil.get_cursor_entry()
      if not entry then
        vim.notify("Oil: no entry under cursor", vim.log.levels.WARN)
        return
      end

      local dir = oil.get_current_dir() or session.get_root() or vim.fn.getcwd()
      if not dir or dir == "" then
        vim.notify("Oil: unable to resolve directory", vim.log.levels.WARN)
        return
      end
      local path = vim.fn.fnamemodify(dir .. "/" .. entry.name, ":p")
      local is_file = entry.type == "file"

      local open_opts = {}
      local source_win = window_utils.get_last_file_window()
      if source_win and vim.api.nvim_win_is_valid(source_win) then
        open_opts.source_win = source_win
        open_opts.require_editable = true
        open_opts.exclude_filetypes = { "oil" }
      end

      local function open_at(target_win)
        if target_win and vim.api.nvim_win_is_valid(target_win) then
          vim.api.nvim_set_current_win(target_win)
        end
        if is_file then
          vim.cmd.edit(vim.fn.fnameescape(path))
        else
          oil.open(path)
        end
      end

      local opened = window_utils.open_in_similar_pane(open_at, open_opts)

      if not opened then
        open_at(nil)
      end
    end, { buffer = buf, desc = "Oil: open entry in matching pane", silent = true })
  end,
})
