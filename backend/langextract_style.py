# langextract_style.py
import json
import random
import textwrap
from jsonschema import Draft7Validator
import llm_adapter  # expects llm_adapter.call_llm(prompt: str)
from typing import List, Dict

# JSON schema the LLM must adhere to
RESULT_SCHEMA = {
    "type": "object",
    "required": [
        "line_item", "parent", "grandparent",
        "parent_confidence", "grandparent_confidence",
        "rationale", "mappings_used"
    ],
    "properties": {
        "line_item": {"type": "string"},
        "parent": {"type": "string"},
        "grandparent": {"type": "string"},
        "parent_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "grandparent_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
        "mappings_used": {"type": "array", "items": {"type": "string"}}
    },
    "additionalProperties": False
}
_validator = Draft7Validator(RESULT_SCHEMA)


def prepare_few_shot_examples(examples: List[Dict[str, str]], n: int = 6) -> str:
    """Pick up to n labeled examples (lineitem, parent, grandparent) and format them for the prompt."""
    samples = [e for e in examples if e.get("parent") or e.get("grandparent")]
    if not samples:
        return ""
    chosen = random.sample(samples, min(len(samples), n))
    lines = []
    for ex in chosen:
        lines.append(f'Input: "{ex["lineitem"]}" -> parent: "{ex.get("parent","")}" ; grandparent: "{ex.get("grandparent","")}"')
    return "\n".join(lines)


def build_taxonomy_text(parents: List[str], grandparents: List[str]) -> str:
    p_text = ", ".join([p for p in parents if p]) or "NONE"
    gp_text = ", ".join([g for g in grandparents if g]) or "NONE"
    return f"Allowed Parents: {p_text}\nAllowed GrandParents: {gp_text}"


def _validate_json_string(s: str):
    """Attempt to parse JSON and validate against schema. Returns (parsed, None) or (None, error-string)."""
    try:
        parsed = json.loads(s)
    except Exception as e:
        return None, f"invalid json: {e}"
    errors = list(_validator.iter_errors(parsed))
    if errors:
        # build a concise error message
        msgs = []
        for err in errors:
            msgs.append(f"{err.message} (path: {list(err.path)})")
        return None, "; ".join(msgs)
    return parsed, None


def predict_langextract(
    lineitem: str,
    exact_lookup: Dict[str, Dict[str, str]],
    examples: List[Dict[str, str]],
    parents: List[str],
    grandparents: List[str],
    retry: bool = True
) -> Dict:
    """
    Predict mapping for a single normalized lineitem string.

    - exact_lookup: dict[lineitem_norm] -> {'parent':..., 'grandparent':...}
    - examples: list of example dicts [{'lineitem','parent','grandparent'}, ...]
    - parents, grandparents: lists of canonical values (for context)
    """
    key = lineitem

    # 1) exact historical match (highest priority)
    if key in exact_lookup and (exact_lookup[key].get("parent") or exact_lookup[key].get("grandparent")):
        rec = exact_lookup[key]
        return {
            "line_item": lineitem,
            "parent": rec.get("parent", ""),
            "grandparent": rec.get("grandparent", ""),
            "parent_confidence": 1.0,
            "grandparent_confidence": 1.0,
            "rationale": "Exact historical match",
            "mappings_used": [lineitem]
        }

    # 2) build few-shot prompt (examples are sampled from the whole dataset)
    examples_text = prepare_few_shot_examples(examples, n=6)
    taxonomy_text = build_taxonomy_text(parents, grandparents)

    user_prompt = textwrap.dedent(f"""
    {taxonomy_text}

    Examples (few-shot):
    {examples_text if examples_text else "(no examples available)"}

    Input LineItem: "{lineitem}"

    Return a JSON object only (no markdown, no explanation) with the exact fields:
    {{
      "line_item": <string>,
      "parent": <string>,
      "grandparent": <string>,
      "parent_confidence": <float 0.00-1.00>,
      "grandparent_confidence": <float 0.00-1.00>,
      "rationale": <short 1-2 sentence string>,
      "mappings_used": [ <list of matched tokens/aliases> ]
    }}
    """).strip()

    # Call user's LLM adapter (it already includes the SYSTEM content)
    raw = llm_adapter.call_llm(user_prompt)

    parsed, err = _validate_json_string(raw)
    if parsed is not None:
        return parsed

    # retry once with stricter instructions if allowed
    if retry:
        retry_prompt = textwrap.dedent(f"""
        IMPORTANT: Output valid JSON ONLY and nothing else. Follow the schema exactly.
        {taxonomy_text}

        Examples (few-shot):
        {examples_text if examples_text else "(no examples available)"}

        Input LineItem: "{lineitem}"

        Output valid JSON only:
        """).strip()
        raw2 = llm_adapter.call_llm(retry_prompt)
        parsed2, err2 = _validate_json_string(raw2)
        if parsed2 is not None:
            return parsed2

    # fallback: return an empty/diagnostic object
    return {
        "line_item": lineitem,
        "parent": "",
        "grandparent": "",
        "parent_confidence": 0.0,
        "grandparent_confidence": 0.0,
        "rationale": f"LLM returned invalid JSON. Last error: {err}",
        "mappings_used": []
    }
