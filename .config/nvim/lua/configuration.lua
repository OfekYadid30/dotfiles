local M = {}

-- When true, every plugin (including dependencies) is pinned: `:Lazy update`
-- and `:Lazy sync` will NOT move them past the commits in lazy-lock.json.
-- Keeps plugins compatible with the Neovim version this config targets.
-- Set to false to allow updating. See lua/plugins/init.lua for how this is used.
M.pin_plugins = true

-- Per-filetype LSP diagnostic messages to hide. Each entry is a Lua pattern
-- (string:match, not literal text and not full regex) checked against the
-- diagnostic's message; a diagnostic is hidden if any pattern for its
-- filetype matches. See lua/plugins/lsp_and_cmp.lua for how this is used.
--
-- Example (uncomment / adapt to enable):
-- M.ignore_error_patterns = {
--   python = {
--     "missing.-docstring",
--     "line too long",
--     "unused import",
--   },
--   cpp = {
--     "unused variable",
--     "unused parameter",
--   },
--   lua = {
--     "unused local",
--   },
-- }

M.ignore_error_patterns = {
  python = {},
  cpp = {},
  lua = {},
}

-- Highlights every occurrence of a given literal string with the specified
-- foreground color, in any buffer. Matching is CASE-SENSITIVE and an EXACT
-- match of the given text (not a wildcard or Lua/regex pattern) - e.g. a
-- key of "TODO" matches "TODO" but never "todo" or "Todo". It matches the
-- text wherever it occurs, including inside a larger word.
-- See core/highlight_strings.lua for the implementation.
--
-- Example (uncomment / adapt to enable):
-- M.highlight_strings = {
--   ["TODO"] = "#ff0000",
--   ["FIXME"] = "#ffaa00",
--   ["NOTE"] = "#00afff",
-- }

M.highlight_strings = {
  ["YAZIZ"] = "#ff0000"
}

return M
