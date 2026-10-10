local lazy_opts = {
  lockfile = vim.fn.stdpath("config") .. "/lazy-lock.json",
}

if type(vim.g.__portable_lazy_root) == "string" and vim.g.__portable_lazy_root ~= "" then
  lazy_opts.root = vim.g.__portable_lazy_root
end

-- Applies configuration.pin_plugins to every plugin spec in `specs` (a list),
-- recursing into dependencies (plain strings are turned into tables).
local function apply_pin(specs, pin)
  if type(specs) == "string" then
    specs = { specs }
  end
  for i, spec in ipairs(specs) do
    if type(spec) == "string" then
      spec = { spec }
      specs[i] = spec
    end
    spec.pin = pin
    if spec.dependencies then
      spec.dependencies = apply_pin(spec.dependencies, pin)
    end
  end
  return specs
end

local pin_plugins = require("configuration").pin_plugins == true

require("lazy").setup(apply_pin({

  -- lazy.nvim updates itself too, so it needs a spec to be pinned.
  { "folke/lazy.nvim" },

  {
    "declancm/maximize.nvim",
    config = function()
      require("plugins.maximize")
    end,
  },

  {
    "VonHeikemen/lsp-zero.nvim",
    branch = "v4.x",
    dependencies = {
      "neovim/nvim-lspconfig",
      "williamboman/mason.nvim",
      "williamboman/mason-lspconfig.nvim",
      "hrsh7th/nvim-cmp",
      "hrsh7th/cmp-nvim-lsp",
      "hrsh7th/cmp-buffer",
      "hrsh7th/cmp-path",
      "L3MON4D3/LuaSnip",
      "rafamadriz/friendly-snippets",
    },
    config = function()
      require("plugins.lsp_and_cmp")
    end,
  },

  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    config = function()
      require("plugins.telescope")
    end,
  },

  {
    "nvim-treesitter/nvim-treesitter",
    -- The config uses the nvim-treesitter.configs API, which only master has.
    -- The default branch is now `main`, a rewrite without it.
    branch = "master",
    lazy = false,
    build = nil,
    config = function()
      require("plugins.treesitter")
    end,
  },
  {
    "nvim-treesitter/nvim-treesitter-context",
    dependencies = { "nvim-treesitter/nvim-treesitter" },
    config = function()
      require("plugins.treesitter_context")
    end,
  },

  {
    "folke/flash.nvim",
    event = "VeryLazy",
    config = function()
      require("plugins.flash")
    end,
  },

  {
    "theprimeagen/harpoon",
    branch = "harpoon2",
    dependencies = { "nvim-lua/plenary.nvim" },
    config = function()
      require("plugins.harpoon")
    end,
  },

  {
    "LintaoAmons/bookmarks.nvim",
    dependencies = {
      "nvim-lua/plenary.nvim",
      "stevearc/dressing.nvim",
      "kkharji/sqlite.lua",
      "nvim-telescope/telescope.nvim",
    },
    config = function()
      require("plugins.bookmarks")
    end,
  },

  { "rose-pine/neovim",  name = "rose-pine" },

  { "tpope/vim-fugitive" },

  {
    "mbbill/undotree",
    config = function()
      require("plugins.undotree")
    end,
  },

  {
    "stevearc/oil.nvim",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      require("plugins.oil")
    end,
  },

  {
    "nvim-neo-tree/neo-tree.nvim",
    branch = "v3.x",
    dependencies = {
      "nvim-lua/plenary.nvim",
      "nvim-tree/nvim-web-devicons",
      "MunifTanjim/nui.nvim",
    },
    config = function()
      require("plugins.neotree")
    end,
  },

  { "lewis6991/gitsigns.nvim", config = true },
  { "numToStr/Comment.nvim",   config = true },
  { "windwp/nvim-autopairs",   enabled = false },
  { "kylechui/nvim-surround",  config = true },
  { "folke/which-key.nvim",    config = true },

  {
    "mfussenegger/nvim-dap",
    dependencies = {
      "rcarriga/nvim-dap-ui",
      "nvim-neotest/nvim-nio",
      "mfussenegger/nvim-dap-python",
      "thehamsta/nvim-dap-virtual-text",
      {
        "nvim-telescope/telescope-dap.nvim",
        dependencies = { "nvim-telescope/telescope.nvim" },
        config = function()
          require("telescope").load_extension("dap")
        end,
      },
    },
    config = function()
      require("plugins.dap")
    end,
  },

  {
    "powerman/vim-plugin-ansiesc",
    config = function()
      require("plugins.ansiesc")
    end,
  },

  {
    "OXY2DEV/markview.nvim",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      require("plugins.markview")
    end,
  },
}, pin_plugins), lazy_opts)
