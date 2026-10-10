
local M = {}

function M.setup()
  local ok, maximize = pcall(require, "maximize")
  if not ok then return end

  maximize.setup({
    restore_on_win_leave = false,
    integrations = { dap = true, nvimtree = true, aerial = true },
  })

  local colors = require("themes.western").colors

  local function apply_line_colors(maximized)
    local above = maximized and colors.line_number_zoom_fg or colors.line_number_above_fg
    local below = maximized and colors.line_number_zoom_fg or colors.line_number_below_fg
    local groups = {
      { "LineNrAbove", above },
      { "LineNrBelow", below },
      { "linenrabove", above },
      { "linenrbelow", below },
    }
    for _, item in ipairs(groups) do
      vim.api.nvim_set_hl(0, item[1], { fg = item[2] })
    end
  end

  local function list_normal_windows()
    local wins = {}
    for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
      if vim.api.nvim_win_get_config(win).relative == "" then
        table.insert(wins, win)
      end
    end
    return wins
  end

  local function normal_win_count()
    return #list_normal_windows()
  end

  local function is_oil_window(win)
    if not (win and vim.api.nvim_win_is_valid(win)) then return false end
    local buf = vim.api.nvim_win_get_buf(win)
    if not vim.api.nvim_buf_is_valid(buf) then return false end
    return vim.bo[buf].filetype == "oil"
  end

  local function close_other_oil_windows()
    local current = vim.api.nvim_get_current_win()
    if is_oil_window(current) then
      vim.notify("Oil pane can't be maximized. Close Oil and try again.", vim.log.levels.WARN)
      return false
    end

    for _, win in ipairs(list_normal_windows()) do
      if win ~= current and is_oil_window(win) then
        pcall(vim.api.nvim_win_close, win, true)
      end
    end
    return true
  end

  local function is_maximized()
    return vim.t.maximized == true and normal_win_count() == 1
  end

  local function sync_state(opts)
    opts = opts or {}
    if opts.clear_stale and vim.t.maximized and normal_win_count() > 1 then
      vim.t.maximized = false
    end
    apply_line_colors(is_maximized())
  end

  local function toggle()
    if not close_other_oil_windows() then
      return
    end

    sync_state({ clear_stale = true })

    if is_maximized() then
      maximize.restore()
      vim.schedule(function()
        sync_state()
      end)
      return
    end

    if normal_win_count() <= 1 then
      apply_line_colors(false)
      return
    end

    maximize.maximize()
    apply_line_colors(true)
  end

  vim.keymap.set("n", "<leader>;", toggle, {
    noremap = true,
    silent = true,
    desc = "Toggle maximize",
  })

  apply_line_colors(false)

  local aug = vim.api.nvim_create_augroup("MaximizeLineNumbers", { clear = true })
  vim.api.nvim_create_autocmd({ "WinNew", "WinClosed" }, {
    group = aug,
    callback = function(args)
      sync_state({ clear_stale = args.event == "WinNew" })
    end,
  })

  vim.api.nvim_create_autocmd("ColorScheme", {
    group = aug,
    callback = function()
      vim.schedule(function()
        sync_state()
      end)
    end,
  })
end

M.setup()
return M
