"""
Polish one section of a draft for academic English: reduce redundancy ("In this paper", "We show that"),
improve formality, and overwrite the section in place. Does not change structure.

With --use_llm: call an LLM to revise the section point-by-point (grammar, redundancy, formality).
Uses OpenAI-compatible API; set LITELLM_PROXY_API_BASE + LITELLM_PROXY_API_KEY or OPENAI_API_BASE + OPENAI_API_KEY.

Usage:
  python polish_text.py --file "draft.md" --target_section "Introduction"
  python polish_text.py --file "draft.md" --target_section "Results" --use_llm

Output: Overwrites the section in the file and prints "Polished section <name> in <path>."
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_utils import find_section  # noqa: E402

# Optional: for --use_llm
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def simple_polish(text: str) -> str:
    """Placeholder polish: strip common colloquialisms when not using LLM."""
    text = re.sub(r"^(In this paper,?\s*)+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(We show that\s*)+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*So,?\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


def llm_polish(text: str, section_name: str) -> str:
    """Revise section with LLM: point-by-point grammar, redundancy, formality. Returns revised text."""
    if not text.strip():
        return text
    if OpenAI is None:
        print(
            "Warning: openai not installed; falling back to simple_polish.", flush=True
        )
        return simple_polish(text)
    base_url = (
        os.environ.get("LITELLM_PROXY_API_BASE")
        or os.environ.get("OPENAI_API_BASE")
        or None
    )
    api_key = os.environ.get("LITELLM_PROXY_API_KEY") or os.environ.get(
        "OPENAI_API_KEY"
    )
    if not api_key:
        print(
            "Warning: no API key (LITELLM_PROXY_API_KEY / OPENAI_API_KEY); falling back to simple_polish.",
            flush=True,
        )
        return simple_polish(text)
    model = (
        os.environ.get("LITELLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    client = OpenAI(
        api_key=api_key, base_url=base_url.rstrip("/") if base_url else None
    )
    # Patent Claims only: skip De-AIGC passes (claims language is intentionally
    # formal/repetitive by convention). All other sections including Detailed Description
    # follow De-AIGC rules normally (see prompts/patent.md).
    is_patent_claims = section_name.lower() == "claims"
    if is_patent_claims:
        system = """You are a patent copy-editor. Revise the given patent section for grammar and clarity only.
- Fix grammar errors and unclear antecedents.
- Do NOT change claim structure, claim language (comprising, wherein, characterized in that), or claim numbering.
- Do NOT remove repetition that is intentional in patent drafting.
- Preserve all section structure; do not add or remove content.
Output ONLY the revised section body text, no commentary or markdown code fence."""
    else:
        system = """You are an academic copy-editor applying the De-AIGC writing standard. Revise the given section using the following 5-pass checklist:

Pass 1 - Claim Calibration:
- Replace overconfident verbs (prove, establish, enable, predict, the only, eliminates) with calibrated ones: support, indicate, constrain, suggest.
- Downgrade any claim not directly supported by evidence in the text.

Pass 2 - Specificity Upgrade:
- Replace abstract nouns (framework, strategy, paradigm, workflow) with concrete operations.
- Add boundary conditions (system, regime, material class) where claims are unbounded.
- Replace vague statistics with named ones (MAD, RMSD, STD).

Pass 3 - Sentence Compression:
- Remove filler clauses and repeated qualifiers.
- Delete any sentence that only restates the previous one.
- Split compound sentences carrying more than one main point.

Pass 4 - Redundancy Removal:
- Delete duplicate thesis statements or definitions.
- Each key term defined once; remove re-definitions.

Pass 5 - Tone Scan:
- Delete or replace: Notably, Significantly, Importantly, Remarkably, It is worth noting that, It is well known that, This section reviews, It should be noted that, Paves the way for, Groundbreaking, Unprecedented, Showcasing, Highlighting, Fosters, Unleashes.
- Remove intensifiers without quantitative backing: just, merely, simply, dramatically.

Rules:
- Preserve all citations [n](URL) and section structure exactly.
- Do not add new content or references; only revise existing text.
- Output ONLY the revised section body text, no commentary or markdown code fence."""
    user = f"Section: {section_name}\n\n{text}"
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        out = (r.choices[0].message.content or "").strip()
        if out.startswith("```"):
            out = re.sub(r"^```\w*\n?", "", out).strip()
            out = re.sub(r"\n?```\s*$", "", out).strip()
        return out if out else text
    except Exception as e:
        print(f"LLM polish failed: {e}; using simple_polish.", flush=True)
        return simple_polish(text)


def main() -> None:
    ap = argparse.ArgumentParser(description="Polish one section for academic English.")
    ap.add_argument("--file", required=True, help="Path to draft file")
    ap.add_argument(
        "--target_section", required=True, help="Section to polish (e.g. Introduction)"
    )
    ap.add_argument(
        "--in_place", action="store_true", help="Overwrite file (default: true)"
    )
    ap.add_argument(
        "--use_llm",
        action="store_true",
        help="Use LLM for point-by-point revision (needs API key in env)",
    )
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", flush=True)
        return

    content = path.read_text(encoding="utf-8")
    found = find_section(content, args.target_section, include_text=True)
    if not found:
        print(f"Section '{args.target_section}' not found in {path}.", flush=True)
        return

    start, end, section_text = found
    lines = section_text.splitlines()
    header = lines[0] if lines else f"## {args.target_section}"
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    polished_body = (
        llm_polish(body, args.target_section) if args.use_llm else simple_polish(body)
    )
    new_section = f"{header}\n\n{polished_body}\n\n"

    new_content = content[:start] + new_section + content[end:].lstrip()
    path.write_text(new_content, encoding="utf-8")
    print(
        f"Polished section {args.target_section} in {path} ({'LLM' if args.use_llm else 'regex'}).",
        flush=True,
    )


if __name__ == "__main__":
    main()
