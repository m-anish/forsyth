# Board reference sheets

One sheet per physical PCB — the working documents for KiCad. Each contains the
board's role, connector pinouts, reference sub-circuits with sourced component values,
a per-board BOM **with designators**, and a bring-up checklist.

| Sheet | Board | Where it lives |
|---|---|---|
| [board-a-core.md](board-a-core.md) | **A — core** | sealed box under the Stevenson screen |
| [board-b-environment.md](board-b-environment.md) | **B — environment** | inside the Stevenson screen |
| [board-d-wind.md](board-d-wind.md) | **D — wind interface** | masthead junction |

(The coordinator gets its own sheet when its design pass starts; the rain gauge is a
bare reed switch and has no PCB.)

**Workflow:** these sheets are the source of truth for *intent*; the KiCad projects are
the source of truth for *implementation*. After each layout pass, export the KiCad BOM
back and reconcile — designators here are proposals until then. Values marked
**[verify]** must be checked against the named datasheet or on the bench before
ordering; everything else carries its source inline.

System-wide context: [../architecture.md](../architecture.md) (esp. §3 power gating,
§6 interconnect, §8 layout notes) · [../BOM.md](../BOM.md) (sourcing + pricing).
