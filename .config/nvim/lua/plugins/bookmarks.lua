
local bookmarks = require("bookmarks")
local session = require("core.session")
local fn = vim.fn

local base_dir = fn.stdpath("data") .. "/bookmarks_per_dir"
fn.mkdir(base_dir, "p")

local cwd = session.get_root() or fn.getcwd()
local safe_name = cwd:gsub("[/:\\]", "_"):gsub("%s+", "_")
local db_dir = string.format("%s/%s", base_dir, safe_name)
fn.mkdir(db_dir, "p")

local colors = require("themes.western").colors

bookmarks.setup({
  persist = { enabled = true },
  db_dir = db_dir,
  backup = {
    enabled = true,
    dir = db_dir .. "/backup",
    delay = 5,
  },

  signs = {
    mark = {
      icon = "󰃁",
      color = colors.bookmark_sign_icon_fg,
      line_bg = "",
    },
    desc_format = function(bookmark)
      if bookmark.name then
        return string.format("  󰃁 %s  ", bookmark.name)
      else
        return "Bookmark here"
      end
    end,
  },

  highlight = {
    name = "BookmarkSign",
    style = {
      fg = colors.bookmark_highlight_text_fg,
      bg = colors.bookmark_highlight_bg,
    },
  },

  treeview = {
    window_split_dimension = 80,
    side = "right",

    render_bookmark = function(node)
      local loc = node.location
      local filename = require("bookmarks.domain.location").get_file_name(loc)
      local live_line = require("bookmarks_live").current_line_for_node(node)
      local name = node.name or ""

      if name ~= "" then
        return string.format("%s:%d (%s)", filename, live_line, name)
      else
        return string.format("%s:%d", filename, live_line)
      end
    end,

    keymap = (function()
      local km = {}
      for _, key in ipairs({
        ".", "R", "m", "o", "<localleader>k", "<localleader>j",
        "D", "x", "c", "u", "t", "+", "=", "-", "<C-o>", "<ESC>",
      }) do
        km[key] = { action = function() end, desc = "" }
      end

      km["q"] = { action = "quit", desc = "Close tree view" }
      km["?"] = { action = "show_help", desc = "Show help" }
      km["J"] = { action = "move_down", desc = "Move node down" }
      km["K"] = { action = "move_up", desc = "Move node up" }
      km["r"] = { action = "rename", desc = "Rename node" }
      km["i"] = { action = "show_info", desc = "Show node info" }
      km["dd"] = { action = "cut", desc = "Cut node" }
      km["yy"] = { action = "copy", desc = "Copy node" }
      km["a"] = { action = "create_list", desc = "Create list (dir)" }
      km["<CR>"] = { action = "toggle", desc = "Expand / collapse or jump" }
      km["p"] = { action = "paste", desc = "Paste below" }
      km["P"] = {
        action = function() vim.api.nvim_feedkeys("pjK", "t", false) end,
        desc = "Paste above",
      }
      km["H"] = { action = "level_up", desc = "Navigate up one level" }
      km["L"] = { action = "set_root", desc = "Set current list as active" }
      km["T"] = {
        action = function()
          vim.api.nvim_feedkeys(string.rep("H", 64), "T", false)
        end,
        desc = "Spam H (fast, safe climb)",
      }
      km["m"] = { action = "set_active", desc = "Set list active" }
      km["<leader>ml"] = { action = "quit", desc = "Close tree view" }

      return km
    end)(),
  },
})

local Service = require("bookmarks.domain.service")
local Repo = require("bookmarks.domain.repo")
local TreeView = require("bookmarks.tree")
local TreeCtx = require("bookmarks.tree.ctx")
local Sign = require("bookmarks.sign")

local function toggle_bookmark(opts)
  opts = opts or {}
  local name = opts.name or ""

  local ok, err = pcall(Service.toggle_mark, name)
  Sign.safe_refresh_signs()

  if not ok then
    vim.notify("Bookmarks: toggle failed — " .. tostring(err), vim.log.levels.ERROR)
  end
end

vim.api.nvim_create_user_command("BookmarksToggle", function(cmdargs)
  toggle_bookmark({ name = table.concat(cmdargs.fargs, " ") })
end, { nargs = "*" })

