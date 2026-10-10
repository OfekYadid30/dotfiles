local M = {}
local session = require("core.session")

local OUTPUT_LIMIT = 50
local STORE_LIMIT = 200
local SAVE_DELAY_MS = 500

local state = { entries = {} }
local loaded = false
local save_pending = false

local schedule_save

local function state_dir()
  return vim.fn.stdpath("state") .. "/recent_files_per_dir"
end

local function state_path()
  local cwd = session.get_root() or vim.fn.getcwd()
  local safe_name = cwd:gsub("[/:\\]", "_"):gsub("%s+", "_")
  return string.format("%s/%s.json", state_dir(), safe_name)
end

local function normalize_path(path)
  if not path or path == "" then
    return nil
  end
  local uv = vim.uv or vim.loop
  if uv and uv.fs_realpath then
    local real = uv.fs_realpath(path)
    if real and real ~= "" then
      return real
    end
  end
  return vim.fn.fnamemodify(path, ":p")
end

local function is_trackable(bufnr)
  if not vim.api.nvim_buf_is_valid(bufnr) then
    return false
  end
  if vim.bo[bufnr].buftype ~= "" then
    return false
  end
  local name = vim.api.nvim_buf_get_name(bufnr)
  if name == "" then
    return false
  end
  if vim.fn.filereadable(name) ~= 1 then
    return false
  end
  return true, normalize_path(name)
end

local function find_entry_index(path)
  for i, item in ipairs(state.entries) do
    if item.path == path then
      return i
    end
  end
  return nil
end

local function trim_entries()
  if #state.entries <= STORE_LIMIT then
    return
  end
  for i = #state.entries, STORE_LIMIT + 1, -1 do
    state.entries[i] = nil
  end
end

local function current_cursor()
  local ok, cursor = pcall(vim.api.nvim_win_get_cursor, 0)
  if not ok or type(cursor) ~= "table" then
    return 1, 1
  end
  local lnum = cursor[1] or 1
  local col = (cursor[2] or 0) + 1
  return lnum, col
end

local function read_shada_quote_marks()
  local shada_path = vim.o.shadafile
  if not shada_path or shada_path == "" or shada_path == "NONE" then
    return {}
  end
  if vim.fn.filereadable(shada_path) ~= 1 then
    return {}
  end

  local ok_read, mpack = pcall(vim.fn.readfile, shada_path, "b")
  if not ok_read then
    return {}
  end
  local ok_parse, objects = pcall(vim.fn.msgpackparse, mpack)
  if not ok_parse or type(objects) ~= "table" then
    return {}
  end

  local positions = {}
  for i = 1, #objects, 4 do
    if objects[i] == 10 then
      local ts = objects[i + 1]
      local entry = objects[i + 3]
      if type(entry) == "table" then
        local mark_name = entry.n or 34
        if mark_name == 34 then
          local file = entry.f
          if type(file) == "string" and file ~= "" then
            local path = normalize_path(file) or file
            if path then
              local lnum = tonumber(entry.l) or 1
              local col = tonumber(entry.c) or 0
              local existing = positions[path]
              if not existing or (type(ts) == "number" and ts > (existing.ts or 0)) then
                positions[path] = { lnum = lnum, col = col + 1, ts = ts or 0 }
              end
            end
          end
        end
      end
    end
  end

  return positions
end

local function seed_from_shada()
  local oldfiles = vim.v.oldfiles or {}
  if vim.tbl_isempty(oldfiles) then
    return
  end
  local positions = read_shada_quote_marks()
  local seen = {}

  for _, file in ipairs(oldfiles) do
    if vim.fn.filereadable(file) == 1 then
      local path = normalize_path(file)
      if path and not seen[path] then
        local pos = positions[path]
        state.entries[#state.entries + 1] = {
          path = path,
          lnum = (pos and pos.lnum) or 1,
          col = (pos and pos.col) or 1,
        }
        seen[path] = true
        if #state.entries >= STORE_LIMIT then
          break
        end
      end
    end
  end

  if #state.entries > 0 then
    schedule_save()
  end
end

