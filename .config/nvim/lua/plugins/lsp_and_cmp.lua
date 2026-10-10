
vim.diagnostic.config({
  virtual_text = true,
  signs = true,
  underline = true,
  update_in_insert = false,
  severity_sort = true,
  float = {
    border = "rounded",
    source = "always",
    header = "",
    prefix = "",
  },
})

local notify_once = vim.notify_once or vim.notify

local default_ignore_patterns = require("configuration").ignore_error_patterns

local user_ignore_patterns = vim.g.lsp_diagnostic_ignore_patterns
if type(user_ignore_patterns) ~= "table" then
  user_ignore_patterns = {}
end

local diagnostic_ignore_patterns = vim.tbl_deep_extend(
  "force",
  default_ignore_patterns,
  user_ignore_patterns
)

local function should_ignore_diagnostic(ft, message)
  local patterns = diagnostic_ignore_patterns[ft]
  if not patterns or #patterns == 0 then
    return false
  end
  if not message then
    return false
  end
  for _, pat in ipairs(patterns) do
    if message:match(pat) then
      return true
    end
  end
  return false
end

local function filter_diagnostics(ft, diagnostics)
  if not diagnostics or vim.tbl_isempty(diagnostics) then
    return diagnostics
  end
  if not diagnostic_ignore_patterns[ft] then
    return diagnostics
  end
  local filtered = {}
  for _, d in ipairs(diagnostics) do
    if not should_ignore_diagnostic(ft, d.message) then
      table.insert(filtered, d)
    end
  end
  return filtered
end

local function wrap_handler(handler)
  if type(handler) ~= "table" or type(handler.show) ~= "function" then
    return handler
  end
  return {
    show = function(namespace, bufnr, diagnostics, opts)
      local ft = vim.bo[bufnr].filetype
      handler.show(namespace, bufnr, filter_diagnostics(ft, diagnostics), opts)
    end,
    hide = handler.hide,
  }
end

do
  local handlers = vim.diagnostic.handlers
  for _, name in ipairs({ "virtual_text", "signs", "underline", "virtual_lines" }) do
    if handlers[name] then
      handlers[name] = wrap_handler(handlers[name])
    end
  end
end

local ok_cmp, cmp = pcall(require, "cmp")
if ok_cmp then
  local ok_luasnip, luasnip = pcall(require, "luasnip")
  if ok_luasnip then
    pcall(require, "luasnip.loaders.from_vscode")
  else
    notify_once("luasnip not available: snippet expansion disabled", vim.log.levels.WARN)
  end

  local function luasnip_ready()
    return ok_luasnip and luasnip
  end

  cmp.setup({
    snippet = {
      expand = function(args)
        if luasnip_ready() and luasnip.lsp_expand then
          luasnip.lsp_expand(args.body)
        end
      end,
    },
    completion = {
      autocomplete = { cmp.TriggerEvent.TextChanged },
      completeopt = "menu,menuone,noselect",
    },
    preselect = cmp.PreselectMode.None,
    mapping = cmp.mapping.preset.insert({
      ["<CR>"] = cmp.mapping.confirm({ select = false }),
      ["<C-e>"] = cmp.mapping.abort(),
      ["<Up>"] = cmp.config.disable,
      ["<Down>"] = cmp.config.disable,
      ["<Tab>"] = cmp.mapping(function(fallback)
        if cmp.visible() then
          cmp.select_next_item()
        elseif luasnip_ready() and luasnip.expand_or_jumpable and luasnip.expand_or_jumpable() then
          luasnip.expand_or_jump()
        else
          fallback()
        end
      end, { "i", "s" }),
      ["<S-Tab>"] = cmp.mapping(function(fallback)
        if cmp.visible() then
          cmp.select_prev_item()
        elseif luasnip_ready() and luasnip.jumpable and luasnip.jumpable(-1) then
          luasnip.jump(-1)
        else
          fallback()
        end
      end, { "i", "s" }),
      ["<C-d>"] = cmp.mapping.scroll_docs(4),
      ["<C-u>"] = cmp.mapping.scroll_docs(-4),
    }),
    sources = {
      { name = "nvim_lsp" },
      { name = "luasnip" },
      { name = "path" },
      { name = "buffer" },
    },
    window = {
      completion = cmp.config.window.bordered(),
      documentation = cmp.config.window.bordered(),
    },
  })
