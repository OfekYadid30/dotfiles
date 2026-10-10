
local fn = vim.fn
local api = vim.api
local session = require("core.session")

local shada_root = fn.stdpath("state") .. "/shada_per_dir"
fn.mkdir(shada_root, "p")

local cwd = session.get_root() or fn.getcwd()
local safe_name = cwd:gsub("[/:\\]", "_"):gsub("%s+", "_")
local shada_path = string.format("%s/%s.shada", shada_root, safe_name)

vim.opt.shadafile = shada_path

local function write_shada_safely()
  local ok, err = pcall(vim.cmd.wshada)
  if not ok and err then
    vim.schedule(function()
      vim.notify("Failed to write shada: " .. err, vim.log.levels.WARN)
    end)
  end
end

if fn.filereadable(shada_path) == 1 then
  local ok, err = pcall(vim.cmd, "silent! rshada")
  if not ok and err then
    vim.schedule(function()
      vim.notify("Failed to read shada: " .. err, vim.log.levels.WARN)
    end)
  end
else
  write_shada_safely()
end


api.nvim_create_autocmd("VimLeavePre", {
  callback = write_shada_safely,
})
