-- Make "+y reach the clipboard of the terminal you are sitting at.
--
-- nvim's own detection prefers wl-copy/xclip whenever DISPLAY or
-- WAYLAND_DISPLAY is set, which over SSH to a machine with a desktop session
-- means the remote desktop's clipboard. Its tmux provider uses
-- `load-buffer -w`, which reaches only the most recently active client.
-- Inside tmux, clip-copy.sh sends OSC 52 to every attached client instead.

if vim.env.TMUX then
  local copy = { "sh", vim.fn.expand("~/.tmux/scripts/clip-copy.sh") }
  local paste = { "tmux", "save-buffer", "-" }
  vim.g.clipboard = {
    name = "clip-copy",
    copy = { ["+"] = copy, ["*"] = copy },
    paste = { ["+"] = paste, ["*"] = paste },
    cache_enabled = 0,
  }
elseif vim.env.SSH_TTY or vim.env.SSH_CONNECTION then
  local osc52 = require("vim.ui.clipboard.osc52")
  -- An OSC 52 read is slow and often refused; paste the last yank instead.
  local function paste()
    return { vim.fn.getreg('"', 1, true), vim.fn.getregtype('"') }
  end
  vim.g.clipboard = {
    name = "osc52",
    copy = { ["+"] = osc52.copy("+"), ["*"] = osc52.copy("*") },
    paste = { ["+"] = paste, ["*"] = paste },
  }
end
