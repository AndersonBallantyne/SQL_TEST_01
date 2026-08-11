import os
import sys
import json
from dotenv import load_dotenv
import anthropic
from logging_utils import get_tool_calls, get_final_answer

# Same fix as agent.py, needed independently here: this file's own CLI (__main__ below)
# and run_verify_eval.py both print LLM-generated reason text without ever importing
# agent.py, so they don't inherit that file's stdout reconfiguration for free.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(encoding="utf-8-sig")

client = anthropic.Anthropic()

# The verifier's only job is checking a proposed answer against tool evidence already
# gathered - it must not answer the question itself or reach for outside knowledge, since
# that would make it just a second opinion instead of an actual evidence check.
VERIFIER_SYSTEM_PROMPT = """You check whether a proposed answer is actually supported by the tool evidence gathered for it. You are not answering the original question yourself and must not use any outside knowledge - judge only whether the proposed answer logically follows from the tool call inputs/outputs shown to you.

When the evidence includes a SQL query, read its actual WHERE/ILIKE conditions, not just the column aliases or the proposed answer's own labels for them. If several per-category counts are compared against a stricter total (e.g. five brand-name counts against a count that additionally requires one specific keyword), check whether each category's own condition is actually a subset of the total's condition:
- If a per-category count is individually LARGER than a stricter total it's being compared against, that count cannot be a valid subset of that total - it is measuring something broader (e.g. a brand-name match with no keyword requirement, versus a total that requires the keyword). An answer that presents such a count as if it belonged to the same narrower category as the total is misleading, even if no single number is fabricated - explain specifically which condition is broader than which, don't just say the numbers "don't add up."
- Multiple per-category counts summing to MORE than a total, on its own, is not a contradiction - a single row can satisfy more than one category's condition at once. Do not flag this pattern by itself when every individual category count is still less than or equal to the total.

Call report_verdict with exactly one of three verdicts:

- "supported" - every claim in the proposed answer is backed by the tool evidence.

- "contradicted" - the answer contradicts the evidence, or takes evidence that does exist and stretches it beyond what it actually shows (e.g. a partial or generic mention presented as if it directly confirms a specific detail, or a count mislabeled as measuring something narrower than its actual condition). Use direct, unqualified language in reason for this case (e.g. "the evidence shows X, not Y").

- "unconfirmed" - a claim isn't fabricated-sounding and doesn't conflict with anything the evidence shows, but has no evidence at all behind it either way (e.g. specific column names/types, domain terminology, or other structured detail the evidence here never queried). This evidence set only covers tool calls made for this specific question - it has no visibility into earlier turns of the same conversation, and it cannot tell whether such a claim reflects real background knowledge the model has about the system versus something inaccurate. Stating a claim confidently does not make it "contradicted" - confident wording is not evidence. Use "unconfirmed" whenever a claim's truth simply cannot be determined from what's in front of you, and name exactly which claim(s) in reason.

If the proposed answer mixes claims from more than one category, pick "contradicted" if any claim is actually contradicted or stretched (that is the more serious problem), otherwise pick "unconfirmed" if any remaining claim can't be confirmed, otherwise "supported". In reason, give your normal reasoning either way (which claims are confirmed, which conditions matter, why) - the verdict field alone carries the contradicted-vs-unconfirmed distinction, so reason doesn't need any special framing or prefix of its own."""

# tool_choice forces this call every time (see verify_answer()) so the verdict is always a
# structured field, never prose that would need parsing. verdict is a 3-way enum rather than
# a boolean - a boolean plus a "start reason with 'Verify further:'" prose convention was tried
# first and never worked in practice (confirmed live 2026-08-11: a reproducible case where the
# model's own reason text kept describing the unconfirmed-not-contradicted situation in its own
# words, but the boolean+prefix convention still collapsed it to a flat unsupported=false every
# time). Forcing a categorical tool-argument choice is what structured tool-calling is actually
# reliable at; remembering a text-formatting convention buried in prose is not.
VERIFIER_TOOL = {
    "name": "report_verdict",
    "description": "Report whether the proposed answer is supported by the tool evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["supported", "contradicted", "unconfirmed"],
                "description": "supported: every claim is backed by the evidence. contradicted: the answer conflicts with or overstates the evidence. unconfirmed: a plausible, non-fabricated claim has no evidence either way."
            },
            "reason": {
                "type": "string",
                "description": "A short explanation of the verdict, citing what the evidence does or doesn't show."
            }
        },
        "required": ["verdict", "reason"]
    }
}

