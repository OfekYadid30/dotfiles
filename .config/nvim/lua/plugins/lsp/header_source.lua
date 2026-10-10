local window_utils = require("core.window_utils")
local session = require("core.session")

local M = {}

local SOURCE_EXTS = { "c", "cc", "cpp", "cxx", "c++", "m", "mm", "cu" }
local HEADER_EXTS = { "h", "hh", "hpp", "hxx", "h++" }

local SOURCE_DIRS = { "src", "source", "sources", "lib" }
local HEADER_DIRS = { "include", "inc", "headers", "header" }

local ROOT_MARKERS = {
  ".git",
  ".hg",
  ".svn",
  "compile_commands.json",
  "compile_flags.txt",
  "Makefile",
  "meson.build",
  "build.ninja",
}

local function to_set(list)
  local set = {}
  for _, item in ipairs(list) do
    set[item] = true
  end
  return set
end

local SOURCE_EXT_SET = to_set(SOURCE_EXTS)
local HEADER_EXT_SET = to_set(HEADER_EXTS)

local function is_file(path)
  local stat = vim.loop.fs_stat(path)
  return stat and stat.type == "file"
end

local function is_dir(path)
  local stat = vim.loop.fs_stat(path)
  return stat and stat.type == "directory"
end

local function get_ext(path)
  local ext = vim.fn.fnamemodify(path, ":e")
  if ext == "" then
    return nil
  end
  return string.lower(ext)
end

local function get_dir(path)
  return vim.fn.fnamemodify(path, ":h")
end

local function get_base_name(path)
  return vim.fn.fnamemodify(path, ":t:r")
end

local function target_exts_for_source(ext)
  if ext == "c" then
    return { "h", "hpp", "hh", "hxx", "h++" }
  end
  if ext == "cpp" or ext == "cc" or ext == "cxx" or ext == "c++" then
    return { "hpp", "h", "hh", "hxx", "h++" }
  end
  if ext == "m" or ext == "mm" or ext == "cu" then
    return { "h", "hpp", "hh", "hxx" }
  end
  return HEADER_EXTS
end

local function target_exts_for_header(ext)
  if ext == "h" then
    return { "c", "cpp", "cc", "cxx", "c++", "m", "mm", "cu" }
  end
  if ext == "hpp" or ext == "hh" or ext == "hxx" or ext == "h++" then
    return { "cpp", "cc", "cxx", "c++", "c", "m", "mm", "cu" }
  end
  return SOURCE_EXTS
end

local function find_in_dir(dir, base_name, exts)
  for _, ext in ipairs(exts) do
    local candidate = vim.fs.joinpath(dir, base_name .. "." .. ext)
    if is_file(candidate) then
      return candidate
    end
  end
  return nil
end

local function split_path(path)
  return vim.split(path, "/", { plain = true, trimempty = true })
end

local function build_alt_dirs(dir, from_dirs, to_dirs)
  local segments = split_path(dir)
  if #segments == 0 then
    return {}
  end

  local has_leading = dir:sub(1, 1) == "/"
  local from_set = to_set(from_dirs)
  local alt_set = {}

  for idx, segment in ipairs(segments) do
    if from_set[segment] then
      for _, replacement in ipairs(to_dirs) do
        local new_segments = {}
        for i, seg in ipairs(segments) do
          new_segments[i] = (i == idx) and replacement or seg
        end
        local new_dir = table.concat(new_segments, "/")
        if has_leading then
          new_dir = "/" .. new_dir
        end
        alt_set[new_dir] = true
      end
    end
  end

  local results = {}
  for path in pairs(alt_set) do
    if path ~= dir then
      table.insert(results, path)
    end
  end
  table.sort(results)
  return results
end

local function find_project_root(start_dir)
  local root_dir = start_dir
  if not is_dir(root_dir) then
    root_dir = session.get_root() or vim.fn.getcwd()
  end

  if vim.fs and vim.fs.find then
    local found = vim.fs.find(ROOT_MARKERS, { path = root_dir, upward = true })[1]
    if found then
      return vim.fn.fnamemodify(found, ":h")
    end
    return root_dir
  end

  for _, marker in ipairs(ROOT_MARKERS) do
    local found = vim.fn.finddir(marker, root_dir .. ";")
    if found ~= "" then
      return vim.fn.fnamemodify(found, ":h")
    end
    found = vim.fn.findfile(marker, root_dir .. ";")
    if found ~= "" then
      return vim.fn.fnamemodify(found, ":h")
    end
  end

  return root_dir