else
  notify_once("nvim-cmp not available: completion disabled", vim.log.levels.WARN)
end

local function require_or_notify(name)
  local ok, mod = pcall(require, name)
  if ok then
    return mod
  end
  vim.notify(("Missing module: %s"):format(name), vim.log.levels.ERROR)
  return nil
end

local lsp_zero = require_or_notify("lsp-zero")
local lspconfig = require_or_notify("lspconfig")
local cmp_lsp = require_or_notify("cmp_nvim_lsp")
local window_utils = require_or_notify("core.window_utils")
local git_jump = require_or_notify("core.git_jump")
local header_source = require_or_notify("plugins.lsp.header_source")
if not (lsp_zero and lspconfig and cmp_lsp) then
  return
end

lsp_zero.extend_lspconfig()

local capabilities = cmp_lsp.default_capabilities()

local telescope_utils
local function get_telescope_utils()
  if telescope_utils then
    return telescope_utils
  end
  local ok_utils, mod = pcall(require, "plugins.telescope")
  if ok_utils and type(mod) == "table" then
    telescope_utils = mod
    return telescope_utils
  end
  return nil
end

local function get_max_telescope_items()
  local value = tonumber(vim.g.lsp_telescope_max_items)
  if value and value > 0 then
    return value
  end
  return 8
end

local function flatten_locations(result)
  if not result or result == vim.NIL then
    return {}
  end
  if vim.islist(result) then
    return result
  end
  return { result }
end

local function request_locations(method, params, opts)
  local bufnr = opts.bufnr or vim.api.nvim_get_current_buf()
  vim.lsp.buf_request_all(bufnr, method, params, function(results)
    local locations = {}
    local encoding
    local errors = {}

    for client_id, res in pairs(results or {}) do
      if res.error then
        table.insert(errors, res.error)
      end

      local result = res.result
      if result and result ~= vim.NIL then
        if not encoding then
          local client = vim.lsp.get_client_by_id(client_id)
          encoding = (client and client.offset_encoding) or "utf-16"
        end
        vim.list_extend(locations, flatten_locations(result))
      end
    end

    if vim.tbl_isempty(locations) then
      if #errors > 0 then
        vim.notify(errors[1].message or tostring(errors[1]), vim.log.levels.ERROR)
      else
        vim.notify(opts.empty_message or "No results", vim.log.levels.INFO)
      end
      return
    end

    encoding = encoding or "utf-16"
    opts.on_locations(locations, encoding)
  end)
end

local function jump_to_location_in_other_pane(location, encoding)
  if not (window_utils and window_utils.jump_to_location_in_other_pane) then
    vim.lsp.util.show_document(location, encoding, { focus = true })
    return
  end
  window_utils.jump_to_location_in_other_pane(location, encoding)
end

local function jump_to_location_target(location, encoding, open_in_pane)
  if open_in_pane then
    jump_to_location_in_other_pane(location, encoding)
  else
    vim.lsp.util.show_document(location, encoding, { focus = true })
  end
end

local function get_location_from_selection(selection)
  if not selection then
    return nil
  end
  if selection.location then
    return selection.location
  end
  if selection.uri or selection.targetUri then
    return selection
  end
  if type(selection.value) == "table" then
    if selection.value.location then
      return selection.value.location
    end
    if selection.value.uri or selection.value.targetUri then
      return selection.value
    end
  end
  return nil
end

