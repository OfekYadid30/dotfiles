-- gd / <leader>gd inside git views (fugitive status, :Git diff/show/log -p,
-- fugitive:// blobs from :Gdiffsplit, :Git blame, gitsigns:// buffers).
-- Always lands in the REAL worktree file, never in a temp/fugitive:// buffer.
-- When the view shows a different version than the worktree (staged content,
-- an old commit, ...) the line is remapped onto the current file with a diff.
local M = {}

local GIT_FILETYPES = { fugitive = true, git = true, fugitiveblame = true }
local VIRTUAL_PATTERNS = { "^fugitive://", "^gitsigns://" }

local function is_virtual_name(name)
  for _, pat in ipairs(VIRTUAL_PATTERNS) do
    if name:match(pat) then
      return true
    end
  end
  return false
end

function M.is_git_view(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  if not vim.api.nvim_buf_is_valid(bufnr) then
    return false
  end
  return GIT_FILETYPES[vim.bo[bufnr].filetype] or is_virtual_name(vim.api.nvim_buf_get_name(bufnr))
end

-- ---------------------------------------------------------------------------
-- git helpers

local function git(cwd, args)
  local cmd = vim.list_extend({ "git" }, args)
  local res = vim.system(cmd, { cwd = cwd, text = true }):wait()
  if res.code ~= 0 then
    return nil
  end
  return res.stdout or ""
end

local function split_lines(text)
  local lines = vim.split(text, "\n", { plain = true })
  if lines[#lines] == "" then
    table.remove(lines)
  end
  return lines
end

local function toplevel_from_gitdir(gitdir)
  local out = git(nil, { "--git-dir=" .. gitdir, "rev-parse", "--show-toplevel" })
  if out and vim.trim(out) ~= "" then
    return vim.trim(out)
  end
  if gitdir:match("/%.git/?$") then
    return (gitdir:gsub("/%.git/?$", ""))
  end
  return nil
end

local function worktree(bufnr)
  local ok, tree = pcall(vim.fn.FugitiveWorkTree, bufnr)
  if ok and type(tree) == "string" and tree ~= "" then
    return tree
  end
  local ok_state, state = pcall(vim.fn["fugitive#Result"], bufnr)
  if ok_state and type(state) == "table" and type(state.git_dir) == "string" and state.git_dir ~= "" then
    local top = toplevel_from_gitdir(state.git_dir)
    if top then
      return top
    end
  end
  local out = git(vim.fn.getcwd(), { "rev-parse", "--show-toplevel" })
  return out and vim.trim(out) ~= "" and vim.trim(out) or nil
end

local function real_file_lines(path)
  local buf = vim.fn.bufnr(path)
  if buf > 0 and vim.api.nvim_buf_is_loaded(buf) then
    return vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  end
  local ok, lines = pcall(vim.fn.readfile, path)
  return ok and lines or {}
end

-- ---------------------------------------------------------------------------
-- line remapping: position `lnum` in `old_lines` -> position in `new_lines`

local diff_fn = (vim.text and vim.text.diff) or vim.diff

local function map_line(old_lines, new_lines, lnum)
  local a = table.concat(old_lines, "\n") .. "\n"
  local b = table.concat(new_lines, "\n") .. "\n"
  local hunks = diff_fn(a, b, { result_type = "indices", algorithm = "histogram" }) or {}

  local offset = 0
  for _, h in ipairs(hunks) do
    local start_a, count_a, start_b, count_b = h[1], h[2], h[3], h[4]
    if count_a == 0 then
      -- pure insertion after old line start_a
      if lnum <= start_a then
        break
      end
      offset = offset + count_b
    else
      if lnum < start_a then
        break
      end
      if lnum < start_a + count_a then
        if count_b == 0 then
          return start_b + 1 -- lines deleted: land right after the deletion
        end
        return start_b + math.min(lnum - start_a, count_b - 1)
      end
      offset = offset + count_b - count_a
    end
  end
  return lnum + offset
end

-- Map a line of some blob (by sha) onto the worktree file.
local function map_from_blob(tree, relpath, sha, lnum)
  if not lnum or not sha or sha:match("^0+$") then
    return lnum
  end
  local wt_hash = git(tree, { "hash-object", "--", relpath })
  if wt_hash and vim.startswith(vim.trim(wt_hash), sha) then
    return lnum -- the diff's "new" side IS the worktree content
  end
  local content = git(tree, { "cat-file", "-p", sha })
  if not content then
    return lnum
  end
  return map_line(split_lines(content), real_file_lines(tree .. "/" .. relpath), lnum)
end

-- ---------------------------------------------------------------------------
-- diff parsing

local function getter(bufnr)
  return function(n)
    if n < 1 then
      return nil
    end
    return vim.api.nvim_buf_get_lines(bufnr, n - 1, n, false)[1]
  end
end

-- If `lnum` is inside a hunk, return { header = <@@ lnum>, lnum = <new-side lnum>, col = <col> }.
local function hunk_position(get, lnum, cursor_col)
  local n = lnum
  local line = get(n)
  while line and not line:match("^@@") do
    if not line:match("^[ +%-\\]") then
      return nil
    end
    n = n - 1
    line = get(n)
  end
  if not line then
    return nil
  end

  local ats = line:match("^(@@+)")
  local ncols = #ats - 1 -- 1 for normal diffs, 2+ for combined (merge) diffs
  local new_start = tonumber(line:match(" %+(%d+)")) or 1

  local new_lnum = new_start
  for i = n + 1, lnum - 1 do
    local prefix = (get(i) or ""):sub(1, ncols)
    if not prefix:match("^\\") and not prefix:find("-", 1, true) then
      new_lnum = new_lnum + 1
    end
  end

  local col = 0
  if lnum ~= n then
    col = math.max(cursor_col - ncols, 0)
  end
  return { header = n, lnum = math.max(new_lnum, 1), col = col }
end

local function unquote(path)
  path = path:gsub("\t.*$", "")
  local quoted = path:match('^"(.*)"$')
  return quoted or path
end

-- `a/foo`, `b/foo`, `i/foo`, `w/foo` (mnemonicprefix), or no prefix at all.
local function strip_prefix(tree, path)
  local stripped = path:match("^[^/]+/(.+)$")
  if stripped and vim.uv.fs_stat(tree .. "/" .. stripped) then
    return stripped
  end
  if vim.uv.fs_stat(tree .. "/" .. path) then
    return path
  end
  return stripped or path
end

-- File headers for the diff containing line `from`.
local function diff_file_header(get, from)
  local n = from
  local line = get(n)
  while line and not line:match("^diff ") do
    n = n - 1
    line = get(n)
  end
  if not line then
    return nil
  end

  local info = { diff_line = line }
  n = n + 1
  line = get(n)
  while line and not line:match("^@@") and not line:match("^diff ") do
    info.index = info.index or line:match("^index [%x,]+%.%.(%x+)")
    info.minus = info.minus or line:match("^%-%-%- (.+)$")
    info.plus = info.plus or line:match("^%+%+%+ (.+)$")
    n = n + 1
    line = get(n)
  end
  return info
end

local function header_relpath(tree, info)
  local path
  if info.plus and info.plus ~= "/dev/null" then
    path = unquote(info.plus)
  elseif info.minus and info.minus ~= "/dev/null" then
    path = unquote(info.minus)
  else
    path = info.diff_line:match("^diff %-%-git .- b/(.+)$")
        or info.diff_line:match("^diff %-%-cc (.+)$")
        or info.diff_line:match("^diff %-%-combined (.+)$")
    if not path then
      return nil
    end
    return unquote(path)
  end
  return strip_prefix(tree, path)
end

-- ---------------------------------------------------------------------------
-- resolvers: each returns { path = <abs real path>, lnum = <int|nil>, col = <int> } or nil, err

-- :Git diff / :Git show / :Git log -p / fugitive:// commit objects
local function resolve_diff_buffer(bufnr, lnum, col)
  local tree = worktree(bufnr)
  if not tree then
    return nil, "not inside a git worktree"
  end
  local get = getter(bufnr)
  local hunk = hunk_position(get, lnum, col)
  local info = diff_file_header(get, hunk and hunk.header or lnum)
  if not info then
    return nil, "no diff under cursor"
  end
  local relpath = header_relpath(tree, info)
  if not relpath then
    return nil, "could not determine file from diff header"
  end

  local target = { path = tree .. "/" .. relpath, col = 0 }
  if hunk then
    target.lnum = map_from_blob(tree, relpath, info.index, hunk.lnum)
    target.col = hunk.col
  end
  return target
end

-- :Git status buffer (filetype fugitive), including inline `=` diffs
local function resolve_status_buffer(bufnr, lnum, col)
  local tree = worktree(bufnr)
  if not tree then
    return nil, "not inside a git worktree"
  end
  local get = getter(bufnr)
  local hunk = hunk_position(get, lnum, col)

  local file_lnum = lnum
  if hunk then
    file_lnum = hunk.header - 1
    while (get(file_lnum) or ""):match("^[ @+%-\\]") do
      file_lnum = file_lnum - 1
    end
  end

  local text = (get(file_lnum) or ""):match("^[A-Z?] (.+)$")
  if not text then
    return nil, "no file under cursor"
  end

  local heading
  for n = file_lnum - 1, 1, -1 do
    local l = get(n) or ""
    if l == "" then
      break
    end
    heading = l:match("^(%u%l+.-) %(%d+%+?%)$")
    if heading then
      break
    end
  end

  -- fugitive keeps the parsed file list; `relative[1]` is the new name on renames
  local relpath
  local status = vim.b[bufnr].fugitive_status
  local entry = heading and status and status.files and status.files[heading] and status.files[heading][text]
  if entry and entry.relative and entry.relative[1] then
    relpath = entry.relative[1]
  else
    relpath = text:match(" %-> (.+)$") or text
  end

  local target = { path = tree .. "/" .. relpath, col = 0 }
  if hunk then
    target.col = hunk.col
    target.lnum = hunk.lnum
    if heading and heading:match("^Staged") then
      -- staged hunks are relative to the index, remap onto the worktree file
      local index_content = git(tree, { "show", ":" .. relpath })
      if index_content then
        target.lnum = map_line(split_lines(index_content), real_file_lines(target.path), hunk.lnum)
      end
    end
  end
  return target
end

local function real_path_of_virtual(name)
  if name:match("^fugitive://") then
    local ok, real = pcall(vim.fn.FugitiveReal, name)
    if ok and type(real) == "string" and real ~= "" and not is_virtual_name(real) then
      return real
    end
    return nil
  end
  -- gitsigns://<gitdir>//<rev>:<relpath>
  local gitdir, relpath = name:match("^gitsigns://(.-)//[^:]*:(.+)$")
  if gitdir then
    local tree = toplevel_from_gitdir(gitdir)
    return tree and (tree .. "/" .. relpath) or nil
  end
  return nil
end

-- fugitive:// / gitsigns:// blob (e.g. left side of :Gdiffsplit)
local function resolve_blob_buffer(bufnr, lnum, col)
  local real = real_path_of_virtual(vim.api.nvim_buf_get_name(bufnr))
  if not real then
    return nil, "could not resolve real file"
  end
  local old_lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  return { path = real, lnum = map_line(old_lines, real_file_lines(real), lnum), col = col }
end

-- :Git blame: line N of the blame window == line N of the blamed buffer
local function resolve_blame_buffer(bufnr, lnum)
  local ok, state = pcall(vim.fn["fugitive#Result"], bufnr)
  local origin = ok and type(state) == "table" and tonumber(state.origin_bufnr) or -1
  if origin > 0 and vim.api.nvim_buf_is_valid(origin) then
    local name = vim.api.nvim_buf_get_name(origin)
    if is_virtual_name(name) then
      return resolve_blob_buffer(origin, lnum, 0)
    end
    return { path = name, lnum = lnum, col = 0 }
  end
  local tree = worktree(bufnr)
  local file = ok and type(state) == "table" and state.blame_file
  if tree and type(file) == "string" and file ~= "" then
    return { path = tree .. "/" .. file, lnum = lnum, col = 0 }
  end
  return nil, "could not resolve blamed file"
end

function M.resolve(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  local cursor = vim.api.nvim_win_get_cursor(0)
  local lnum, col = cursor[1], cursor[2]
  local ft = vim.bo[bufnr].filetype

  if ft == "fugitive" then
    return resolve_status_buffer(bufnr, lnum, col)
  elseif ft == "fugitiveblame" then
    return resolve_blame_buffer(bufnr, lnum)
  elseif ft == "git" then
    return resolve_diff_buffer(bufnr, lnum, col)
  elseif is_virtual_name(vim.api.nvim_buf_get_name(bufnr)) then
    return resolve_blob_buffer(bufnr, lnum, col)
  end
  return nil, "not a git view"
end

-- ---------------------------------------------------------------------------
-- jumping

function M.jump(opts)
  opts = opts or {}
  local target, err = M.resolve()
  if not target then
    vim.notify("git jump: " .. (err or "nothing to jump to"), vim.log.levels.WARN)
    return
  end
  if not vim.uv.fs_stat(target.path) then
    vim.notify("git jump: file does not exist in worktree: " .. target.path, vim.log.levels.WARN)
    return
  end

  local last = math.max(#real_file_lines(target.path), 1)
  local pos = { line = math.min(math.max(target.lnum or 1, 1), last) - 1, character = target.col or 0 }
  local location = { uri = vim.uri_from_fname(target.path), range = { start = pos, ["end"] = pos } }

  -- windows like :Git blame have 'winfixbuf'; they can't show the file themselves
  if opts.other_pane or vim.wo.winfixbuf then
    require("core.window_utils").jump_to_location_in_other_pane(location, "utf-8")
  else
    vim.lsp.util.show_document(location, "utf-8", { focus = true })
  end
end

local function attach(bufnr)
  if vim.b[bufnr].git_jump_attached or not M.is_git_view(bufnr) then
    return
  end
  vim.b[bufnr].git_jump_attached = true
  vim.keymap.set("n", "gd", function()
    M.jump()
  end, { buffer = bufnr, silent = true, desc = "Git: go to real file" })
  vim.keymap.set("n", "<leader>gd", function()
    M.jump({ other_pane = true })
  end, { buffer = bufnr, silent = true, desc = "Git: go to real file (other pane)" })
end

function M.setup()
  local group = vim.api.nvim_create_augroup("GitJump", { clear = true })
  vim.api.nvim_create_autocmd({ "FileType", "BufWinEnter" }, {
    group = group,
    callback = function(args)
      attach(args.buf)
    end,
  })
end

return M
