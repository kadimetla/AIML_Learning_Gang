# Agent Skills, recreated with LangGraph primitives

Microsoft Agent Framework's [Agent
Skills](https://devblogs.microsoft.com/agent-framework/agent-skills-for-python-is-now-released/)
package reusable expertise (instructions, reference docs, scripts) as
`SKILL.md` bundles, loaded through progressive disclosure (advertise names
-> load full instructions -> read resources -> run scripts) via a
`SkillsProvider` wired into their `Agent` class.

LangGraph has no `SkillsProvider` -- it's a different framework, and you
can't plug Microsoft's `Agent`/`SkillsProvider` classes into a
`StateGraph`. But the *pattern* isn't framework-specific (it's the same
shape as Anthropic's own Skill format, which is what the `Skill` tool used
in this very session is built on), and it maps directly onto primitives
this repo already teaches separately:

| Script | Concept (from Microsoft's posts) | Built from |
|---|---|---|
| [`01_file_based_skill.py`](01_file_based_skill.py) | File-based skills (`SKILL.md` + frontmatter, `references/`), progressive disclosure via `load_skill`/`read_skill_resource` | [`../tool_node_weather/`](../tool_node_weather/)'s ToolNode + tools_condition loop |
| [`02_code_defined_skill.py`](02_code_defined_skill.py) | Code-defined / `InlineSkill` -- skills built in Python (simulating a database), no files at all | same loop, different skill source |
| [`03_script_execution_with_approval.py`](03_script_execution_with_approval.py) | `run_skill_script` requiring host approval by default | the same loop, plus `interrupt()` from [`../hitl/`](../hitl/) called *inside* the tool instead of a dedicated node |

Needs `OPENAI_API_KEY` in `.env` (see `.env.example`) -- the whole point of
each script is the model *deciding* whether a skill applies, so it needs to
reason for real rather than follow a scripted reply.

```bash
uv run examples/agent_skills/01_file_based_skill.py
uv run examples/agent_skills/02_code_defined_skill.py
uv run examples/agent_skills/03_script_execution_with_approval.py
```

## A real gotcha this ran into

Building these hit an actual bug, not a hypothetical one: `gpt-4o-mini` at
`temperature=0` got stuck calling `load_skill` with identical arguments
forever, never producing a final answer -- a known repetition trap at
greedy decoding. Telling the model "don't call this twice" in the system
prompt reduced it but didn't reliably fix it. What did: every `load_skill`
(and `read_skill_resource`) tool checks its own conversation history via
`InjectedState` and refuses a repeat with a different, corrective message
instead of returning identical content again -- since the tool's *output*
changes, the loop breaks deterministically no matter what the model does.
`recursion_limit=10` is kept as a backstop on top of that, not a substitute
for it.

## What's deliberately simplified

- No sandboxing on `run_skill_script` -- `03`'s script is pure Python string
  math, not arbitrary code execution, so the interrupt-approval gate is the
  only safety control shown. A real `run_skill_script` running untrusted
  code would still need the sandboxing Microsoft's post calls out.
- No tenant-aware filtering or caching -- both are `SkillsProvider`
  production concerns orthogonal to the core "advertise/load/read/run"
  shape these scripts focus on.
- `skills/` (used by `01`) has two skills; a real skill library would
  likely be much larger, which is exactly when the "advertise names only,
  load full instructions on demand" distinction starts to matter for
  keeping context lean.