def build_evidence_block(tool_calls):
    if not tool_calls:
        return "No tool calls were made for this question."
    lines = []
    for call in tool_calls:
        lines.append(f"Tool: {call['tool_name']}")
        lines.append(f"Input: {json.dumps(call['input'])}")
        lines.append(f"Output: {json.dumps(call['output'], default=str)}")
        lines.append("")
    return "\n".join(lines)

def verify_answer(user_question, answer, tool_calls):
    evidence = build_evidence_block(tool_calls)
    user_content = f"""Question: {user_question}

Tool evidence:
{evidence}

Proposed answer: {answer}

Is the proposed answer supported by the tool evidence?"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=VERIFIER_SYSTEM_PROMPT,
        tools=[VERIFIER_TOOL],
        tool_choice={"type": "tool", "name": "report_verdict"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_verdict":
            # Confirmed live 2026-08-08: a large evidence + answer payload made this call hit
            # its own max_tokens cap mid-generation, truncating report_verdict's JSON after
            # "verdict" but before "reason" ever got written. block.input["reason"] then threw
            # KeyError, silently swallowed by agent.py's try/except - the user saw no badge at
            # all, not even a red one, with zero trace of why. Raising max_tokens (512 -> 1024)
            # cuts how often this fires; .get() with a fallback means a still-truncated response
            # returns a real (if less detailed) verdict instead of vanishing.
            if response.stop_reason == "max_tokens" and "reason" not in block.input:
                print(f"[VERIFIER TRUNCATED] report_verdict hit max_tokens before 'reason' was written")
            verdict = block.input.get("verdict")
            if verdict is None:
                raise RuntimeError(f"Verifier's report_verdict call was missing 'verdict' entirely: {block.input!r}")
            reason = block.input.get(
                "reason",
                "Verifier's explanation was cut off before it could be generated (the verifier's own response hit its token limit).",
            )
            # The verdict enum carries the contradicted-vs-unconfirmed distinction now, not a
            # prose prefix the model has to remember to write - the caller-facing shape (a plain
            # supported: bool, reason: str) stays exactly what it was so agent.py/app.py/
            # run_verify_eval.py don't need to change at all.
            if verdict == "supported":
                supported = True
            elif verdict == "contradicted":
                supported = False
            elif verdict == "unconfirmed":
                supported = False
                reason = f"Verify further: {reason}"
            else:
                print(f"[VERIFIER UNEXPECTED VERDICT] report_verdict returned verdict={verdict!r}, treating as unsupported")
                supported = False
            return supported, reason

    raise RuntimeError("Verifier did not return a report_verdict tool call.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python verify_answer.py <question_id> ["override answer text"]')
        sys.exit(1)

    question_id = sys.argv[1]
    # Lets one script prove both the good and the deliberately-bad case: real tool evidence
    # either paired with its real logged answer, or with a wrong answer typed in here instead.
    override_answer = sys.argv[2] if len(sys.argv) > 2 else None

    tool_calls = get_tool_calls(question_id, include_output=True)
    logged_answer = get_final_answer(question_id)

    if logged_answer is None and override_answer is None:
        print(f"No logged answer found for question_id {question_id!r}, and no override answer given.")
        sys.exit(1)

    user_question = tool_calls[0]["user_question"] if tool_calls else "(question text unavailable - no tool calls logged for this question_id)"
    answer = override_answer if override_answer is not None else logged_answer

    supported, reason = verify_answer(user_question, answer, tool_calls)

    print(f"question_id: {question_id}")
    print(f"question: {user_question}")
    print(f"answer: {answer}")
    print(f"supported: {supported}")
    print(f"reason: {reason}")
