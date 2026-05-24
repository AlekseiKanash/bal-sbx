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
- rename the step file from [prefix]_step_NN.md to in_progress_step_NN.md
- start implementation


When completed:
- rename the step file from in_progress_step_NN.md to done_step_NN.md
- do not commit. User will do it manually or ask you separately.