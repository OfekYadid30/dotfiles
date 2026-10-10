-- <leader>g git prefix (the LSP keeps <leader>gd / gD / gr* / gi).
-- Output REPLACES the current window (:Git ++curwin), so gd / <leader>gd
-- from core.git_jump work inside it as usual.
local M = {}

local function worktree()
  local ok, tree = pcall(vim.fn.FugitiveWorkTree)
  if ok and type(tree) == "string" and tree ~= "" then
    return tree
  end
  local res = vim.system({ "git", "rev-parse", "--show-toplevel" }, { cwd = vim.fn.getcwd(), text = true }):wait()
  if res.code == 0 and vim.trim(res.stdout or "") ~= "" then
    return vim.trim(res.stdout)
  end
  return nil
end

local function warn(msg)
  vim.notify("git diff: " .. msg, vim.log.levels.WARN)
end

-- `git diff <rev>`: everything after <rev> up to the worktree (uncommitted included)
local function diff_in_curwin(rev)
  local args = rev and (" " .. vim.fn.fnameescape(rev)) or ""
  vim.cmd("Git ++curwin diff" .. args)
end

-- Pick a commit from the log; show the diff from it (exclusive) to the worktree.
function M.diff_from_picked_commit()
  local tree = worktree()
  if not tree then
    return warn("not inside a git worktree")
  end
  local target_win = vim.api.nvim_get_current_win()
  local actions = require("telescope.actions")
  local action_state = require("telescope.actions.state")

  require("telescope.builtin").git_commits({
    cwd = tree,
    prompt_title = "Diff from commit (exclusive)",
    attach_mappings = function(prompt_bufnr)
      actions.select_default:replace(function()
        local entry = action_state.get_selected_entry()
        actions.close(prompt_bufnr)
        if not entry then
          return
        end
        if vim.api.nvim_win_is_valid(target_win) then
          vim.api.nvim_set_current_win(target_win)
        end
        diff_in_curwin(entry.value)
      end)
      return true
    end,
  })
end

-- Fugitive only opens output in a buffer for commands it knows page (diff,
-- log, show, ...); it expands plain aliases itself but can't see inside
-- `!` shell aliases, so `git mdiffp` would just echo. Force --paginate for
-- shell aliases that wrap diff/log/show, but not ones that rebase/push/commit
-- (fugitive aborts editors under --paginate).
local function wants_pager(args)
  local name = args:match("^(%S+)")
  if not name then
    return false
  end
  local res = vim.system({ "git", "config", "--get", "alias." .. name }, { cwd = worktree(), text = true }):wait()
  local alias = res.code == 0 and vim.trim(res.stdout or "") or ""
  if not alias:match("^!") then
    return false
  end
  for _, word in ipairs({ "rebase", "push", "commit", "fixup" }) do
    if alias:match(word) then
      return false
    end
  end
  return alias:match("git%s+diff") or alias:match("git%s+log") or alias:match("git%s+show") or alias:match("mlog")
end

-- :GitRun <args> -- `:Git ++curwin <args>`, paginating shell aliases (above).
local function git_run(opts)
  local args = vim.trim(opts.args):gsub("^git%s+", "")
  if args == "" then
    return
  end
  local paginate = wants_pager(args) and "--paginate " or ""
  vim.cmd("Git ++curwin " .. paginate .. args)
end

function M.setup()
  vim.api.nvim_create_user_command("GitRun", git_run, { nargs = "*", complete = "customlist,fugitive#Complete" })
  -- Prefill the cmdline (not silent, so it shows); <Tab> uses fugitive's
  -- completion and .gitconfig aliases work.
  vim.keymap.set("n", "<leader>gg", ":GitRun ", { desc = "Git: run command" })
  vim.keymap.set("n", "<leader>gp", M.diff_from_picked_commit, { silent = true, desc = "Git: diff from picked commit" })
end

return M
