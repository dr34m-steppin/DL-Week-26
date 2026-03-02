from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.mastery import compute_topic_state, grade_band
from app.services.retrieval import LexicalRetriever, split_into_chunks


def test_mastery_logic() -> None:
    state = compute_topic_state(attempts=8, correct=2, total_response_time_ms=600000, streak_wrong=3)
    assert 0 <= state.mastery_score <= 1
    assert state.risk_level in {"LOW", "MEDIUM", "HIGH"}
    assert grade_band(88) == "A"
    assert grade_band(40) == "F"


def test_retrieval() -> None:
    text = """
    Gradient descent updates model parameters using loss gradients.
    Backpropagation uses chain rule to compute gradients.
    Cross-validation estimates model generalization.
    """
    chunks = split_into_chunks(text, chunk_size=80, overlap=10)
    retriever = LexicalRetriever(chunks)
    results = retriever.search("How does backpropagation compute gradients?", top_k=2)
    assert len(results) >= 1


def main() -> None:
    test_mastery_logic()
    test_retrieval()
    print("smoke_test passed")


if __name__ == "__main__":
    main()
