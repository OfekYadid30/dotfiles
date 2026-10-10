local M = {}

local stack = {}
local keymaps_set = false

local function normalize_path(path)
  if not path or path == "" then
    return nil
  end
  local uv = vim.uv or vim.loop
  if uv and uv.fs_realpath then
    local real = uv.fs_realpath(path)
    if real and real ~= "" then
      return real
    end
  end
  return vim.fn.fnamemodify(path, ":p")
end

local function is_valid_buf(bufnr)
  return bufnr and bufnr ~= 0 and vim.api.nvim_buf_is_valid(bufnr)
end

local function capture_location()
  local bufnr = vim.api.nvim_get_current_buf()
  if not is_valid_buf(bufnr) then
    return nil, "No active buffer"
  end
  -- Non-file buffers (e.g. fugitive diff/log output) are saved by bufnr only:
  -- their name is a temp file, so there's nothing to reopen once they're gone.
  local is_file = vim.bo[bufnr].buftype == ""
  local filename = is_file and vim.api.nvim_buf_get_name(bufnr) or nil
  local cursor = vim.api.nvim_win_get_cursor(0)
  local lnum = cursor[1] or 1
  local col = (cursor[2] or 0) + 1

  local entry = {
    bufnr = bufnr,
    filename = normalize_path(filename),
    lnum = lnum,
    col = col,
    text = vim.api.nvim_get_current_line(),
  }

  if not entry.filename or entry.filename == "" then
    entry.filename = nil
  end

  return entry
end

local function jump_to_entry(entry)
  if type(entry) ~= "table" then
    vim.notify("Invalid jump location", vim.log.levels.WARN)
    return false
  end

  local filename = entry.filename
  local bufnr = entry.bufnr
  local target_bufnr = nil

  if is_valid_buf(bufnr) then
    if filename then
      local bufname = normalize_path(vim.api.nvim_buf_get_name(bufnr))
      if bufname == filename then
        target_bufnr = bufnr
      end
    else
      target_bufnr = bufnr
    end
  end

  if target_bufnr then
    vim.api.nvim_set_current_buf(target_bufnr)
  elseif filename and filename ~= "" then
    if vim.fn.filereadable(filename) ~= 1 then
      vim.notify("File no longer exists: " .. filename, vim.log.levels.WARN)
      return false
    end
    vim.cmd.edit(vim.fn.fnameescape(filename))
  else
    vim.notify("Jump location no longer available", vim.log.levels.WARN)
    return false
  end

  local lnum = tonumber(entry.lnum) or 1
  local col = tonumber(entry.col) or 1
  pcall(vim.api.nvim_win_set_cursor, 0, { lnum, math.max(col - 1, 0) })
  return true
end

function M.push()
  local entry, err = capture_location()
  if not entry then
    vim.notify(err or "Could not save jump location", vim.log.levels.WARN)
    return
  end
  stack[#stack + 1] = entry
end

-- Top of the stack, or nil (with a notice) when it's empty.
local function peek()
  local entry = stack[#stack]
  if not entry then
    vim.notify("Jump stack is empty", vim.log.levels.INFO)
  end
  return entry
end

function M.apply()
  local entry = peek()
  if entry then
    jump_to_entry(entry)
  end
end

function M.pop()
  if peek() then
    table.remove(stack)
  end
end

function M.pop_and_apply()
  if peek() then
    jump_to_entry(table.remove(stack))
  end
end

function M.clear()
  if #stack == 0 then
    vim.notify("Jump stack is already empty", vim.log.levels.INFO)
    return
  end
  stack = {}
end

function M.show()
  local ok, telescope = pcall(require, "plugins.telescope")
  if not ok or type(telescope) ~= "table" or type(telescope.show_list) ~= "function" then
    vim.notify("Telescope not available", vim.log.levels.WARN)
    return
  end

  local entries = {}
  for i = #stack, 1, -1 do
    local entry = stack[i]
    local bufnr = is_valid_buf(entry.bufnr) and entry.bufnr or nil
    if entry.filename or bufnr then
      entries[#entries + 1] = {
        bufnr = bufnr,
        filename = entry.filename,
        lnum = entry.lnum,
        col = entry.col,
        text = entry.text or "",
      }
    end
  end

  telescope.show_list(entries, {
    prompt_title = "Jump Stack",
    empty_message = "Jump stack is empty",
    on_select = function(selection)
      local item = selection
      if type(selection) == "table" and selection.value ~= nil then
        item = selection.value
      end
      jump_to_entry(item)
    end,
  })
end

function M.setup_keymaps()
  if keymaps_set then
    return
  end
  keymaps_set = true

  vim.keymap.set("n", "<leader>ks", M.push, { noremap = true, silent = true, desc = "Jump stack: save location" })
  vim.keymap.set("n", "<leader>ka", M.apply, { noremap = true, silent = true, desc = "Jump stack: apply last" })
  vim.keymap.set("n", "<leader>kd", M.pop, { noremap = true, silent = true, desc = "Jump stack: remove last" })
  vim.keymap.set("n", "<leader>kp", M.pop_and_apply, { noremap = true, silent = true, desc = "Jump stack: pop last (go + remove)" })
  vim.keymap.set("n", "<leader>kc", M.clear, { noremap = true, silent = true, desc = "Jump stack: clear" })
  vim.keymap.set("n", "<leader>kf", M.show, { noremap = true, silent = true, desc = "Jump stack: show" })
end

M.setup_keymaps()

return M