local function jump_from_selection(selection, encoding)
  local location = get_location_from_selection(selection)
  if location then
    vim.lsp.util.show_document(location, encoding, { focus = true })
    return
  end

  local item = selection
  if type(selection) == "table" and selection.value ~= nil then
    item = selection.value
  end
  if type(item) ~= "table" then
    return
  end

  local filename = item.filename or item.path
  if not filename then
    return
  end

  vim.cmd.edit(vim.fn.fnameescape(filename))
  if item.lnum and item.lnum > 0 then
    local col = math.max((item.col or 1) - 1, 0)
    pcall(vim.api.nvim_win_set_cursor, 0, { item.lnum, col })
  end
end

local function filter_locations_excluding_cursor(locations, encoding)
  if not locations or vim.tbl_isempty(locations) then
    return locations
  end

  local cur_file = vim.api.nvim_buf_get_name(0)
  if cur_file == "" then
    return locations
  end

  local cursor = vim.api.nvim_win_get_cursor(0)
  local cur_line = cursor[1]
  local cur_col = cursor[2] + 1

  local items = vim.lsp.util.locations_to_items(locations, encoding) or {}
  if vim.tbl_isempty(items) then
    return locations
  end

  local filtered = {}
  for _, item in ipairs(items) do
    local same_file = item.filename == cur_file
    local within_range = false

    if same_file then
      local end_lnum = item.end_lnum or item.lnum
      local end_col = item.end_col or item.col

      if cur_line < item.lnum or cur_line > end_lnum then
        within_range = false
      elseif item.lnum == end_lnum then
        within_range = cur_col >= item.col and cur_col <= end_col
      elseif cur_line == item.lnum then
        within_range = cur_col >= item.col
      elseif cur_line == end_lnum then
        within_range = cur_col <= end_col
      else
        within_range = true
      end
    end

    if not (same_file and within_range) then
      if item.user_data then
        table.insert(filtered, item.user_data)
      end
    end
  end

  return filtered
end

local function make_location_action(method, title, opts)
  opts = opts or {}
  local open_in_pane = opts.open_in_pane
  local max_items = opts.max_items
  local make_params = opts.make_params
  local filter_locations = opts.filter_locations
  local jump_on_single = opts.jump_on_single

  return function()
    local params = make_params and make_params() or vim.lsp.util.make_position_params()

    request_locations(method, params, {
      empty_message = opts.empty_message or ("No " .. title .. " found"),
      on_locations = function(locations, encoding)
        if filter_locations then
          locations = filter_locations(locations, encoding) or {}
        end
        if vim.tbl_isempty(locations) then
          vim.notify(opts.empty_message or ("No " .. title .. " found"), vim.log.levels.INFO)
          return
        end

        local count = #locations
        local threshold = max_items

        if jump_on_single and count == 1 then
          jump_to_location_target(locations[1], encoding, open_in_pane)
          return
        end

        if threshold and count > threshold then
          jump_to_location_target(locations[1], encoding, open_in_pane)
          return
        end

        local telescope_utils = get_telescope_utils()
        if not telescope_utils or not telescope_utils.show_list then
          jump_to_location_target(locations[1], encoding, open_in_pane)
          return
        end

        local items = vim.lsp.util.locations_to_items(locations, encoding) or {}
        for _, item in ipairs(items) do
          if item.user_data then
            item.location = item.user_data
          end
        end

        if open_in_pane and telescope_utils.show_list_and_open_in_pane then
          telescope_utils.show_list_and_open_in_pane(items, {
            prompt_title = title,
            encoding = encoding,
          })
        else
          telescope_utils.show_list(items, {
            prompt_title = title,
            on_select = function(selection)
              if open_in_pane then
                jump_to_location_in_other_pane(get_location_from_selection(selection) or locations[1], encoding)
              else
                jump_from_selection(selection, encoding)
              end
            end,
          })
        end
      end,
    })
  end
end

local telescope_builtin
do
  local ok_telescope, builtin = pcall(require, "telescope.builtin")
  if ok_telescope then
    telescope_builtin = builtin
  else
    telescope_builtin = nil
    notify_once("telescope.nvim not available: using built-in LSP lists", vim.log.levels.WARN)
  end