end

local function search_project(root, names, limit)
  if vim.fs and vim.fs.find then
    return vim.fs.find(names, { path = root, type = "file", limit = limit })
  end

  local results = {}
  for _, name in ipairs(names) do
    local glob = vim.fs.joinpath(root, "**", name)
    local matches = vim.fn.glob(glob, false, true)
    for _, match in ipairs(matches) do
      table.insert(results, match)
      if limit and #results >= limit then
        return results
      end
    end
  end
  return results
end

local function score_candidate(path, current_dir)
  local dir = get_dir(path)
  local seg_a = split_path(current_dir)
  local seg_b = split_path(dir)
  local common = 0
  local limit = math.min(#seg_a, #seg_b)
  for i = 1, limit do
    if seg_a[i] ~= seg_b[i] then
      break
    end
    common = common + 1
  end
  local depth_diff = math.abs(#seg_a - #seg_b)
  return (common * 10) - depth_diff
end

local function pick_best_candidate(candidates, current_dir, current_path)
  local best
  local best_score = -math.huge
  for _, path in ipairs(candidates) do
    if path ~= current_path and is_file(path) then
      local score = score_candidate(path, current_dir)
      if score > best_score then
        best_score = score
        best = path
      end
    end
  end
  return best
end

function M.find_counterpart(path)
  if not path or path == "" then
    return nil, "No file loaded"
  end

  local ext = get_ext(path)
  if not ext then
    return nil, "File has no extension: " .. path
  end

  local is_source = SOURCE_EXT_SET[ext]
  local is_header = HEADER_EXT_SET[ext]
  if not (is_source or is_header) then
    return nil, "Not a source or header file: " .. path
  end

  local target_exts = is_source and target_exts_for_source(ext) or target_exts_for_header(ext)
  local dir = get_dir(path)
  local base_name = get_base_name(path)

  local found = find_in_dir(dir, base_name, target_exts)
  if found then
    return found
  end

  local alt_dirs
  if is_source then
    alt_dirs = build_alt_dirs(dir, SOURCE_DIRS, HEADER_DIRS)
  else
    alt_dirs = build_alt_dirs(dir, HEADER_DIRS, SOURCE_DIRS)
  end

  for _, alt_dir in ipairs(alt_dirs) do
    local alt_found = find_in_dir(alt_dir, base_name, target_exts)
    if alt_found then
      return alt_found
    end
  end

  local root = find_project_root(dir)
  local candidate_names = {}
  for _, target_ext in ipairs(target_exts) do
    table.insert(candidate_names, base_name .. "." .. target_ext)
  end

  local matches = search_project(root, candidate_names, 20)
  if #matches > 0 then
    local best = pick_best_candidate(matches, dir, path)
    if best then
      return best
    end
  end

  return nil, "No related source/header found for: " .. path
end

function M.open_counterpart(opts)
  opts = opts or {}
  if vim.bo.buftype ~= "" then
    vim.notify("Current buffer is not a file", vim.log.levels.WARN)
    return
  end

  local current_path = vim.fn.expand("%:p")
  local target_path, reason = M.find_counterpart(current_path)
  if not target_path then
    vim.notify(reason, vim.log.levels.WARN)
    return
  end

  if opts.other_pane then
    local source_win = vim.api.nvim_get_current_win()
    local info = window_utils.focus_closest_by_size({ ensure_target = true })
    if not info.target or not vim.api.nvim_win_is_valid(info.target) then
      vim.api.nvim_set_current_win(source_win)
      vim.notify("Could not find another window to open the file", vim.log.levels.WARN)
      return
    end
    vim.cmd("edit " .. vim.fn.fnameescape(target_path))
  else
    vim.cmd("edit " .. vim.fn.fnameescape(target_path))
  end
end

return M
