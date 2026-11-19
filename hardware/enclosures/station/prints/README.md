# Print tracker

Which station parts are printed, on which plate, and what is left. Managed by
the `printshop` MCP server (`~/.claude/mcp-servers/printshop`); ask Claude for
"parts status", "plan plates", "show plate P003", and so on.

- `project.json`: the part list (`../out/parts.json`, written by `build.py`)
  and how many stations' worth to print (`sets`).
- `state.json`: every plate, its status (planned, sliced, uploaded, printing,
  done, failed, dropped), and what came off it. This is the record.
- `plates/`: one folder per plate with the OrcaSlicer project you can open
  and edit, its preview and its G-code. Regenerable, so not in git.

If a part's model changes after its plate was planned, the plate says so;
drop it and plan again to print the new version.
