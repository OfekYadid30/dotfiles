local M = {}

local function get_statusline_buf()
  local winid = vim.g.statusline_winid
  if winid and winid ~= 0 and vim.api.nvim_win_is_valid(winid) then
    return vim.api.nvim_win_get_buf(winid)
  end
  return 0
end

local function format_filename(bufnr)
  local bufname = vim.api.nvim_buf_get_name(bufnr or 0)
  if bufname == "" then
    return "[No Name]"
  end

  local display = bufname
  local oil_path = bufname:match("^oil://(.+)")
  if oil_path then
    display = oil_path
    if display == "" then display = "/" end
    local relative = vim.fn.fnamemodify(display, ":~:.")
    if relative ~= "." and relative ~= "" then
      display = relative
    else
      display = vim.fn.fnamemodify(display, ":~")
      if display == "" then display = "/" end
    end
    return display
  end

  display = vim.fn.fnamemodify(display, ":~:.")
  if display == "" then
    return "[No Name]"
  end
  return display
end

local function search_count_segment()
  if vim.v.hlsearch == 0 then
    return ""
  end

  local ok, count = pcall(vim.fn.searchcount, {
    recompute = 1,
    maxcount = 9999,
    timeout = 100,
  })
  if not ok or type(count) ~= "table" then
    return ""
  end

  local total = tonumber(count.total) or 0
  if total == 0 then
    return ""
  end

  local current = tonumber(count.current) or 0
  if count.incomplete == 1 then
    return string.format("[%d/?] ", current)
  end
  return string.format("[%d/%d] ", current, total)
end

function M.render()
  local filename = format_filename(get_statusline_buf()):gsub("%%", "%%%%")
  local search_segment = search_count_segment()
  local file_segment = table.concat({
    "%#StatusLineFile#",
    filename,
    "%#StatusLine#",
  })
  return table.concat({
    "%<",
    file_segment,
    "%h%m%r%=",
    search_segment,
    "%-14.(%l,%c%V%) %P",
  })
end

return M
