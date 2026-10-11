Build a Contradiction-Safe Context Picker for Director
OpenArt logo
OpenArt
Due
Oct 11, 3:30 PM PDT
Build a working context picker that helps Director continue with a useful, consistent view of the user's current project.

Context
OpenArt's Director helps a user develop a cinematic video through an ongoing conversation. The user makes decisions about characters, visual style and scenes, then revises some of them as the project develops. Director needs to carry the relevant decisions into each new turn so the conversation and creative output stay consistent. As a session grows, the next prompt cannot contain its entire history. The team needs a component that selects useful memory for that prompt within the available context budget. For this task, the memories are already provided as structured cards. The resources include a sample session, product notes, a technical contract, test inputs and a recording tool. You will work with this supplied data rather than build a system that extracts memories from conversation text.

Your Role
You are joining OpenArt as a Software Engineer, Agent, responsible for the component that selects memory before a Director turn. Build a working context picker that helps Director continue with a useful, consistent view of the user's current project. Use the supplied technical contract for the request and response formats and required component behavior. Choose your own implementation approach. Test the implementation, record its actual behavior on the supplied inputs, and explain how the team would integrate it and what limitations they should understand.

Deliverables
Package all required deliverables into a single ZIP archive named `director-context.zip` and submit the archive.

your runnable implementation, tests, results and documentation. Keep the required output files at the archive's root, together with any supporting local modules and tests.
the recorder's original output, including unsuccessful requests. Submit the runnable implementation together with its supporting files and documentation.
Must include:

• context_solver.py: Python 3.11 standard-library CLI; One stdin JSON request to one stdout JSON response following the public context selection contract; included local modules are allowed.

• benchmark_results.json: Actual unchanged-recorder JSON observations and captured execution log; Actual selected cards, recomputable utility/cost, diagnostics, wall time, peak memory and input integrity for every public corpus request.

• benchmark_run.log: Actual unchanged-recorder JSON observations and captured execution log; Actual selected cards, recomputable utility/cost, diagnostics, wall time, peak memory and input integrity for every public corpus request.

• README.md: Markdown; Clean-extraction commands, runnable local regression command, method and limitations, measurement environment and operational note.




ContextYour RoleDeliverables