local M = {}
local last_file_window

local function is_valid_window(win)
  return win and win ~= 0 and vim.api.nvim_win_is_valid(win)
end

local function is_window_in_current_tab(win)
  return is_valid_window(win) and vim.api.nvim_win_get_tabpage(win) == vim.api.nvim_get_current_tabpage()
end

local function is_float_window(win)
  return vim.api.nvim_win_get_config(win).relative ~= ""
end

local function is_file_window(win)
  if not is_valid_window(win) or is_float_window(win) then
    return false
  end
  local buf = vim.api.nvim_win_get_buf(win)
  local bo = vim.bo[buf]
  return bo.buftype == "" and bo.filetype ~= "oil"
end

local function normalize_excluded_filetypes(value)
  if type(value) ~= "table" then
    return nil
  end
  if not vim.tbl_islist(value) then
    return value
  end

  local set = {}
  for _, ft in ipairs(value) do
    if type(ft) == "string" and ft ~= "" then
      set[ft] = true
    end
  end
  return set
end

local function list_normal_windows(opts)
  opts = opts or {}
  local excluded = normalize_excluded_filetypes(opts.exclude_filetypes)
  local windows = {}
  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if not is_float_window(win) then
      local buf = vim.api.nvim_win_get_buf(win)
      local bo = vim.bo[buf]
      local allowed_buftype = (not opts.require_editable) or bo.buftype == ""
      local allowed_filetype = not (excluded and excluded[bo.filetype])
      if allowed_buftype and allowed_filetype then
        table.insert(windows, win)
      end
    end
  end
  return windows
end

local function split_from_source(source_win, split_cmd)
  local previous = vim.api.nvim_get_current_win()
  if is_valid_window(source_win) then
    vim.api.nvim_set_current_win(source_win)
  end

  vim.cmd(split_cmd or "vsplit")

  if is_valid_window(previous) then
    vim.api.nvim_set_current_win(previous)
  end
end

function M.get_last_file_window()
  if is_file_window(last_file_window) and is_window_in_current_tab(last_file_window) then
    return last_file_window
  end

  local alternate = vim.fn.win_getid(vim.fn.winnr("#"))
  if is_file_window(alternate) and is_window_in_current_tab(alternate) then
    return alternate
  end

  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if is_file_window(win) then
      return win
    end
  end
  return nil
end

local function find_closest_by_size(source_win, windows, exclude_win)
  local best_win
  local min_diff = math.huge

  local source_width = vim.api.nvim_win_get_width(source_win)
  local source_height = vim.api.nvim_win_get_height(source_win)

  for _, win in ipairs(windows) do
    if win ~= exclude_win then
      local width = vim.api.nvim_win_get_width(win)
      local height = vim.api.nvim_win_get_height(win)
      local diff = math.abs(source_width - width) + math.abs(source_height - height)

      if diff < min_diff then
        min_diff = diff
        best_win = win
      end
    end
  end

  return best_win
end

function M.closest_by_size(opts)
  opts = opts or {}

  local source_win = opts.source_win or vim.api.nvim_get_current_win()
  if not is_window_in_current_tab(source_win) then
    source_win = vim.api.nvim_get_current_win()
  end

  -- The window to never target is the one the user is actually sitting in,
  -- not necessarily source_win (they differ when a picker like oil supplies
  -- a stand-in source_win while the current window is the picker itself).
  local exclude_win = vim.api.nvim_get_current_win()

  local list_opts = {
    require_editable = opts.require_editable,
    exclude_filetypes = opts.exclude_filetypes,
  }
  local windows = list_normal_windows(list_opts)
  local target = find_closest_by_size(source_win, windows, exclude_win)

  if opts.ensure_target and not target then
    split_from_source(source_win, opts.split_cmd)
    windows = list_normal_windows(list_opts)
    exclude_win = vim.api.nvim_get_current_win()
    target = find_closest_by_size(source_win, windows, exclude_win)
  end

  return {
    source = source_win,
    target = target,
  }
end

function M.focus_closest_by_size(opts)
  opts = opts or {}
  if opts.ensure_target == nil then
    opts.ensure_target = true
  end

  local info = M.closest_by_size(opts)
  if info.target and vim.api.nvim_win_is_valid(info.target) then
    vim.api.nvim_set_current_win(info.target)
  end
  return info
end

function M.open_in_similar_pane(cb, opts)
  opts = opts or {}
  if opts.ensure_target == nil then
    opts.ensure_target = true
  end

  local info = M.closest_by_size(opts)
  if info.target then
    cb(info.target)
    return true
  end
  return false
end

function M.jump_to_location_in_other_pane(location, encoding)
  M.open_in_similar_pane(function(win_id)
    if not (win_id and vim.api.nvim_win_is_valid(win_id)) then
      vim.lsp.util.show_document(location, encoding, { focus = true })
      return
    end
    vim.api.nvim_set_current_win(win_id)
    vim.lsp.util.show_document(location, encoding, { focus = true })
  end)
end

local tracking_group = vim.api.nvim_create_augroup("WindowUtilsTracking", { clear = true })
vim.api.nvim_create_autocmd({ "WinEnter", "BufWinEnter" }, {
  group = tracking_group,
  callback = function()
    local win = vim.api.nvim_get_current_win()
    if is_file_window(win) then
      last_file_window = win
    end
  end,
})

return M
