local uv = vim.uv or vim.loop

-- Don't pass messages to |ins-completion-menu|
vim.opt.shortmess:append("c")

-- Prevent "Hit Enter to continue" prompts for many messages
vim.opt.shortmess:append("A")
vim.opt.shortmess:append("I")
vim.opt.shortmess:append("O")
vim.opt.shortmess:append("T")

local function path_exists(path)
  return type(path) == "string" and uv.fs_stat(path) ~= nil
end

local function delete_path(path)
  if type(path) ~= "string" or path == "" then
    return
  end
  if vim.fn.isdirectory(path) == 1 then
    vim.fn.delete(path, "rf")
    return
  end
  if vim.fn.filereadable(path) == 1 then
    vim.fn.delete(path)
  end
end

local function read_json(path)
  local ok_read, lines = pcall(vim.fn.readfile, path)
  if not ok_read or type(lines) ~= "table" or #lines == 0 then
    return nil
  end
  local ok_decode, decoded = pcall(vim.json.decode, table.concat(lines, "\n"))
  if ok_decode and type(decoded) == "table" then
    return decoded
  end
  return nil
end

local function write_json(path, value)
  local ok_encode, encoded = pcall(vim.json.encode, value)
  if not ok_encode or type(encoded) ~= "string" then
    return
  end
  vim.fn.mkdir(vim.fn.fnamemodify(path, ":h"), "p")
  pcall(vim.fn.writefile, { encoded }, path)
end

local function count_directories(path)
  if vim.fn.isdirectory(path) ~= 1 then
    return 0
  end
  local scan = uv.fs_scandir(path)
  if not scan then
    return 0
  end
  local count = 0
  while true do
    local name, t = uv.fs_scandir_next(scan)
    if not name then
      break
    end
    if t == "directory" then
      count = count + 1
    end
  end
  return count
end

local function host_fingerprint()
  local uname = uv.os_uname() or {}
  local ver = vim.version()
  return {
    sysname = uname.sysname or "",
    machine = uname.machine or "",
    release = uname.release or "",
    nvim = string.format("%d.%d.%d", ver.major, ver.minor, ver.patch),
    config = vim.fn.stdpath("config"),
    data = vim.fn.stdpath("data"),
  }
end

local function same_fingerprint(a, b)
  if type(a) ~= "table" or type(b) ~= "table" then
    return false
  end
  return a.sysname == b.sysname
      and a.machine == b.machine
      and a.release == b.release
      and a.nvim == b.nvim
      and a.config == b.config
      and a.data == b.data
end

local function reset_portability_caches_if_needed()
  local state_dir = vim.fn.stdpath("state")
  local marker = state_dir .. "/portable-host.json"
  local current = host_fingerprint()
  local previous = read_json(marker)

  if not same_fingerprint(previous, current) then
    delete_path(vim.fn.stdpath("cache") .. "/luac")
    delete_path(state_dir .. "/lazy/pkg-cache.lua")
    delete_path(state_dir .. "/lazy/state.json")
    delete_path(vim.fn.stdpath("config") .. "/plugin/packer_compiled.lua")
  end

  write_json(marker, current)
end

local function try_clone_lazy(path)
  if vim.fn.executable("git") ~= 1 then
    return false, "git is not installed"
  end

  local cmd = {
    "git",
    "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    path,
  }

  if vim.system then
    local result = vim.system(cmd, { text = true, timeout = 12000 }):wait()
    if result.code == 0 then
      return true
    end
    local msg = (result.stderr or result.stdout or "git clone failed"):gsub("%s+$", "")
    return false, msg
  end

  local output = vim.fn.system(cmd)
  if vim.v.shell_error == 0 then
    return true
  end
  return false, type(output) == "string" and output:gsub("%s+$", "") or "git clone failed"
end

local function setup_lazy_bootstrap()
  local data_lazy_root = vim.fn.stdpath("data") .. "/lazy"
  local offline_lazy_root = vim.fn.stdpath("config") .. "/pack/offline/start"

  local data_count = count_directories(data_lazy_root)
  local offline_count = count_directories(offline_lazy_root)
  local lazy_root = data_count >= offline_count and data_lazy_root or offline_lazy_root

  local candidates = {
    lazy_root .. "/lazy.nvim",
    data_lazy_root .. "/lazy.nvim",
    offline_lazy_root .. "/lazy.nvim",
  }

  local lazypath
  for _, candidate in ipairs(candidates) do
    if path_exists(candidate) then
      lazypath = candidate
      break
    end
  end

  if not lazypath then
    local allow_bootstrap = vim.env.NVIM_ALLOW_LAZY_BOOTSTRAP == "1"
    if allow_bootstrap then
      local clone_target = data_lazy_root .. "/lazy.nvim"
      vim.fn.mkdir(data_lazy_root, "p")
      local cloned, clone_err = try_clone_lazy(clone_target)
      if cloned and path_exists(clone_target) then
        lazy_root = data_lazy_root
        lazypath = clone_target
      else
        return false, lazy_root, clone_err
      end
    else
      return false, lazy_root, "set NVIM_ALLOW_LAZY_BOOTSTRAP=1 to allow cloning lazy.nvim"
    end
  end

  vim.opt.rtp:prepend(lazypath)
  return true, lazy_root
end

reset_portability_caches_if_needed()
local lazy_ok, lazy_root, lazy_err = setup_lazy_bootstrap()
vim.g.__portable_lazy_root = lazy_root

vim.g.mapleader = " "

require("core.session").setup()
require("core.shada")
require("core.options")
require("core.clipboard")
require("core.keymaps")
require("core.autocmds")
require("core.highlight_strings")
require("core.recent_files").setup()
require("core.git_jump").setup()
require("core.git_diff").setup()

if lazy_ok then
  local ok_plugins, plugins_err = pcall(require, "plugins")
  if not ok_plugins then
    vim.notify("plugins failed to load: " .. plugins_err, vim.log.levels.ERROR)
  end
else
  vim.schedule(function()
    local msg = "lazy.nvim is unavailable. Neovim started without plugins."
    if lazy_err and lazy_err ~= "" then
      msg = msg .. " (" .. lazy_err .. ")"
    end
    vim.notify(msg, vim.log.levels.WARN)
  end)
end

vim.api.nvim_create_autocmd({ "InsertLeave", "TextChanged", "TextChangedI" }, {
  pattern = "*",
  callback = function(args)
    local bo = vim.bo[args.buf]
    if bo.filetype == "oil" and args.event ~= "InsertLeave" then
      return
    end
    if bo.modified and bo.modifiable then
      vim.cmd("silent! wall")
    end
  end,
})

local ok, err = pcall(require, "userinit")
if not ok then
  vim.notify("userinit.lua failed to load: " .. err, vim.log.levels.ERROR)
end
