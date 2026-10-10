vim.opt.termguicolors = true
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.numberwidth = 1
vim.opt.signcolumn = "yes"
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true
vim.opt.smartindent = true
vim.opt.autoindent = true
vim.opt.cursorline = true
vim.opt.scrolloff = 4
vim.opt.completeopt = { "menu", "menuone", "noselect" }
vim.opt.splitright = true
vim.opt.cmdheight = 1
vim.opt.fillchars:append({
  vert = " ",
  vertleft = " ",
  vertright = " ",
  verthoriz = " ",
})
vim.o.statusline = "%!v:lua.require'core.statusline'.render()"
vim.opt.shortmess:remove("S")

vim.api.nvim_create_autocmd("filetype", {
  pattern = { "netrw", "nvimtree", "oil", "neo-tree" },
  callback = function()
    vim.opt_local.number = true
    vim.opt_local.relativenumber = true
  end,
})

local colors = require("themes.western").colors

local function normalize_hex_color(value)
  if value == nil then
    return nil
  end
  if type(value) == "number" then
    return string.format("#%06x", value)
  end
  if type(value) == "string" then
    if value == "NONE" then
      return nil
    end
    if value:match("^#%x%x%x%x%x%x$") then
      return value
    end
  end
  return nil
end

local function hex_to_rgb(hex)
  local normalized = normalize_hex_color(hex)
  if not normalized then
    return nil
  end
  return tonumber(normalized:sub(2, 3), 16),
    tonumber(normalized:sub(4, 5), 16),
    tonumber(normalized:sub(6, 7), 16)
end

local function rgb_to_hex(r, g, b)
  return string.format("#%02x%02x%02x", r, g, b)
end

local function blend_hex_colors(base_hex, target_hex, alpha)
  local r1, g1, b1 = hex_to_rgb(base_hex)
  local r2, g2, b2 = hex_to_rgb(target_hex)
  if not r1 or not r2 then
    return normalize_hex_color(base_hex)
  end
  local r = math.floor(r1 * (1 - alpha) + r2 * alpha + 0.5)
  local g = math.floor(g1 * (1 - alpha) + g2 * alpha + 0.5)
  local b = math.floor(b1 * (1 - alpha) + b2 * alpha + 0.5)
  return rgb_to_hex(r, g, b)
end

local function apply_custom_highlights()
  local cursorline = vim.api.nvim_get_hl(0, { name = "CursorLine", link = false })
  local statusline_bg = normalize_hex_color(cursorline.bg)
    or normalize_hex_color(colors.statusline_bg)
    or colors.editor_panel_background
  local commandline_bg = blend_hex_colors(statusline_bg, colors.editor_background, 0.18)
  vim.api.nvim_set_hl(0, "linenrabove", { fg = colors.line_number_above_fg })
  vim.api.nvim_set_hl(0, "linenrbelow", { fg = colors.line_number_below_fg })
  vim.api.nvim_set_hl(0, "WinSeparator", {
    fg = colors.win_separator_fg,
    bg = "NONE",
    bold = true,
  })
  vim.api.nvim_set_hl(0, "StatusLine", {
    fg = colors.statusline_file_fg,
    bg = statusline_bg,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "StatusLineNC", {
    fg = colors.statusline_file_fg,
    bg = statusline_bg,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "StatusLineFile", {
    fg = colors.statusline_file_fg,
    bg = statusline_bg,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "MsgArea", {
    fg = colors.statusline_file_fg,
    bg = commandline_bg,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "MsgSeparator", {
    fg = colors.statusline_file_fg,
    bg = commandline_bg,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "Cmdline", {
    fg = colors.statusline_file_fg,
    bg = commandline_bg,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "Visual", {
    bg = colors.visual_bg,
    fg = colors.editor_background,
    bold = true,
  })
  vim.api.nvim_set_hl(0, "VisualNOS", {
    bg = colors.visual_bg,
    fg = colors.editor_background,
    bold = true,
  })
end

apply_custom_highlights()

vim.api.nvim_create_autocmd({ "ColorScheme", "VimEnter" }, {
  callback = apply_custom_highlights,
})

vim.opt.signcolumn = "no"
