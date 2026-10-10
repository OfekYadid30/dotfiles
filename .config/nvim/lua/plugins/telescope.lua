local M = {}

local window_utils

local telescope_ok, telescope = pcall(require, "telescope")
if not telescope_ok then
  vim.notify("telescope.nvim not found", vim.log.levels.ERROR)
  return
end

local builtin = require("telescope.builtin")
local actions = require("telescope.actions")
local action_state = require("telescope.actions.state")
local finders = require("telescope.finders")
local pickers = require("telescope.pickers")
local previewers = require("telescope.previewers")
local conf = require("telescope.config").values
local sorters = require("telescope.sorters")
local fzy = require("telescope.algos.fzy")
local make_entry = require("telescope.make_entry")
local utils = require("telescope.utils")
local recent_files = require("core.recent_files")
local session = require("core.session")
local uv = vim.uv or vim.loop

local path_sep = package.config:sub(1, 1)
local session_root = session.get_root() or vim.fn.getcwd()
local session_root_abs = vim.fn.fnamemodify(session_root, ":p")
if session_root_abs:sub(-1) ~= path_sep then
  session_root_abs = session_root_abs .. path_sep
end

local function recent_display_path(path)
  if not path or path == "" then
    return path
  end
  local abs = vim.fn.fnamemodify(path, ":p")
  if abs:sub(1, #session_root_abs) == session_root_abs then
    local rel = abs:sub(#session_root_abs + 1)
    if rel == "" then
      return abs
    end
    return rel
  end
  return abs
end

local function get_search_path()
  if vim.bo.filetype == "oil" then
    return require("oil").get_current_dir()
  end
  return vim.fn.expand("%:p:h")
end

local function is_git_worktree(path)
  local output = vim.fn.system({ "git", "-C", path, "rev-parse", "--is-inside-work-tree" })
  return vim.v.shell_error == 0 and output:match("^true") ~= nil
end

local function echo_bottom_warning(message)
  vim.api.nvim_echo({ { message, "WarningMsg" } }, false, {})
end

local rg_vimgrep_arguments = {
  "rg",
  "--color=never",
  "--no-heading",
  "--with-filename",
  "--line-number",
  "--column",
  "--smart-case",
  "--hidden",
  "--no-messages",
  "--glob", "!.git/**",
  "--glob", "!node_modules/**",
  "--glob", "!__pycache__/**",
  "--glob", "!build/**",
  "--glob", "!dist/**",
  "--glob", "!target/**",
  "--glob", "!*.o",
  "--glob", "!*.obj",
  "--glob", "!*.so",
  "--glob", "!*.dll",
  "--glob", "!*.exe",
  "--glob", "!*.lock",
  "--glob", "!*.jpg",
  "--glob", "!*.jpeg",
  "--glob", "!*.png",
  "--glob", "!*.gif",
  "--glob", "!*.zip",
  "--glob", "!*.tar",
  "--glob", "!*.gz",
}

local rg_find_files_command = {
  "rg",
  "--files",
  "--hidden",
  "--follow",
  "--no-messages",
  "--glob", "!.git/**",
  "--glob", "!node_modules/**",
  "--glob", "!__pycache__/**",
  "--glob", "!build/**",
  "--glob", "!dist/**",
  "--glob", "!target/**",
}

local default_buffer_previewer_maker = previewers.buffer_previewer_maker
local max_preview_size_bytes = 1024 * 1024

local function safe_buffer_previewer_maker(filepath, bufnr, opts)
  local resolved = vim.fn.expand(filepath)
  local stat = uv.fs_stat(resolved)
  if not stat or stat.type ~= "file" then
    return
  end
  if stat.size > max_preview_size_bytes then
    return
  end

  local fd = uv.fs_open(resolved, "r", 438)
  if not fd then
    return
  end
  local chunk = uv.fs_read(fd, 4096, 0)
  uv.fs_close(fd)
  if chunk and chunk:find("\0", 1, true) then
    return
  end

  pcall(default_buffer_previewer_maker, resolved, bufnr, opts)
end

telescope.setup({
  defaults = {
    vimgrep_arguments = rg_vimgrep_arguments,
    buffer_previewer_maker = safe_buffer_previewer_maker,
    layout_strategy = "vertical",
    layout_config = {
      vertical = {
        prompt_position = "bottom",
        preview_height = 0.6,
      },
      width = 0.99,
      height = 0.99,
    },
    sorting_strategy = "descending",
    file_ignore_patterns = {
      "%.o", "%.obj", "%.so", "%.dll", "%.exe",
      "%.jpg", "%.png", "%.gif", "%.zip", "%.tar", "%.gz",
      "%.lock",
      "node_modules/", "__pycache__/", "build/", "dist/", "target/", ".git/",
    },
    mappings = {
      i = {
        ["<C-l>"] = actions.send_selected_to_qflist + actions.open_qflist,
        ["<C-c>"] = function()
          vim.cmd("stopinsert")
        end,
      },
      n = {
        ["<C-l>"] = actions.send_selected_to_qflist + actions.open_qflist,
        ["<C-c>"] = actions.close,
      },
    },
  },
  pickers = {
    find_files = {
      find_command = rg_find_files_command,
      hidden = true,
    },
  },
})

vim.keymap.set("n", "<leader>ff", function()
  if not is_git_worktree(session_root) then
    echo_bottom_warning("not in a git repository (fallback to cwd search)")
    builtin.find_files({ cwd = session_root })
    return
  end
  builtin.git_files({ cwd = session_root })
end, { desc = "Telescope: Find git files" })

vim.keymap.set("n", "<leader>fF", function()
  builtin.find_files({ cwd = session_root })
end, { desc = "Telescope: Find files in cwd" })

vim.keymap.set("n", "<leader>fg", function()
  builtin.live_grep({ cwd = session_root })
end, { desc = "Telescope: Grep in cwd" })

vim.keymap.set("n", "<leader>fh", function()
  builtin.live_grep({
    search_dirs = { get_search_path() },
  })
end, { desc = "Telescope: Grep in current dir" })

vim.keymap.set("n", "<leader>fj", function()
  if vim.bo.filetype == "oil" then
    local oil = require("oil")
    local entry = oil.get_cursor_entry()
    if entry and entry.ft ~= "dir" then
      builtin.live_grep({
        search_dirs = { vim.fs.joinpath(oil.get_current_dir(), entry.name) },
      })
    else
      vim.notify("Cannot grep a directory", vim.log.levels.WARN)
    end
    return
  end
  builtin.live_grep({
    search_dirs = { vim.fn.expand("%:p") },
  })
end, { desc = "Telescope: Grep in current file" })

vim.keymap.set("n", "<leader>fd", function()
  builtin.find_files({
    cwd = get_search_path(),
  })
end, { desc = "Telescope: Find files in current dir" })

vim.keymap.set("n", "<leader>F", function()
  builtin.resume()
end, { desc = "Telescope: Resume last picker" })

local function show_letter_marks()
  local bufnr = vim.api.nvim_get_current_buf()
  local bufname = vim.api.nvim_buf_get_name(bufnr)
  local entries = {}

  local sources = {
    {
      items = vim.fn.getmarklist(bufnr),
      name_func = function(_, line)
        local ok, line_text = pcall(vim.api.nvim_buf_get_lines, bufnr, line - 1, line, false)
        return (ok and line_text[1]) or ""
      end,
    },
    {
      items = vim.fn.getmarklist(),
      name_func = function(mark)
        local ok, mark_info = pcall(vim.api.nvim_get_mark, mark, {})
        if not ok or not mark_info then
          return ""
        end
        return mark_info[4] or ""
      end,
    },
  }

  for _, source in ipairs(sources) do
    for _, mark_data in ipairs(source.items) do
      local mark = mark_data.mark:sub(2, 2)
      if mark:match("%a") then
        local _, lnum, col = unpack(mark_data.pos)
        local name = source.name_func(mark, lnum)
        table.insert(entries, {
          line = string.format("%s %6d %4d %s", mark, lnum, col - 1, name),
          lnum = lnum,
          col = col,
          filename = utils.path_expand(mark_data.file or bufname),
        })
      end
    end
  end

  if vim.tbl_isempty(entries) then
    vim.notify("No letter marks set", vim.log.levels.INFO)
    return
  end

  pickers
      .new({}, {
        prompt_title = "Letter Marks",
        finder = finders.new_table({
          results = entries,
          entry_maker = make_entry.gen_from_marks({}),
        }),
        previewer = conf.grep_previewer({}),
        sorter = conf.generic_sorter({}),
        push_cursor_on_edit = true,
        push_tagstack_on_edit = true,
      })
      :find()
end

vim.keymap.set("n", "<leader>fm", show_letter_marks, { desc = "Telescope: Letter marks" })

local function take_last(items, max_items)
  if #items <= max_items then
    return items
  end

  local start = #items - max_items + 1
  local recent = {}
  for i = start, #items do
    recent[#recent + 1] = items[i]
  end
  return recent
end

local function make_location_entry(entry)
  local display = string.format("%s:%d:%d", entry.filename, entry.lnum, entry.col)
  return {
    value = entry,
    display = display,
    ordinal = display,
    filename = entry.filename,
    lnum = entry.lnum,
    col = entry.col,
  }
end

local function make_recent_entry(entry)
  local display_path = recent_display_path(entry.filename)
  local display = string.format("%s:%d:%d", display_path, entry.lnum, entry.col)
  return {
    value = entry,
    display = display,
    ordinal = display_path,
    filename = entry.filename,
    lnum = entry.lnum,
    col = entry.col,
    index = entry.index,
  }
end

local function recent_files_sorter()
  local offset = -fzy.get_score_floor()
  return sorters.Sorter:new({
    discard = true,
    scoring_function = function(_, prompt, line, entry)
      if prompt == nil or prompt == "" then
        return (entry and entry.index) or 1
      end
      if not fzy.has_match(prompt, line) then
        return -1
      end
      local fzy_score = fzy.score(prompt, line)
      if fzy_score == fzy.get_score_min() then
        return 1
      end
      local score = 1 / (fzy_score + offset)
      if entry and entry.index then
        score = score + (entry.index * 1e-6)
      end
      return score
    end,
    highlighter = function(_, prompt, display)
      return fzy.positions(prompt, display)
    end,
  })
end

local function build_jumplist_entries(max_items)
  local jumps, cur = unpack(vim.fn.getjumplist())
  local entries = {}
  for idx, jump in ipairs(jumps) do
    if idx ~= cur then
      local filename = jump.filename
      if not filename or filename == "" then
        if jump.bufnr and jump.bufnr ~= 0 then
          filename = vim.api.nvim_buf_get_name(jump.bufnr)
        end
      end
      if filename and filename ~= "" and vim.fn.filereadable(filename) == 1 then
        table.insert(entries, {
          filename = filename,
          lnum = jump.lnum or 1,
          col = (jump.col or 0) + 1,
        })
      end
    end
  end

  return take_last(entries, max_items)
end

vim.keymap.set("n", "<leader>fl", function()
  local entries = build_jumplist_entries(30)
  if vim.tbl_isempty(entries) then
    vim.notify("Jumplist is empty", vim.log.levels.INFO)
    return
  end

  pickers.new({}, {
    prompt_title = "Jumplist",
    finder = finders.new_table({
      results = entries,
      entry_maker = make_location_entry,
    }),
    previewer = conf.grep_previewer({}),
    sorter = conf.generic_sorter({}),
    push_cursor_on_edit = true,
    push_tagstack_on_edit = true,
  }):find()
end, { desc = "Telescope: Jumplist" })

vim.keymap.set("n", "<leader>fo", function()
  local entries = recent_files.get_entries(30)
  if vim.tbl_isempty(entries) then
    vim.notify("No recent files found", vim.log.levels.INFO)
    return
  end

  for idx, entry in ipairs(entries) do
    entry.index = idx
  end

  pickers.new({}, {
    prompt_title = "Recent files",
    finder = finders.new_table({
      results = entries,
      entry_maker = make_recent_entry,
    }),
    previewer = conf.grep_previewer({}),
    sorter = recent_files_sorter(),
  }):find()
end, { desc = "Telescope: Recent files" })

local function is_quickfix_item(item)
  return type(item) == "table" and (item.filename or item.bufnr)
end

function M.show_list(items, opts)
  opts = opts or {}
  if not items or vim.tbl_isempty(items) then
    vim.notify(opts.empty_message or "No results", vim.log.levels.INFO)
    return false
  end
  opts.prompt_title = opts.prompt_title or "Results"

  local entry_maker = opts.entry_maker
  local qf_entry_maker
  if not entry_maker and is_quickfix_item(items[1]) then
    qf_entry_maker = make_entry.gen_from_quickfix({})
    entry_maker = qf_entry_maker
  end

  local previewer = opts.previewer
  if not previewer and qf_entry_maker then
    previewer = conf.qflist_previewer({})
  end

  local attach_mappings = opts.attach_mappings
  if not attach_mappings and type(opts.on_select) == "function" then
    attach_mappings = function(bufnr, map)
      local function open_selected()
        local selection = action_state.get_selected_entry()
        actions.close(bufnr)
        opts.on_select(selection)
      end
      map("i", "<CR>", open_selected)
      map("n", "<CR>", open_selected)
      return true
    end
  end

  pickers.new(opts, {
    finder = finders.new_table({
      results = items,
      entry_maker = entry_maker,
    }),
    sorter = conf.generic_sorter(opts),
    previewer = previewer,
    attach_mappings = attach_mappings,
  }):find()
  return true
end

function M.show_list_and_open_in_pane(items, opts)
  if not window_utils then
    window_utils = require("core.window_utils")
  end

  opts = opts or {}
  if not items or vim.tbl_isempty(items) then
    vim.notify(opts.empty_message or "No results", vim.log.levels.INFO)
    return false
  end
  opts.prompt_title = opts.prompt_title or "Select to Open"

  local function extract_location(entry)
    if type(entry) ~= "table" then
      return nil
    end
    if entry.location then
      return entry.location
    end
    if entry.uri or entry.targetUri then
      return entry
    end
    if type(entry.value) == "table" then
      if entry.value.location then
        return entry.value.location
      end
      if entry.value.uri or entry.value.targetUri then
        return entry.value
      end
    end
    return nil
  end

  local function extract_path(entry)
    local item = entry
    if type(entry) == "table" and entry.value ~= nil then
      item = entry.value
    end
    if type(item) == "string" then
      return item
    end
    if type(item) ~= "table" then
      return nil
    end
    if item.filename then
      return item.filename, item.lnum, item.col
    end
    if item.bufnr then
      return vim.api.nvim_buf_get_name(item.bufnr), item.lnum, item.col
    end
    if item.path then
      return item.path, item.lnum, item.col
    end
    return nil
  end

  local function open_in_pane(entry)
    window_utils.open_in_similar_pane(function(win_id)
      if not (win_id and vim.api.nvim_win_is_valid(win_id)) then
        return
      end
      vim.api.nvim_set_current_win(win_id)

      local location = extract_location(entry)
      if location then
        vim.lsp.util.show_document(location, opts.encoding or "utf-16", { focus = true })
        return
      end

      local path, lnum, col = extract_path(entry)
      if not path or vim.fn.filereadable(path) == 0 then
        vim.notify("Not a valid file path: " .. tostring(path), vim.log.levels.ERROR)
        return
      end
      vim.cmd.edit(vim.fn.fnameescape(path))
      if lnum and lnum > 0 then
        local cursor_col = math.max((col or 1) - 1, 0)
        pcall(vim.api.nvim_win_set_cursor, win_id, { lnum, cursor_col })
      end
    end)
  end

  return M.show_list(items, vim.tbl_extend("force", {}, opts, {
    on_select = function(selection)
      open_in_pane(selection)
    end,
  }))
end

return M
