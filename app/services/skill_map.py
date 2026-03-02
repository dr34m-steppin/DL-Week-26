import re
from collections import Counter
from typing import Dict, List

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "under", "your", "their", "have", "has", "been", "will", "would", "about", "through", "between", "also", "when", "where", "which", "while", "student", "learning", "course", "topic", "model"
}


def _top_terms(text: str, limit: int = 8) -> List[str]:
    tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text)
        if len(t) > 3
    ]
    filtered = [t for t in tokens if t not in _STOPWORDS]
    counter = Counter(filtered)
    ranked = [word for word, _ in counter.most_common(limit * 3)]
    deduped = []
    for word in ranked:
        if word not in deduped:
            deduped.append(word)
        if len(deduped) >= limit:
            break
    return [w.replace("-", " ").title() for w in deduped]


def build_skill_map(raw_text: str) -> List[Dict[str, object]]:
    topics = _top_terms(raw_text, limit=8)
    if not topics:
        topics = ["Foundations", "Core Concepts", "Practice", "Evaluation"]

    skill_nodes: List[Dict[str, object]] = []
    for idx, topic in enumerate(topics):
        prereqs = [] if idx == 0 else [topics[idx - 1]]
        skill_nodes.append(
            {
                "topic": topic,
                "prerequisites": prereqs,
                "validated": False,
                "professor_notes": "",
            }
        )

    return skill_nodes
