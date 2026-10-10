
local dap = require("dap")
local dapui = require("dapui")
local colors = require("themes.western").colors

dapui.setup({
  layouts = {
    {
      elements = { "repl" },
      size = 0.25,
      position = "bottom",
    },
  },
  controls = { enabled = false },
})

local dap_python = require("dap-python")
local system_python = vim.fn.exepath("python3")

dap_python.setup(system_python)
dap_python.resolve_python = function()
  return system_python
end
dap_python.test_runner = "pytest"

dap.configurations.python = {
  {
    type = "python",
    request = "launch",
    name = "Launch file",
    program = "${file}",
    console = "integratedTerminal",
    args = {},
  },
  {
    type = "python",
    request = "attach",
    name = "Attach to external process",
    connect = {
      host = "127.0.0.1",
      port = 32045,
    },
    justMyCode = false,
  },
}

require("nvim-dap-virtual-text").setup({
  enabled = true,
  highlight_changed_variables = true,
  show_stop_reason = true,
})

vim.api.nvim_set_hl(0, "DapBreakpointLine", { bg = colors.dap_breakpoint_line_bg })
vim.api.nvim_set_hl(0, "DapStoppedLine", { bg = colors.dap_stopped_line_bg })

vim.fn.sign_define("DapBreakpoint", {
  text = "",
  texthl = "DiagnosticError",
  linehl = "DapBreakpointLine",
  numhl = "",
})
vim.fn.sign_define("DapBreakpointCondition", {
  text = "",
  texthl = "DiagnosticWarn",
  linehl = "DapBreakpointLine",
  numhl = "",
})
vim.fn.sign_define("DapLogPoint", {
  text = "",
  texthl = "DiagnosticInfo",
  linehl = "DapBreakpointLine",
  numhl = "",
})
vim.fn.sign_define("DapStopped", {
  text = "",
  texthl = "DiagnosticHint",
  linehl = "DapStoppedLine",
  numhl = "",
})
vim.fn.sign_define("DapBreakpointRejected", {
  text = "",
  texthl = "DiagnosticError",
  linehl = "DapBreakpointLine",
  numhl = "",
})


vim.keymap.set("n", "<leader>dc", dap.continue, { desc = "DAP Continue" })
vim.keymap.set("n", "<leader>do", dap.step_over, { desc = "DAP Step Over" })
vim.keymap.set("n", "<leader>di", dap.step_into, { desc = "DAP Step Into" })
vim.keymap.set("n", "<leader>du", dap.step_out, { desc = "DAP Step Out" })
vim.keymap.set("n", "<leader>dA", dap.disconnect, { desc = "DAP Detach" })

vim.keymap.set("n", "<leader>dx", function()
  dap.run(dap.configurations.python[1])
end, { desc = "DAP Run Current File" })

vim.keymap.set("n", "<leader>dd", dap.toggle_breakpoint, { desc = "DAP Toggle Breakpoint" })

vim.keymap.set("n", "<leader>dD", function()
  dap.clear_breakpoints()
  vim.notify("DAP: Cleared all breakpoints")
end, { desc = "DAP Clear All Breakpoints" })

vim.keymap.set("n", "<leader>ds", function()
  dap.set_breakpoint(nil, nil, vim.fn.input("Log point message: "))
end, { desc = "DAP Log Point" })

vim.keymap.set("n", "<leader>dl", dapui.toggle, { desc = "DAP Toggle UI" })

local function jump_to_breakpoint(next_bp)
  local breakpoints = dap.list_breakpoints()
  local bufnr = vim.api.nvim_get_current_buf()
  local cur_line = vim.api.nvim_win_get_cursor(0)[1]

  local line_nums = {}
  for _, bp in ipairs(breakpoints[bufnr] or {}) do
    table.insert(line_nums, bp.line)
  end
  table.sort(line_nums)

  if #line_nums == 0 then
    vim.notify("No breakpoints in this file", vim.log.levels.WARN)
    return
  end

  local target
  if next_bp then
    for _, l in ipairs(line_nums) do
      if l > cur_line then
        target = l
        break
      end
    end
    if not target then
      target = line_nums[1]
    end
  else
    for i = #line_nums, 1, -1 do
      if line_nums[i] < cur_line then
        target = line_nums[i]
        break
      end
    end
    if not target then
      target = line_nums[#line_nums]
    end
  end

  vim.api.nvim_win_set_cursor(0, { target, 0 })
end

vim.keymap.set("n", "<leader>dn", function()
  jump_to_breakpoint(true)
end, { desc = "DAP Next Breakpoint" })

vim.keymap.set("n", "<leader>dp", function()
  jump_to_breakpoint(false)
end, { desc = "DAP Previous Breakpoint" })

vim.keymap.set("n", "<leader>df", function()
  local ok, telescope = pcall(require, "telescope")
  if ok and telescope.extensions and telescope.extensions.dap then
    telescope.extensions.dap.list_breakpoints()
  else
    vim.notify("Telescope DAP extension not loaded", vim.log.levels.ERROR)
  end
end, { desc = "Telescope: Show DAP Breakpoints" })

dap.listeners.after.event_initialized["dapui_config"] = function()
  dapui.open()
end
dap.listeners.before.event_terminated["dapui_config"] = function()
  dapui.close()
end
dap.listeners.before.event_exited["dapui_config"] = function()
  dapui.close()
end

vim.keymap.set("n", "<leader>da", function()
  local port_input = vim.fn.input("Attach port: ", "32045")
  local port = tonumber(port_input)
  if not port then
    vim.notify("Invalid port: " .. tostring(port_input), vim.log.levels.ERROR)
    return
  end

  require("dap").run({
    type = "python",
    request = "attach",
    name = "Attach running Python",
    connect = { host = "127.0.0.1", port = port },
  })
end, { desc = "DAP Attach to port" })

pcall(function()
  require("telescope").load_extension("dap")
end)