local function ensure_tree_context()
  local ctx = TreeCtx.get_ctx()
  if ctx and ctx.win and vim.api.nvim_win_is_valid(ctx.win) then
    return ctx
  end

  local ok, err = pcall(TreeView.toggle)
  if not ok then
    vim.notify("Bookmarks: failed to open tree view — " .. tostring(err), vim.log.levels.ERROR)
    return nil
  end

  return TreeCtx.get_ctx()
end

local function safe_get_parent_id(node_id)
  local ok, parent_id = pcall(Repo.get_parent_id, node_id)
  if not ok then
    return nil
  end
  return parent_id
end

local function expand_parent_lists(node_id)
  local seen = {}
  local current = node_id

  while current and not seen[current] do
    seen[current] = true
    local parent_id = safe_get_parent_id(current)
    if not parent_id then break end

    local parent = Repo.find_node(parent_id)
    if parent and parent.type == "list" and not parent.is_expanded then
      parent.is_expanded = true
      Repo.update_node(parent)
    end

    if parent_id == 0 then break end
    current = parent_id
  end
end

local function is_node_under_root(node_id, root_id)
  if root_id == 0 then return true end
  local current = node_id
  local visited = {}
  while current and current ~= 0 and not visited[current] do
    if current == root_id then
      return true
    end
    visited[current] = true
    current = safe_get_parent_id(current)
  end
  return false
end

local function focus_bookmark_in_tree()
  local bookmark = Service.find_bookmark_by_location()
  if not bookmark then
    vim.notify("Bookmarks: no bookmark at cursor to reveal", vim.log.levels.WARN)
    return
  end

  local ctx = ensure_tree_context()
  if not ctx then return end

  local parent_id = safe_get_parent_id(bookmark.id)
  if parent_id == nil then
    vim.notify("Bookmarks: unable to determine bookmark parent list", vim.log.levels.WARN)
    parent_id = 0
  end

  local root_id = ctx.lines_ctx and ctx.lines_ctx.root_id or 0
  local root_changed = false
  if parent_id ~= 0 and root_id ~= 0 and not is_node_under_root(bookmark.id, root_id) then
    Service.set_active_list(parent_id)
    root_changed = true
  end

  expand_parent_lists(bookmark.id)

  if root_changed then
    TreeView.refresh(parent_id)
  else
    TreeView.refresh()
  end

  ctx = TreeCtx.get_ctx()
  if not ctx or not ctx.lines_ctx or not ctx.lines_ctx.lines_ctx then
    vim.notify("Bookmarks: tree view is not ready", vim.log.levels.WARN)
    return
  end

  local target_line
  for idx, line_ctx in ipairs(ctx.lines_ctx.lines_ctx) do
    if line_ctx.id == bookmark.id then
      target_line = idx
      break
    end
  end

  if not target_line then
    vim.notify("Bookmarks: bookmark is not visible in the tree", vim.log.levels.WARN)
    return
  end

  if ctx.win and vim.api.nvim_win_is_valid(ctx.win) then
    vim.api.nvim_set_current_win(ctx.win)
    vim.api.nvim_win_set_cursor(ctx.win, { target_line, 0 })
    vim.cmd("normal! zz")
  end
end

local M_live = {}
local ns_bookmarks_live = vim.api.nvim_create_namespace("bookmarks_live")
local Live = {
  marks = {},
}

local function get_bufnr_from_location(loc)
  if loc and loc.bufnr and vim.api.nvim_buf_is_loaded(loc.bufnr) then
    return loc.bufnr
  end
  if loc and (loc.path or loc.filepath) then
    local path = loc.path or loc.filepath
    local bufnr = vim.fn.bufnr(path, true)
    if bufnr > 0 then return bufnr end
  end
  return nil
end

local function node_key(node)
  local loc = node.location or {}
  local path = loc.path or loc.filepath or ""
  local line = loc.line or 0
  local name = node.name or ""
  return table.concat({ path, tostring(line), name }, "::")
end

