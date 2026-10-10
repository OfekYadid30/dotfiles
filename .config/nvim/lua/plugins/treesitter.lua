local ok, configs = pcall(require, "nvim-treesitter.configs")
if not ok then
  return
end

local uv = vim.uv or vim.loop

local function resolve_treesitter_root()
  local lazy_ok, lazy_config = pcall(require, "lazy.core.config")
  if lazy_ok and lazy_config.plugins and lazy_config.plugins["nvim-treesitter"] then
    local dir = lazy_config.plugins["nvim-treesitter"].dir
    if type(dir) == "string" and uv.fs_stat(dir) then
      return dir
    end
  end

  local fallbacks = {
    vim.fn.stdpath("data") .. "/lazy/nvim-treesitter",
    vim.fn.stdpath("config") .. "/pack/offline/start/nvim-treesitter",
  }
  for _, dir in ipairs(fallbacks) do
    if uv.fs_stat(dir) then
      return dir
    end
  end

  return fallbacks[1]
end

local parser_root_dir = resolve_treesitter_root()
local parser_install_dir = parser_root_dir .. "/parser"
vim.opt.runtimepath:append(parser_root_dir)
vim.opt.runtimepath:append(parser_install_dir)

local function patch_python_fstring_highlighting()
  if not (vim.treesitter and vim.treesitter.query) then
    return
  end

  local query = vim.treesitter.query
  if type(query.get_files) ~= "function" or type(query.set) ~= "function" then
    return
  end

  local files = query.get_files("python", "highlights")
  if type(files) ~= "table" or #files == 0 then
    return
  end

  local base_query
  for _, path in ipairs(files) do
    if path:find("nvim%-treesitter/queries/python/highlights%.scm$") then
      local ok_read, lines = pcall(vim.fn.readfile, path)
      if ok_read and type(lines) == "table" and #lines > 0 then
        base_query = table.concat(lines, "\n")
        break
      end
    end
  end

  if not base_query or base_query == "" then
    return
  end

  local patched_query, replacements = base_query:gsub("%(interpolation%)%s*@none%s*\n", "")
  if replacements == 0 then
    return
  end

  pcall(query.set, "python", "highlights", patched_query)
end

patch_python_fstring_highlighting()

configs.setup({
  parser_install_dir = parser_install_dir,
  ensure_installed = {
    "lua",
    "c",
    "cpp",
    "python",
    "javascript",
    "typescript",
    "json",
    "yaml",
    "html",
    "css",
    "bash",
    "rust",
    "proto",
  },
  auto_install = false,
  sync_install = true,
  highlight = {
    enable = true,
    disable = { "cmake" },
  },
  indent = {
    enable = true,
    disable = { "cmake" },
  },
})