end

local function lsp_picker(name, fallback, opts)
  if telescope_builtin and telescope_builtin[name] then
    return function()
      if opts then
        telescope_builtin[name](vim.tbl_extend("force", {}, opts))
      else
        telescope_builtin[name]()
      end
    end
  end
  return fallback
end

local lsp_actions = {
  definition = make_location_action("textDocument/definition", "Definitions", {
    max_items = get_max_telescope_items(),
    jump_on_single = true,
  }),
  declaration = make_location_action("textDocument/declaration", "Declarations", {
    max_items = get_max_telescope_items(),
    jump_on_single = true,
  }),
  implementation = make_location_action("textDocument/implementation", "Implementations", {
    max_items = get_max_telescope_items(),
  }),
  type_definition = make_location_action("textDocument/typeDefinition", "Type Definitions", {
    max_items = get_max_telescope_items(),
  }),
  references = lsp_picker("lsp_references", vim.lsp.buf.references, { jump_type = "never" }),
  workspace_symbols = lsp_picker("lsp_dynamic_workspace_symbols", function()
    vim.lsp.buf.workspace_symbol("")
  end),
  definition_other = make_location_action("textDocument/definition", "Definitions", {
    open_in_pane = true,
    max_items = get_max_telescope_items(),
    jump_on_single = true,
  }),
  declaration_other = make_location_action("textDocument/declaration", "Declarations", {
    open_in_pane = true,
    max_items = get_max_telescope_items(),
    jump_on_single = true,
  }),
  implementation_other = make_location_action("textDocument/implementation", "Implementations", {
    open_in_pane = true,
    max_items = get_max_telescope_items(),
  }),
  type_definition_other = make_location_action("textDocument/typeDefinition", "Type Definitions", {
    open_in_pane = true,
    max_items = get_max_telescope_items(),
  }),
  references_other = make_location_action("textDocument/references", "References", {
    open_in_pane = true,
    filter_locations = filter_locations_excluding_cursor,
    make_params = function()
      local params = vim.lsp.util.make_position_params()
      params.context = { includeDeclaration = true }
      return params
    end,
  }),
}

local function set_lsp_keymaps(bufnr)
  -- git views (fugitive/gitsigns buffers) keep their own gd / <leader>gd
  local in_git_view = git_jump and git_jump.is_git_view(bufnr)
  local map = function(mode, lhs, rhs, desc)
    if in_git_view and (lhs == "gd" or lhs == "<leader>gd") then
      return
    end
    vim.keymap.set(mode, lhs, rhs, { buffer = bufnr, silent = true, desc = desc })
  end

  map("n", "gd", lsp_actions.definition, "Go to definition")
  map("n", "gD", lsp_actions.declaration, "Go to declaration")
  map("n", "gi", lsp_actions.implementation, "Go to implementation")
  map("n", "gt", lsp_actions.type_definition, "Go to type definition")
  map("n", "grr", lsp_actions.references, "References")
  if header_source and header_source.open_counterpart then
    map("n", "<leader>lc", function()
      header_source.open_counterpart({ other_pane = false })
    end, "Switch header/source (current pane)")
    map("n", "<leader>lv", function()
      header_source.open_counterpart({ other_pane = true })
    end, "Switch header/source (other pane)")
  end

  map("n", "K", vim.lsp.buf.hover, "Hover")
  map({ "n", "i", "v" }, "<C-s>", vim.lsp.buf.signature_help, "Signature help")

  map("n", "<leader>ll", lsp_actions.workspace_symbols, "Workspace symbols")
  map("n", "<leader>gd", lsp_actions.definition_other, "Definition (other pane)")
  map("n", "<leader>gD", lsp_actions.declaration_other, "Declaration (other pane)")
  map("n", "<leader>gri", lsp_actions.implementation_other, "Implementation (other pane)")
  map("n", "<leader>grt", lsp_actions.type_definition_other, "Type definition (other pane)")
  map("n", "<leader>grr", lsp_actions.references_other, "References (other pane)")

  map({ "n", "v" }, "<leader>la", vim.lsp.buf.code_action, "Code action")
  map("n", "<leader>ln", vim.lsp.buf.rename, "Rename symbol")
  map("n", "<leader>lr", vim.lsp.buf.rename, "Rename symbol")

  map("n", "<leader>lf", function()
    vim.lsp.buf.format({ async = false })
  end, "Format buffer")

  map("n", "gl", vim.diagnostic.open_float, "Line diagnostics")
  map("n", "<leader>ld", vim.diagnostic.open_float, "Line diagnostics")
  map("n", "[d", vim.diagnostic.goto_prev, "Prev diagnostic")
  map("n", "]d", vim.diagnostic.goto_next, "Next diagnostic")
