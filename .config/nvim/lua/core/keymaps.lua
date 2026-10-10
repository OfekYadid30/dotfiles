local window_utils = require("core.window_utils")
local session = require("core.session")
require("core.jump_stack")

local function relative_path()
  local file
  if vim.bo.filetype == "oil" then
    local ok, oil = pcall(require, "oil")
    file = ok and oil.get_current_dir()
    if not file then
      return nil, "Oil: unable to resolve directory"
    end
  else
    file = vim.fn.expand("%:p")
  end

  if not file or file == "" then
    return nil, "No file loaded"
  end

  file = file:gsub("/$", "")

  local root = session.get_root() or vim.fn.getcwd()
  local relative = vim.fn.fnamemodify(file, ":.")
  if root then
    local root_prefix = root:gsub("/$", "") .. "/"
    if file:sub(1, #root_prefix) == root_prefix then
      relative = file:sub(#root_prefix + 1)
    end
  end
  return relative
end

-- Builds on relative_path(): "<path>, at line: N" (is_visual = false)
-- or "<path>, at lines: start-end" (is_visual = true, collapses to
-- "at line: N" when the selection is a single line). Also returns the
-- start/end line numbers so callers building on top don't recompute them.
local function hs_string(is_visual)
  local relative, err = relative_path()
  if not relative then
    return nil, err
  end

  local start_line, end_line
  if is_visual then
    vim.cmd("normal! \27") -- exit visual mode so '< '> marks are set
    start_line = vim.fn.line("'<")
    end_line = vim.fn.line("'>")
  else
    start_line = vim.fn.line(".")
    end_line = start_line
  end

  local suffix
  if start_line == end_line then
    suffix = "at line: " .. start_line
  else
    suffix = "at lines: " .. start_line .. "-" .. end_line
  end

  return '"' .. relative .. '", ' .. suffix, start_line, end_line
end

-- Builds on hs_string(): appends ", content: <text>". Returns the full
-- message plus the hs_string() message (no content) for short notifications.
local function hd_string(is_visual)
  local info, start_line, end_line = hs_string(is_visual)
  if not info then
    return nil, start_line -- start_line holds the error message here
  end

  local content
  if is_visual then
    local mode = vim.fn.visualmode()
    local ok, region = pcall(vim.fn.getregion, vim.fn.getpos("'<"), vim.fn.getpos("'>"), { type = mode })
    content = ok and table.concat(region, "\n") or table.concat(vim.fn.getline(start_line, end_line), "\n")
  else
    content = vim.fn.getline(".")
  end

  return info .. ", content: ```\n" .. content .. "\n```", info
end

vim.keymap.set("n", "<leader>y", '"+y', { noremap = true, silent = true })
vim.keymap.set("v", "<leader>y", '"+y', { noremap = true, silent = true })
vim.keymap.set("n", "<leader>yy", '"+yy', { noremap = true, silent = true })

vim.keymap.set("n", "<C-h>", "<Cmd>wincmd h<CR>", { noremap = true, silent = true, desc = "Move to left pane" })
vim.keymap.set("n", "<C-j>", "<Cmd>wincmd j<CR>", { noremap = true, silent = true, desc = "Move to below pane" })
vim.keymap.set("n", "<C-k>", "<Cmd>wincmd k<CR>", { noremap = true, silent = true, desc = "Move to above pane" })
vim.keymap.set("n", "<C-l>", "<Cmd>wincmd l<CR>", { noremap = true, silent = true, desc = "Move to right pane" })
vim.keymap.set("n", "<C-Left>", "<Cmd>wincmd h<CR>", { noremap = true, silent = true, desc = "Move to left pane" })
vim.keymap.set("n", "<C-Down>", "<Cmd>wincmd j<CR>", { noremap = true, silent = true, desc = "Move to below pane" })
vim.keymap.set("n", "<C-Up>", "<Cmd>wincmd k<CR>", { noremap = true, silent = true, desc = "Move to above pane" })
vim.keymap.set("n", "<C-Right>", "<Cmd>wincmd l<CR>", { noremap = true, silent = true, desc = "Move to right pane" })

vim.keymap.set("n", "<BS>", "<Cmd>wincmd h<CR>", { noremap = true, silent = true })

vim.keymap.set(
  "n",
  "<leader>ss",
  [[:let @/='\<<C-r><C-w>\>'<CR>:set hlsearch<CR>]],
  { noremap = true, silent = true, desc = "Highlight word under cursor" }
)

vim.keymap.set(
  "n",
  "<leader>sa",
  [[:let @/="<C-r><C-w>"<CR>:set hlsearch<CR>]],
  { noremap = true, silent = true, desc = "Highlight substrings of word under cursor" }
)

vim.keymap.set(
  "n",
  "<leader>sd",
  ":nohlsearch<CR>",
  { noremap = true, silent = true, desc = "Remove search highlight" }
)

vim.keymap.set("n", "<leader>hh", function()
  local normal_count = 0
  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if vim.api.nvim_win_get_config(win).relative == "" then
      normal_count = normal_count + 1
    end
  end

  if normal_count < 2 then
    vim.cmd("vsplit")
    return
  end

  local source_win = vim.api.nvim_get_current_win()
  local info = window_utils.focus_closest_by_size({ ensure_target = false })
  if not info.target then
    vim.notify("Could not find another window to swap", vim.log.levels.WARN)
    return
  end

  local buf_source = vim.api.nvim_win_get_buf(source_win)
  local buf_target = vim.api.nvim_win_get_buf(info.target)

  vim.api.nvim_win_set_buf(source_win, buf_target)
  vim.api.nvim_win_set_buf(info.target, buf_source)
  vim.api.nvim_set_current_win(source_win)
end, { desc = "swap windows" })


vim.keymap.set("n", "<leader>hb", function()
  local source_win = vim.api.nvim_get_current_win()
  local file = vim.fn.expand("%:p")
  if file == "" then
    vim.notify("No file loaded", vim.log.levels.WARN)
    return
  end

  local pos = { unpack(vim.api.nvim_win_get_cursor(source_win)) }
  local info = window_utils.closest_by_size({ ensure_target = true })
  if not info.target then
    vim.notify("Could not locate a target window", vim.log.levels.WARN)
    return
  end

  local keys = vim.api.nvim_replace_termcodes("<C-o>", true, false, true)
  vim.api.nvim_feedkeys(keys, "n", true)

  vim.api.nvim_set_current_win(info.target)
  if vim.fn.expand("%:p") ~= file then
    vim.cmd("edit " .. vim.fn.fnameescape(file))
  end
  pcall(vim.api.nvim_win_set_cursor, info.target, pos)
  vim.api.nvim_set_current_win(source_win)
end, { noremap = true, silent = true, desc = "Mirror cursor in other split and jump back here" })

vim.keymap.set("n", "<leader>ha", function()
  local relative, err = relative_path()
  if not relative then
    vim.notify(err, vim.log.levels.WARN)
    return
  end

  vim.fn.setreg("+", relative)
  vim.notify("Copied: " .. relative)
end, { noremap = true, silent = true, desc = "Copy file path relative to root" })

vim.keymap.set("n", "<leader>hs", function()
  local msg, err = hs_string(false)
  if not msg then
    vim.notify(err, vim.log.levels.WARN)
    return
  end
  vim.fn.setreg("+", msg)
  vim.notify("Copied: " .. msg)
end, { noremap = true, silent = true, desc = "Copy file path with line number" })

vim.keymap.set("v", "<leader>hs", function()
  local msg, err = hs_string(true)
  if not msg then
    vim.notify(err, vim.log.levels.WARN)
    return
  end
  vim.fn.setreg("+", msg)
  vim.notify("Copied: " .. msg)
end, { noremap = true, silent = true, desc = "Copy file path with line range" })

vim.keymap.set("n", "<leader>hd", function()
  local msg, info = hd_string(false)
  if not msg then
    vim.notify(info, vim.log.levels.WARN)
    return
  end
  vim.fn.setreg("+", msg)
  -- notify only the path/line info, never the content: content can be
  -- multi-line and a multi-line vim.notify triggers a hit-enter prompt
  vim.notify("Copied: " .. info)
end, { noremap = true, silent = true, desc = "Copy file path, line number, and content" })

vim.keymap.set("v", "<leader>hd", function()
  local msg, info = hd_string(true)
  if not msg then
    vim.notify(info, vim.log.levels.WARN)
    return
  end
  vim.fn.setreg("+", msg)
  vim.notify("Copied: " .. info)
end, { noremap = true, silent = true, desc = "Copy file path, line range, and selected content" })

vim.keymap.set("n", "<leader>hf", function()
  local source_win = vim.api.nvim_get_current_win()
  local file = vim.fn.expand("%:p")
  if file == "" then
    vim.notify("No file loaded", vim.log.levels.WARN)
    return
  end

  local pos = { unpack(vim.api.nvim_win_get_cursor(source_win)) }
  window_utils.open_in_similar_pane(function(target_win)
    if not (target_win and vim.api.nvim_win_is_valid(target_win)) then
      vim.notify("Could not locate a target window", vim.log.levels.WARN)
      return
    end

    vim.api.nvim_set_current_win(target_win)
    if vim.fn.expand("%:p") ~= file then
      vim.cmd("edit " .. vim.fn.fnameescape(file))
    end
    pcall(vim.api.nvim_win_set_cursor, target_win, pos)
  end)
end, { noremap = true, silent = true, desc = "Mirror cursor in other split and focus it" })

vim.keymap.set("n", "<leader>wd", function()
  local source_win = vim.api.nvim_get_current_win()
  local info = window_utils.closest_by_size({ ensure_target = true })
  if not info.target then
    vim.notify("Could not locate a target window", vim.log.levels.WARN)
    return
  end

  vim.cmd("windo diffoff!")

  vim.api.nvim_set_current_win(source_win)
  vim.cmd("diffthis")

  vim.api.nvim_set_current_win(info.target)
  vim.cmd("diffthis")

  vim.api.nvim_set_current_win(source_win)
end, { noremap = true, silent = true, desc = "Diff current pane with the closest pane" })

vim.keymap.set("n", "<leader>wD", function()
  vim.cmd("windo diffoff!")
end, { noremap = true, silent = true, desc = "Remove diff from all panes" })
