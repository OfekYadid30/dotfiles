local M = {}

local uv = vim.uv or vim.loop
local session_root

local function normalize_path(path)
  if not path or path == "" then
    return nil
  end

  local abs = vim.fn.fnamemodify(path, ":p")
  if uv and uv.fs_realpath then
    local real = uv.fs_realpath(abs)
    if real and real ~= "" then
      return real
    end
  end
  return abs
end

local function resolve_startup_root()
  local argv = vim.fn.argv()
  if type(argv) == "table" and #argv > 0 then
    local first = argv[1]
    if type(first) == "string" and first ~= "" and first ~= "-" then
      local candidate = normalize_path(first)
      if candidate then
        if vim.fn.isdirectory(candidate) == 1 then
          return candidate
        end

        local parent = normalize_path(vim.fn.fnamemodify(candidate, ":h"))
        if parent and vim.fn.isdirectory(parent) == 1 then
          return parent
        end
      end
    end
  end

  return normalize_path(vim.fn.getcwd())
end

function M.setup()
  if session_root then
    return session_root
  end

  session_root = resolve_startup_root()
  if not session_root then
    return nil
  end

  vim.g.session_root_dir = session_root

  local current = normalize_path(vim.fn.getcwd())
  if current ~= session_root then
    pcall(vim.cmd.cd, vim.fn.fnameescape(session_root))
  end

  return session_root
end

function M.get_root()
  return session_root or vim.g.session_root_dir or M.setup()
end

return M
