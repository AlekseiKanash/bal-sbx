---
name: roadmap.next-step
description: Get next roadmap step
---
Call:
mcp__roadmap__get_next_step()
If roadmap is complete and the is nothing to do:
- inform user
- stop

Otherwise:
- use returned step as authoritative
- start implementation