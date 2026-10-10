local patterns = require("configuration").highlight_strings or {}

if not vim.tbl_isempty(patterns) then
  local group_names = {}

  local function get_group_name(str)
    if not group_names[str] then
      group_names[str] = "UserHighlightString" .. (vim.tbl_count(group_names) + 1)
    end
    return group_names[str]
  end

  local function apply_highlight_groups()
    for str, color in pairs(patterns) do
      vim.api.nvim_set_hl(0, get_group_name(str), { fg = color })
    end
  end

  local win_match_ids = {}

  local function clear_window_matches(win)
    local ids = win_match_ids[win]
    if not ids then
      return
    end
    for _, id in ipairs(ids) do
      pcall(vim.fn.matchdelete, id, win)
    end
    win_match_ids[win] = nil
  end

  local function apply_window_matches(win)
    clear_window_matches(win)
    local ids = {}
    for str, _ in pairs(patterns) do
      -- \V = very nomagic (literal text), \C = force case-sensitive
      local vim_pattern = [[\V\C]] .. vim.fn.escape(str, [[\/]])
      local ok, id = pcall(vim.fn.matchadd, get_group_name(str), vim_pattern, 10, -1, { window = win })
      if ok then
        table.insert(ids, id)
      end
    end
    win_match_ids[win] = ids
  end

  apply_highlight_groups()

  local group = vim.api.nvim_create_augroup("UserHighlightStrings", { clear = true })

  vim.api.nvim_create_autocmd({ "BufWinEnter", "WinEnter", "FileType" }, {
    group = group,
    callback = function()
      apply_window_matches(vim.api.nvim_get_current_win())
    end,
  })

  vim.api.nvim_create_autocmd("ColorScheme", {
    group = group,
    callback = apply_highlight_groups,
  })

  vim.api.nvim_create_autocmd("WinClosed", {
    group = group,
    callback = function(args)
      win_match_ids[tonumber(args.match)] = nil
    end,
  })

  for _, win in ipairs(vim.api.nvim_list_wins()) do
    apply_window_matches(win)
  end
end
