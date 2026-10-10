vim.api.nvim_create_autocmd("FileType", {
  pattern = { "lua", "javascript", "typescript", "json", "yaml" },
  callback = function()
    vim.opt_local.tabstop = 2
    vim.opt_local.shiftwidth = 2
  end,
})

vim.opt.autoread = true

local file_sync_group = vim.api.nvim_create_augroup("FileSyncOnExternalChange", { clear = true })
vim.api.nvim_create_autocmd({
  "BufEnter",
  "FocusGained",
  "TermClose",
  "TermLeave",
  "CursorHold",
  "CursorHoldI",
}, {
  group = file_sync_group,
  callback = function()
    if vim.fn.mode() == "c" then
      return
    end
    vim.cmd("silent! checktime")
  end,
})

vim.api.nvim_create_autocmd("User", {
  pattern = "LazyDone",
  callback = function()
    local ok, western = pcall(require, "themes.western")
    if ok and western.rosepine and western.rosepine.setup then
      western.rosepine.setup()
    else
      vim.cmd.colorscheme("default")
    end
  end,
})

-- <CR> in the quickfix list (e.g. after telescope <C-l>) opens the entry in the
-- last focused file split. Neovim's default 'switchbuf=uselast' relies on the
-- previous window, which after telescope is its (closed) float -> arbitrary pick.
vim.api.nvim_create_autocmd("FileType", {
  group = vim.api.nvim_create_augroup("QuickfixOpenInLastSplit", { clear = true }),
  pattern = "qf",
  callback = function(args)
    local info = vim.fn.getwininfo(vim.api.nvim_get_current_win())[1]
    if info and info.loclist == 1 then
      return -- location lists belong to their own window; keep the default
    end
    vim.keymap.set("n", "<CR>", function()
      local idx = vim.fn.line(".")
      local target = require("core.window_utils").get_last_file_window()
      if not target or vim.wo[target].winfixbuf then
        vim.cmd(idx .. "cc")
        return
      end
      vim.api.nvim_set_current_win(target)
      vim.cmd(idx .. "cc")
    end, { buffer = args.buf, silent = true, desc = "Quickfix: open in last focused split" })
  end,
})
