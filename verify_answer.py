import os
import sys
import json
from dotenv import load_dotenv
import anthropic
from logging_utils import get_tool_calls, get_final_answer

load_dotenv(encoding="utf-8-sig")

client = anthropic.Anthropic()

# The verifier's only job is checking a proposed answer against tool evidence already
# gathered - it must not answer the question itself or reach for outside knowledge, since
# that would make it just a second opinion instead of an actual evidence check.
VERIFIER_SYSTEM_PROMPT = """You check whether a proposed answer is actually supported by the tool evidence gathered for it. You are not answering the original question yourself and must not use any outside knowledge - judge only whether the proposed answer logically follows from the tool call inputs/outputs shown to you.

Call report_verdict with supported=true only if every claim in the proposed answer is backed by the tool evidence. If the answer contradicts the evidence, overstates it, or claims something the evidence never shows, set supported=false and explain why in reason."""

# tool_choice forces this call every time (see verify_answer()) so the verdict is always a
# structured field, never prose that would need parsing.
VERIFIER_TOOL = {
    "name": "report_verdict",
    "description": "Report whether the proposed answer is supported by the tool evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "supported": {
                "type": "boolean",
                "description": "True if the proposed answer is fully supported by the tool evidence, false otherwise."
            },
            "reason": {
                "type": "string",
                "description": "A short explanation of the verdict, citing what the evidence does or doesn't show."
            }
        },
        "required": ["supported", "reason"]
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
        max_tokens=512,
        system=VERIFIER_SYSTEM_PROMPT,
        tools=[VERIFIER_TOOL],
        tool_choice={"type": "tool", "name": "report_verdict"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_verdict":
            return block.input["supported"], block.input["reason"]

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