local function load_state()
  if loaded then
    return
  end
  loaded = true

  local path = state_path()
  if vim.fn.filereadable(path) ~= 1 then
    seed_from_shada()
    return
  end

  local ok_read, lines = pcall(vim.fn.readfile, path)
  if not ok_read or not lines or vim.tbl_isempty(lines) then
    seed_from_shada()
    return
  end

  local ok_decode, decoded = pcall(vim.fn.json_decode, table.concat(lines, "\n"))
  if not ok_decode or type(decoded) ~= "table" then
    seed_from_shada()
    return
  end

  local entries = decoded.entries or decoded
  if type(entries) ~= "table" then
    seed_from_shada()
    return
  end

  local cleaned = {}
  local seen = {}
  for _, item in ipairs(entries) do
    if type(item) == "table" then
      local raw_path = item.path or item.filename
      if type(raw_path) == "string" then
        local path = normalize_path(raw_path)
        if path and not seen[path] and vim.fn.filereadable(path) == 1 then
          cleaned[#cleaned + 1] = {
            path = path,
            lnum = tonumber(item.lnum) or 1,
            col = tonumber(item.col) or 1,
          }
          seen[path] = true
          if #cleaned >= STORE_LIMIT then
            break
          end
        end
      end
    end
  end

  state.entries = cleaned
end

local function save_state()
  local path = state_path()
  vim.fn.mkdir(vim.fn.fnamemodify(path, ":h"), "p")

  local ok_encode, json = pcall(vim.fn.json_encode, {
    version = 1,
    entries = state.entries,
  })
  if not ok_encode or not json then
    return
  end

  pcall(vim.fn.writefile, { json }, path)
end

schedule_save = function()
  if save_pending then
    return
  end
  save_pending = true
  vim.defer_fn(function()
    save_pending = false
    save_state()
  end, SAVE_DELAY_MS)
end

function M.record(bufnr)
  local ok, path = is_trackable(bufnr)
  if not ok then
    return
  end
  load_state()

  local idx = find_entry_index(path)
  local lnum, col
  if idx then
    lnum = state.entries[idx].lnum
    col = state.entries[idx].col
    table.remove(state.entries, idx)
  else
    lnum, col = current_cursor()
  end

  table.insert(state.entries, 1, {
    path = path,
    lnum = lnum or 1,
    col = col or 1,
  })
  trim_entries()
  schedule_save()
end

function M.update_position(bufnr, opts)
  local ok, path = is_trackable(bufnr)
  if not ok then
    return
  end
  load_state()

  opts = opts or {}
  local lnum, col = current_cursor()

  local idx = find_entry_index(path)
  if idx then
    state.entries[idx].lnum = lnum
    state.entries[idx].col = col
  else
    table.insert(state.entries, 1, {
      path = path,
      lnum = lnum,
      col = col,
    })
  end

  trim_entries()
  if not opts.skip_save then
    schedule_save()
  end
end

function M.get_entries(limit)
  load_state()
  local max_items = limit or OUTPUT_LIMIT
  local current = normalize_path(vim.fn.expand("%:p"))
  local entries = {}

  for _, item in ipairs(state.entries) do
    if item.path ~= current and vim.fn.filereadable(item.path) == 1 then
      entries[#entries + 1] = {
        filename = item.path,
        lnum = item.lnum or 1,
        col = item.col or 1,
      }
      if #entries >= max_items then
        break
      end
    end
  end

  return entries
end

function M.flush()
  local bufnr = vim.api.nvim_get_current_buf()
  M.update_position(bufnr, { skip_save = true })
  save_state()
end

function M.setup()
  load_state()
  local group = vim.api.nvim_create_augroup("RecentFilesTracking", { clear = true })

  vim.api.nvim_create_autocmd("BufEnter", {
    group = group,
    callback = function(args)
      M.record(args.buf)
    end,
  })

  vim.api.nvim_create_autocmd("BufLeave", {
    group = group,
    callback = function(args)
      M.update_position(args.buf)
    end,
  })

  vim.api.nvim_create_autocmd("VimLeavePre", {
    group = group,
    callback = function()
      M.flush()
    end,
  })
end

return M
