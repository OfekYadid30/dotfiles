// Mirrors the Claude Code tmux hooks in ~/.claude/settings.json by calling the
// same scripts, which call ~/.tmux/scripts/attn.sh on/off -- the same switch as
// attn_on/attn_off -- so there is one window-wide @need_attention flag:
//   Stop / Notification           -> tmux-attn-set.sh   (tab turns green)
//   UserPromptSubmit / SessionEnd -> tmux-attn-clear.sh (tab back to white)
//   SessionStart                  -> tmux-attn-track.sh (so a closed pane can
//                                    still clear its window)
// A question/permission prompt counts as a Notification, and answering it
// counts as UserPromptSubmit (answers don't go through chat.message).
import { spawn, spawnSync } from "node:child_process"
import { homedir } from "node:os"

const HOOKS = `${homedir()}/.claude/hooks`

function run(script) {
  if (!process.env.TMUX) return
  spawnSync(`${HOOKS}/${script}`, { input: "{}", timeout: 10000, stdio: ["pipe", "ignore", "ignore"] })
}

// opencode runs plugins in a worker thread that is torn down on quit without
// any exit/signal handlers firing, so SessionEnd can't be caught in-process.
// Instead, a detached watcher holds a pipe whose write end only opencode owns;
// the OS closes it the instant opencode dies (/exit, Ctrl-C or kill), so the
// watcher's `cat` gets EOF immediately and clears the flag -- no polling.
function watchForExit() {
  if (!process.env.TMUX) return
  const script = `cat >/dev/null; echo '{}' | "${HOOKS}/tmux-attn-clear.sh"`
  const child = spawn("/bin/sh", ["-c", script], { detached: true, stdio: ["pipe", "ignore", "ignore"] })
  child.stdin.unref?.()
  child.unref()
}

export const TmuxAttn = async () => {
  // Subagent (child) sessions go idle on their own; only the root session
  // finishing counts as "answered", like Claude's background_tasks check.
  const childSessions = new Set()

  run("tmux-attn-track.sh")
  watchForExit()

  return {
    "chat.message": async () => run("tmux-attn-clear.sh"),
    // Backup for question.asked/replied: the question tool blocks between
    // these two hooks while it waits for the user.
    "tool.execute.before": async ({ tool }) => {
      if (tool === "question") run("tmux-attn-set.sh")
    },
    "tool.execute.after": async ({ tool }) => {
      if (tool === "question") run("tmux-attn-clear.sh")
    },
    event: async ({ event }) => {
      const p = event.properties ?? {}
      switch (event.type) {
        case "session.created":
        case "session.updated":
          if (p.info?.parentID) childSessions.add(p.info.id)
          break
        case "session.idle":
          if (!childSessions.has(p.sessionID)) run("tmux-attn-set.sh")
          break
        case "permission.asked":
        case "permission.updated":
        case "question.asked":
          run("tmux-attn-set.sh")
          break
        case "permission.replied":
        case "question.replied":
        case "question.rejected":
          run("tmux-attn-clear.sh")
          break
        case "session.deleted":
        case "server.instance.disposed":
          run("tmux-attn-clear.sh")
          break
      }
    },
  }
}