local function ensure_extmark_for_node(node)
  local loc = node.location
  if not loc then return end
  local bufnr = get_bufnr_from_location(loc)
  if not bufnr then return end

  Live.marks[bufnr] = Live.marks[bufnr] or {}
  local key = node_key(node)
  local id = Live.marks[bufnr][key]

  if not id then
    local row = math.max((loc.line or 1) - 1, 0)
    local ok, new_id = pcall(vim.api.nvim_buf_set_extmark, bufnr, ns_bookmarks_live, row, 0, {})
    if ok and new_id then
      Live.marks[bufnr][key] = new_id
    end
  end
end

local function current_line_for_node(node)
  local loc = node.location
  if not loc then return node.line or 1 end

  local bufnr = get_bufnr_from_location(loc)
  if not bufnr then
    return loc.line or 1
  end

  Live.marks[bufnr] = Live.marks[bufnr] or {}
  local key = node_key(node)
  local id = Live.marks[bufnr][key]

  if id then
    local pos = vim.api.nvim_buf_get_extmark_by_id(bufnr, ns_bookmarks_live, id, {})
    if pos and pos[1] then
      return (pos[1] + 1)
    end
  end

  ensure_extmark_for_node(node)
  id = Live.marks[bufnr][key]
  if id then
    local pos = vim.api.nvim_buf_get_extmark_by_id(bufnr, ns_bookmarks_live, id, {})
    if pos and pos[1] then
      return (pos[1] + 1)
    end
  end

  return loc.line or 1
end

package.loaded["bookmarks_live"] = M_live
M_live.current_line_for_node = current_line_for_node
M_live.ensure_extmark_for_node = ensure_extmark_for_node

local function fetch_all_marks()
  local ok, S = pcall(require, "bookmarks.domain.service")
  if not ok then return {} end
  local candidates = {
    "list_all_marks",
    "list_marks",
    "get_all_marks",
    "get_all",
    "all",
  }
  for _, name in ipairs(candidates) do
    local f = S[name]
    if type(f) == "function" then
      local ok2, res = pcall(f)
      if ok2 and type(res) == "table" then
        return res
      end
    end
  end
  return {}
end

local function refresh_once()
  local ok_sign, SignMod = pcall(require, "bookmarks.sign")
  if not ok_sign then return end

  local all = fetch_all_marks()
  for _, mark in ipairs(all) do
    if mark and mark.location then
      ensure_extmark_for_node(mark)
      local live_line = current_line_for_node(mark)
      local loc = vim.tbl_extend("force", {}, mark.location)
      loc.line = live_line
      pcall(SignMod.place_sign, loc)
    end
  end
end

local refresh_timer = vim.loop.new_timer()
refresh_timer:start(0, 300, vim.schedule_wrap(refresh_once))

vim.api.nvim_create_autocmd({ "VimLeavePre", "ExitPre" }, {
  callback = function()
    if refresh_timer and not refresh_timer:is_closing() then
      refresh_timer:stop()
      refresh_timer:close()
    end
  end,
})

local map = vim.keymap.set

map("n", "<leader>mm", function()
  toggle_bookmark()
end, { desc = "Bookmarks: Toggle at cursor" })

map("n", "<leader>mM", function()
  vim.ui.input({ prompt = "Bookmark name (leave empty to toggle): " }, function(input)
    toggle_bookmark({ name = input or "" })
  end)
end, { desc = "Bookmarks: Toggle (prompt name)" })

map("n", "<leader>mn", "<cmd>BookmarksGotoNext<cr>", { desc = "Next bookmark (global)" })
map("n", "<leader>mp", "<cmd>BookmarksGotoPrev<cr>", { desc = "Previous bookmark (global)" })
map("n", "<leader>mf", focus_bookmark_in_tree, { desc = "Bookmarks: focus tree on this bookmark" })

map("n", "<leader>ml", function()
  refresh_once()
  TreeView.toggle()

  local ctx = TreeCtx.get_ctx()
  if ctx and ctx.win and vim.api.nvim_win_is_valid(ctx.win) then
    vim.api.nvim_set_current_win(ctx.win)
    vim.cmd("wincmd L")
  end
end, { desc = "Open bookmarks tree (ascending order)" })
