
local neotree = require("neo-tree")

neotree.setup({
  close_if_last_window = false,
  enable_git_status = true,
  enable_diagnostics = true,

  filesystem = {
    hijack_netrw_behavior = "disabled",
    bind_to_cwd = true,
    follow_current_file = {
      enabled = true,
      leave_dirs_open = true,
    },
    use_libuv_file_watcher = true,
    window = {
      position = "left",
      width = 55,
    },
    filtered_items = {
      hide_dotfiles = false,
      hide_gitignored = false,
      hide_by_name = { "node_modules", "__pycache__", ".git" },
    },
  },

  popup_border_style = "rounded",
  open_files_do_not_replace_types = { "terminal", "Trouble", "qf", "Outline", "trouble" },

  default_component_configs = {
    indent = { padding = 1 },
    icon = {
      folder_closed = "",
      folder_open = "",
      folder_empty = "",
    },
    git_status = {
      symbols = {
        added = "✚",
        modified = "",
        deleted = "✖",
        renamed = "󰁕",
        untracked = "",
        ignored = "",
      },
    },
  },

  window = {
    width = 55,
  },
})

vim.keymap.set("n", "<leader>E", ":Neotree toggle left<CR>", {
  noremap = true,
  silent = true,
  desc = "Toggle Neo-tree (left)",
})