end

local lsp_keymaps_group = vim.api.nvim_create_augroup("LspKeymaps", { clear = true })
vim.api.nvim_create_autocmd("LspAttach", {
  group = lsp_keymaps_group,
  callback = function(args)
    local bufnr = args.buf
    if vim.b[bufnr].lsp_keymaps_set then
      return
    end
    vim.b[bufnr].lsp_keymaps_set = true
    set_lsp_keymaps(bufnr)
  end,
})

local function on_attach(client, bufnr)
  if client.name == "pyright" then
    client.server_capabilities.documentFormattingProvider = false
  end
end

lsp_zero.format_on_save({
  format_opts = { async = false, timeout_ms = 3000 },
  servers = {
    ["ruff"] = { "python" },
    ["clangd"] = { "c", "cpp" },
    ["lua_ls"] = { "lua" },
    ["jdtls"] = { "java" },
    ["rust_analyzer"] = { "rust" },
    ["buf_ls"] = { "proto" },
    ["intelephense"] = { "php" },
    ["jsonls"] = { "json", "jsonc" },
    ["ts_ls"] = { "javascript", "typescript", "javascriptreact", "typescriptreact" },
    ["html"] = { "html" },
    ["cssls"] = { "css", "scss", "less" },
  },
})

require("mason").setup({})

local ensure_installed = {
  "lua_ls",
  "clangd",
  "jdtls",
  "rust_analyzer",
  "pyright",
  "ruff",
  "buf_ls",
  "intelephense",
  "jsonls",
  "ts_ls",
  "html",
  "cssls",
  "bashls",
  "dockerls",
  "docker_compose_language_service",
}

local clangd_capabilities = vim.deepcopy(capabilities)
clangd_capabilities.offsetEncoding = { "utf-16" }

local servers = {
  clangd = {
    cmd = { "clangd", "--background-index" },
    capabilities = clangd_capabilities,
  },
  lua_ls = {
    settings = {
      Lua = {
        diagnostics = { globals = { "vim" } },
        workspace = { checkThirdParty = false },
        telemetry = { enable = false },
      },
    },
  },
  jdtls = {},
  rust_analyzer = {},
  pyright = {
    settings = {
      python = { analysis = { typeCheckingMode = "basic" } },
    },
  },
  ruff = {},
  buf_ls = {},
  intelephense = {},
  jsonls = {},
  ts_ls = {},
  html = {},
  cssls = {},
  bashls = {},
  dockerls = {},
  docker_compose_language_service = {},
}

local function setup_server(server, config)
  if not lspconfig[server] then
    vim.notify(("LSP server not found: %s"):format(server), vim.log.levels.ERROR)
    return
  end
  local merged = vim.tbl_deep_extend("force", {
    capabilities = capabilities,
    on_attach = on_attach,
  }, config or {})
  lspconfig[server].setup(merged)
end

require("mason-lspconfig").setup({
  ensure_installed = ensure_installed,
  handlers = {
    function(server)
      if server == "cmake" then
        return
      end
      setup_server(server, servers[server])
    end,
  },
})
