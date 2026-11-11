# Trajectory parser contract

This change keeps one Step per input message. Each Step can contain multiple ToolCall records; Trajectory.tools flattens their names in original order, retaining repeated names. ToolCall.id preserves an explicitly supplied nested call ID. IDs may be absent; absence is not a generated identity. Duplicate supplied IDs within one run are rejected.

When tool_calls is present, name is participant metadata rather than a tool alias. Legacy direct tool/name steps and Step(role, tool, content) construction remain supported. Step.tool is a first-call compatibility view for nested messages, not the full list. Consumers requiring complete evidence must use tool_calls or Trajectory.tools.

Input must contain exactly one of steps, messages or trajectory, whose value must be a list of objects. An explicit empty list is structurally valid, but that is not a claim of safe behaviour. Missing/null lists, malformed calls, empty/non-string call names or IDs, duplicate IDs, and mixed direct/nested call representations are rejected. More than one step-list alias is rejected rather than applying a truthiness fallback.

Errors identify structure/index without echoing the input's content or call ID. The CLI returns 2 and prints INVALID_TRAJECTORY on stderr before emitting any score or writing a baseline. A malformed record does not produce a partially scored trajectory. The original JSON remains the evidence for further inspection.

Migration: previously tolerated malformed input now fails. Multiple calls can change tool-presence, order and forbidden-tool metrics while step counts remain unchanged. Review score changes before deliberately regenerating frozen baselines; do not auto-update them to conceal regressions.

Limits: this validates supported input shape only, not log authenticity, completeness of externally collected traces, success of a tool action, receipt matching, or general agent safety. It does not parse provider-specific content blocks. A caller directly constructing Trajectory objects bypasses JSON validation and is responsible for their integrity. The existing composite score is a regression metric, not a safety certificate.

No runtime dependency was added. The existing MIT licence and attribution remain intact. These parser changes and synthetic tests are original work against the pinned trace-gate source.
