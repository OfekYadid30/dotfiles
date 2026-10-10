local ok, context = pcall(require, "treesitter-context")
if not ok then
  return
end

context.setup({
  enable = true,
  max_lines = 0,
  min_window_height = 0,
  line_numbers = false,
  multiline_threshold = 20,
  trim_scope = "outer",
  mode = "cursor",
  separator = "-",
  zindex = 20,
  on_attach = function()
    return true
  end,
})
