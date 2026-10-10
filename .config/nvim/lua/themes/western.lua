
local M = {}

local hex_editor_bg_primary         = "#1e1a16"
local hex_editor_bg_alt             = "#2a231d"
local hex_editor_fg_primary         = "#e0c097"
local hex_pale_gold                = "#fdf1df"
local hex_light_gold               = "#ddb97a"
local hex_full_gold                = "#d4a657"
local hex_light_gray               = "#b3b3b3"
local hex_dark_gold                = "#6f5211"
local hex_sand                     = "#c8a379"
local hex_telescope_focus_bg       = "#9b6b24"
local hex_red_clay                 = "#b25c3e"
local hex_accent                   = "#e3bf55"
local hex_border                   = "#3b2e1f"
local hex_visual                   = "#3b2a1a"
local hex_visual_bright_green      = hex_pale_gold
local hex_comment                  = "#a69279"
local hex_green_soft               = "#8ee3a6"
local hex_pink_soft                = "#f0b5c8"
local hex_purple_soft              = "#c4a7e7"
local hex_green_primary            = "#4fa96b"
local hex_statusline_bg            = "#241f1a"
local hex_dap_breakpoint_line_bg   = "#2a0e0e"
local hex_dap_stopped_line_bg      = "#142a14"
local hex_zoom_restore_fallback_fg = "#b48ead"

local color_editor_background             = hex_editor_bg_primary
local color_editor_panel_background       = hex_editor_bg_alt
local color_editor_primary_text           = hex_editor_fg_primary
local color_line_number_above_fg          = hex_light_gold
local color_line_number_below_fg          = hex_light_gold
local color_line_number_zoom_fg           = hex_pale_gold
local color_line_number_restore_fallback  = hex_zoom_restore_fallback_fg
local color_bookmark_sign_icon_fg         = hex_green_soft
local color_bookmark_highlight_text       = hex_full_gold
local color_bookmark_highlight_background = hex_editor_bg_alt
local color_telescope_preview_line_bg     = hex_telescope_focus_bg
local color_dap_breakpoint_line_bg        = hex_dap_breakpoint_line_bg
local color_dap_stopped_line_bg           = hex_dap_stopped_line_bg
local color_win_separator_fg              = hex_light_gray
local color_statusline_file_fg            = hex_light_gold
local color_statusline_bg                 = hex_statusline_bg
local color_visual_bg                     = hex_visual_bright_green

M.colors = {
  editor_background = color_editor_background,
  editor_panel_background = color_editor_panel_background,
  editor_primary_text = color_editor_primary_text,
  line_number_above_fg = color_line_number_above_fg,
  line_number_below_fg = color_line_number_below_fg,
  line_number_zoom_fg = color_line_number_zoom_fg,
  line_number_restore_fallback_fg = color_line_number_restore_fallback,
  bookmark_sign_icon_fg = color_bookmark_sign_icon_fg,
  bookmark_highlight_text_fg = color_bookmark_highlight_text,
  bookmark_highlight_bg = color_bookmark_highlight_background,
  telescope_preview_line_bg = color_telescope_preview_line_bg,
  dap_breakpoint_line_bg = color_dap_breakpoint_line_bg,
  dap_stopped_line_bg = color_dap_stopped_line_bg,
  win_separator_fg = color_win_separator_fg,
  statusline_file_fg = color_statusline_file_fg,
  statusline_bg = color_statusline_bg,
  visual_bg = color_visual_bg,
}

M.rosepine = {
  setup = function()
    local ok, rp = pcall(require, "rose-pine")
    if ok then
      rp.setup({
        variant = "main",
        disable_background = false,
      })
      vim.cmd.colorscheme("rose-pine")
    else
      vim.notify("rose-pine.nvim not found", vim.log.levels.WARN)
    end
  end,
}

return M
