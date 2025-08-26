# shared_setup.py
import pandas as pd
import json
import re
from collections import defaultdict
from typing import Dict, Any, List

def normalize_lineitem(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = re.sub(r'\s+', ' ', s)
    return s

def load_label_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    df['LineItem_norm'] = df['LineItem'].apply(normalize_lineitem)
    # keep Parent and GrandParent columns as-is
    return df

def build_lookups(df: pd.DataFrame):
    """
    Returns:
      - exact: dict[lineitem_norm] -> {'parent':..., 'grandparent':...}
      - examples: list of dicts [{'lineitem':..., 'parent':..., 'grandparent':...}, ...]
      - parents: list, grandparents: list
    """
    exact: Dict[str, Dict[str,str]] = {}
    examples: List[Dict[str,str]] = []
    parents = set()
    grandparents = set()
    for _, r in df.iterrows():
        key = r['LineItem_norm']
        exact[key] = {'parent': r.get('Parent', '').strip(), 'grandparent': r.get('GrandParent', '').strip()}
        examples.append({
            'lineitem': r['LineItem_norm'],
            'parent': r.get('Parent', '').strip(),
            'grandparent': r.get('GrandParent', '').strip()
        })
        if r.get('Parent','').strip():
            parents.add(r.get('Parent','').strip())
        if r.get('GrandParent','').strip():
            grandparents.add(r.get('GrandParent','').strip())
    parents = sorted([p for p in parents if p])
    grandparents = sorted([g for g in grandparents if g])
    return exact, examples, parents, grandparents

def build_hierarchical_json(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Returns: {GrandParent: {Parent: [LineItems...]}}
    """
    tree = {}
    for _, r in df.iterrows():
        li = r['LineItem'].strip() if r['LineItem'] else ""
        gp = r.get('GrandParent','').strip() or "UNASSIGNED"
        p = r.get('Parent','').strip() or "UNASSIGNED"
        tree.setdefault(gp, {}).setdefault(p, []).append(li)
    return tree

def build_descriptions_from_hierarchy(hier: dict, max_sample_chars=200) -> list:
    descriptions = []
    for gp, parents in hier.items():
        for parent, items in parents.items():
            sample = ", ".join(items[:8])
            desc_text = f"Parent '{parent}' (grandparent '{gp}') includes examples: {sample}"
            descriptions.append({
                "grandparent": gp,
                "parent": parent,
                "description": desc_text[:max_sample_chars]
            })
    return descriptions

def save_json(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
