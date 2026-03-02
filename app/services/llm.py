import json
import random
import re
from typing import Any, Dict, List
from urllib.parse import quote

import httpx
from openai import AzureOpenAI, OpenAI

from app.config import settings
from app.services.retrieval import LexicalRetriever, RetrievedChunk, split_into_chunks
from app.services.skill_map import build_skill_map


class LLMService:
    def __init__(self) -> None:
        self.provider = settings.llm_provider

    def _azure_client(self) -> AzureOpenAI:
        return AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )

    def _openai_client(self) -> OpenAI:
        return OpenAI(api_key=settings.openai_api_key)

    def _extract_json(self, text: str) -> List[Dict[str, Any]]:
        # The model often wraps JSON in markdown code fences.
        match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    def generate_quiz(
        self,
        course_text: str,
        topics: List[str],
        num_questions: int = 8,
        difficulty: str = "Intermediate",
        blooms_level: str = "Apply",
        coverage_scope: str = "all",
    ) -> List[Dict[str, Any]]:
        generated: List[Dict[str, Any]] = []
        try:
            if self.provider == "azure_openai" and settings.azure_openai_api_key:
                generated = self._generate_quiz_azure(
                    course_text,
                    topics,
                    num_questions,
                    difficulty=difficulty,
                    blooms_level=blooms_level,
                    coverage_scope=coverage_scope,
                )
            if self.provider == "openai" and settings.openai_api_key:
                generated = self._generate_quiz_openai(
                    course_text,
                    topics,
                    num_questions,
                    difficulty=difficulty,
                    blooms_level=blooms_level,
                    coverage_scope=coverage_scope,
                )
            if self.provider == "huggingface" and settings.huggingface_api_key:
                generated = self._generate_quiz_hf(
                    course_text,
                    topics,
                    num_questions,
                    difficulty=difficulty,
                    blooms_level=blooms_level,
                    coverage_scope=coverage_scope,
                )
        except Exception:
            generated = []

        cleaned = self._normalize_quiz_questions(generated, topics, num_questions)
        if cleaned:
            return cleaned[:num_questions]

        # Keep the demo flow alive when upstream model APIs are unavailable.
        return self._generate_quiz_mock(course_text, topics, num_questions)

    def generate_skill_map(
        self,
        course_text: str,
        max_topics: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            if self.provider == "azure_openai" and settings.azure_openai_api_key:
                generated = self._generate_skill_map_azure(course_text, max_topics)
                normalized = self._normalize_skill_nodes(generated, max_topics)
                if normalized:
                    return normalized
            if self.provider == "openai" and settings.openai_api_key:
                generated = self._generate_skill_map_openai(course_text, max_topics)
                normalized = self._normalize_skill_nodes(generated, max_topics)
                if normalized:
                    return normalized
            if self.provider == "huggingface" and settings.huggingface_api_key:
                generated = self._generate_skill_map_hf(course_text, max_topics)
                normalized = self._normalize_skill_nodes(generated, max_topics)
                if normalized:
                    return normalized
        except Exception:
            return self._generate_skill_map_mock(course_text, max_topics)

        return self._generate_skill_map_mock(course_text, max_topics)

    def chat(
        self,
        question: str,
        retrieved_chunks: List[RetrievedChunk],
    ) -> str:
        try:
            if self.provider == "azure_openai" and settings.azure_openai_api_key:
                return self._chat_azure(question, retrieved_chunks)
            if self.provider == "openai" and settings.openai_api_key:
                return self._chat_openai(question, retrieved_chunks)
            if self.provider == "huggingface" and settings.huggingface_api_key:
                return self._chat_hf(question, retrieved_chunks)
        except Exception:
            return self._chat_mock(question, retrieved_chunks)
        return self._chat_mock(question, retrieved_chunks)

    def generate_course_summary(self, course_text: str, focus_topic: str = "") -> str:
        focus = focus_topic.strip() or "full course"
        prompt = (
            "Create a concise, student-friendly course summary from the provided material. "
            "Return plain text with headings:\n"
            "1) Course Overview\n"
            "2) Key Concepts\n"
            "3) Prerequisites To Review\n"
            "4) High-Yield Checklist\n"
            "5) 3 Quick Self-Check Questions\n\n"
            f"Focus area: {focus}\n\n"
            f"Course material:\n{course_text[:14000]}"
        )
        fallback = self._course_summary_mock(course_text, focus_topic)
        return self._generate_learning_text(prompt, fallback)

    def relearn_concept(self, course_text: str, concept: str) -> str:
        concept = concept.strip() or "Core concept"
        prompt = (
            "Teach the concept again for a student who is struggling. "
            "Return plain text with headings:\n"
            "1) Concept In Simple Words\n"
            "2) Why It Matters\n"
            "3) Step-by-Step Intuition\n"
            "4) Common Mistakes\n"
            "5) Mini Practice Prompt\n"
            "Keep it practical and grounded in the provided course content.\n\n"
            f"Target concept: {concept}\n\n"
            f"Course material:\n{course_text[:14000]}"
        )
        fallback = self._relearn_concept_mock(course_text, concept)
        return self._generate_learning_text(prompt, fallback)

    def generate_solved_examples(self, course_text: str, concept: str, num_examples: int = 3) -> str:
        concept = concept.strip() or "Core concept"
        count = max(1, min(5, int(num_examples)))
        prompt = (
            "Generate solved example questions for study. "
            f"Return exactly {count} examples in plain text. "
            "Each example must include:\n"
            "- Problem\n"
            "- Given\n"
            "- Steps\n"
            "- Final Answer\n"
            "- Why This Works\n"
            "Use the course material and avoid unsupported facts.\n\n"
            f"Target concept: {concept}\n\n"
            f"Course material:\n{course_text[:14000]}"
        )
        fallback = self._solved_examples_mock(course_text, concept, count)
        return self._generate_learning_text(prompt, fallback)

    def _prompt_skill_map(self, text: str, max_topics: int) -> str:
        return (
            "You are a curriculum mapping assistant. Extract the most important course topics and their prerequisites "
            "from the provided document. Return ONLY a JSON array using this schema: "
            "[{topic, prerequisites, reason}]. "
            f"Generate 5 to {max_topics} topics. "
            "Rules: topic should be short and specific. prerequisites should be a list of other topic names required first. "
            "Use only concepts present in the text. reason should be one concise sentence referencing course intent.\n\n"
            f"Course Document:\n{text[:14000]}"
        )

    def _generate_learning_text(self, prompt: str, fallback: str) -> str:
        try:
            if self.provider == "azure_openai" and settings.azure_openai_api_key:
                content = self._complete_text_azure(prompt)
                if content.strip():
                    return self._normalize_learning_output(content.strip())
            if self.provider == "openai" and settings.openai_api_key:
                content = self._complete_text_openai(prompt)
                if content.strip():
                    return self._normalize_learning_output(content.strip())
            if self.provider == "huggingface" and settings.huggingface_api_key:
                content = self._complete_text_hf(prompt)
                if content.strip():
                    return self._normalize_learning_output(content.strip())
        except Exception:
            pass
        return self._normalize_learning_output(fallback)

    def _normalize_learning_output(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        normalized: List[str] = []

        for raw_line in lines:
            line = raw_line
            line = re.sub(r"^\s*```.*$", "", line)
            line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
            line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            line = re.sub(r"__(.*?)__", r"\1", line)
            line = re.sub(r"`([^`]+)`", r"\1", line)
            line = re.sub(r"^\s*\*\s+", "- ", line)
            normalized.append(line.rstrip())

        cleaned = "\n".join(normalized)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _complete_text_azure(self, prompt: str) -> str:
        client = self._azure_client()
        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a precise teaching assistant. Return plain text only."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _complete_text_openai(self, prompt: str) -> str:
        client = self._openai_client()
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a precise teaching assistant. Return plain text only."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _complete_text_hf(self, prompt: str) -> str:
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 900,
                "temperature": 0.2,
                "return_full_text": False,
            },
        }
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
        url = f"https://api-inference.huggingface.co/models/{settings.huggingface_model}"

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list) and data and "generated_text" in data[0]:
            return str(data[0]["generated_text"])
        return ""

    def _topic_guided_course_context(self, text: str, topics: List[str], max_chunks: int = 10) -> str:
        chunks = split_into_chunks(text, chunk_size=900, overlap=120)
        if not chunks:
            return text[:9000]

        retriever = LexicalRetriever(chunks)
        selected: List[str] = []
        seen = set()

        focus_topics = [topic for topic in topics if topic.strip()]
        if not focus_topics:
            focus_topics = ["course objectives", "core concepts", "common mistakes"]

        for topic in focus_topics[:8]:
            results = retriever.search(topic, top_k=2)
            for item in results:
                key = item.text.strip()
                if key and key not in seen:
                    seen.add(key)
                    selected.append(f"[Topic: {topic}] {item.text}")
                if len(selected) >= max_chunks:
                    break
            if len(selected) >= max_chunks:
                break

        if not selected:
            selected = chunks[:max_chunks]

        return "\n\n".join(selected)[:12000]

    def _fetch_topic_web_summary(self, topic: str) -> str:
        if not topic.strip():
            return ""
        safe_topic = quote(topic.strip().replace(" ", "_"))
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_topic}"
        headers = {"accept": "application/json", "user-agent": "ReLearnAI/1.0"}

        try:
            with httpx.Client(timeout=6.0, follow_redirects=True) as client:
                resp = client.get(wiki_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = str(data.get("extract", "")).strip()
                    if len(extract) > 25:
                        return extract[: settings.online_context_chars_per_topic]
        except Exception:
            pass

        ddg_url = "https://api.duckduckgo.com/"
        try:
            with httpx.Client(timeout=6.0, follow_redirects=True) as client:
                resp = client.get(
                    ddg_url,
                    params={
                        "q": topic,
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1",
                    },
                    headers={"user-agent": "ReLearnAI/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    abstract = str(data.get("AbstractText", "")).strip()
                    if len(abstract) > 25:
                        return abstract[: settings.online_context_chars_per_topic]
        except Exception:
            pass

        return ""

    def _topic_online_context(self, topics: List[str]) -> str:
        if not settings.enable_online_context:
            return ""

        snippets: List[str] = []
        for topic in topics[: max(1, settings.online_context_max_topics)]:
            summary = self._fetch_topic_web_summary(topic)
            if summary:
                snippets.append(f"[Web Topic: {topic}] {summary}")
        return "\n\n".join(snippets)[:3500]

    def _prompt_quiz(
        self,
        text: str,
        topics: List[str],
        num_questions: int,
        difficulty: str,
        blooms_level: str,
        coverage_scope: str,
    ) -> str:
        topic_text = ", ".join(topics) if topics else "Course Concepts"
        course_context = self._topic_guided_course_context(text, topics, max_chunks=12)
        online_context = self._topic_online_context(topics)
        online_section = (
            f"\n\nONLINE_REFERENCE_CONTEXT (secondary, optional):\n{online_context}"
            if online_context
            else "\n\nONLINE_REFERENCE_CONTEXT: none"
        )
        return (
            "You are an assessment assistant. Generate high-quality, topic-aligned diagnostic multiple-choice questions "
            "for an academic course. Return ONLY JSON array with schema: "
            "[{topic, question, options, correct_option, explanation, source_chunk}]. "
            f"Need exactly {num_questions} questions with 4 options each. "
            "Each question must be directly grounded in COURSE_CONTEXT first. "
            "Use ONLINE_REFERENCE_CONTEXT only to enrich phrasing or examples when consistent with course material. "
            "Do not introduce unrelated facts. "
            "Options should be concise and plausible. correct_option must exactly match one option string. "
            "At least 30% of questions should test application, not just definition recall. "
            f"Difficulty target: {difficulty}. "
            f"Bloom's taxonomy target: {blooms_level}. "
            f"Coverage scope: {coverage_scope}. "
            "Set source_chunk to a short excerpt copied from COURSE_CONTEXT used to form the question.\n\n"
            f"Prioritize topics: {topic_text}.\n\n"
            f"COURSE_CONTEXT:\n{course_context}"
            f"{online_section}"
        )

    def _generate_quiz_azure(
        self,
        text: str,
        topics: List[str],
        count: int,
        difficulty: str,
        blooms_level: str,
        coverage_scope: str,
    ) -> List[Dict[str, Any]]:
        client = self._azure_client()
        prompt = self._prompt_quiz(
            text,
            topics,
            count,
            difficulty=difficulty,
            blooms_level=blooms_level,
            coverage_scope=coverage_scope,
        )
        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You produce strict JSON outputs."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        parsed = self._extract_json(raw)
        return parsed if parsed else self._generate_quiz_mock(text, topics, count)

    def _generate_skill_map_azure(self, text: str, max_topics: int) -> List[Dict[str, Any]]:
        client = self._azure_client()
        prompt = self._prompt_skill_map(text, max_topics)
        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            temperature=0.1,
            messages=[
                {"role": "system", "content": "You produce strict JSON outputs."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        return self._extract_json(raw)

    def _generate_quiz_openai(
        self,
        text: str,
        topics: List[str],
        count: int,
        difficulty: str,
        blooms_level: str,
        coverage_scope: str,
    ) -> List[Dict[str, Any]]:
        client = self._openai_client()
        prompt = self._prompt_quiz(
            text,
            topics,
            count,
            difficulty=difficulty,
            blooms_level=blooms_level,
            coverage_scope=coverage_scope,
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You produce strict JSON outputs."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        parsed = self._extract_json(raw)
        return parsed if parsed else self._generate_quiz_mock(text, topics, count)

    def _generate_skill_map_openai(self, text: str, max_topics: int) -> List[Dict[str, Any]]:
        client = self._openai_client()
        prompt = self._prompt_skill_map(text, max_topics)
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": "You produce strict JSON outputs."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        return self._extract_json(raw)

    def _generate_quiz_hf(
        self,
        text: str,
        topics: List[str],
        count: int,
        difficulty: str,
        blooms_level: str,
        coverage_scope: str,
    ) -> List[Dict[str, Any]]:
        prompt = self._prompt_quiz(
            text,
            topics,
            count,
            difficulty=difficulty,
            blooms_level=blooms_level,
            coverage_scope=coverage_scope,
        )
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1200,
                "temperature": 0.2,
                "return_full_text": False,
            },
        }
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
        url = f"https://api-inference.huggingface.co/models/{settings.huggingface_model}"

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list) and data and "generated_text" in data[0]:
            parsed = self._extract_json(data[0]["generated_text"])
            if parsed:
                return parsed

        return self._generate_quiz_mock(text, topics, count)

    def _generate_skill_map_hf(self, text: str, max_topics: int) -> List[Dict[str, Any]]:
        prompt = self._prompt_skill_map(text, max_topics)
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1000,
                "temperature": 0.1,
                "return_full_text": False,
            },
        }
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
        url = f"https://api-inference.huggingface.co/models/{settings.huggingface_model}"

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list) and data and "generated_text" in data[0]:
            return self._extract_json(data[0]["generated_text"])
        return []

    def _normalize_skill_nodes(self, generated: List[Dict[str, Any]], max_topics: int) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        seen = set()

        for item in generated:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue
            key = topic.lower()
            if key in seen:
                continue
            seen.add(key)

            raw_prereqs = item.get("prerequisites", [])
            prereqs: List[str] = []
            if isinstance(raw_prereqs, list):
                for entry in raw_prereqs:
                    value = str(entry).strip()
                    if value and value.lower() != key and value.lower() not in [p.lower() for p in prereqs]:
                        prereqs.append(value)
            elif isinstance(raw_prereqs, str):
                for entry in raw_prereqs.split(","):
                    value = entry.strip()
                    if value and value.lower() != key and value.lower() not in [p.lower() for p in prereqs]:
                        prereqs.append(value)

            cleaned.append(
                {
                    "topic": topic,
                    "prerequisites": prereqs[:4],
                    "reason": str(item.get("reason", "")).strip(),
                }
            )
            if len(cleaned) >= max_topics:
                break

        known_topics = {item["topic"].lower() for item in cleaned}
        for item in cleaned:
            item["prerequisites"] = [
                prereq
                for prereq in item["prerequisites"]
                if prereq.lower() in known_topics
            ]

        return cleaned

    def _generate_skill_map_mock(self, text: str, max_topics: int) -> List[Dict[str, Any]]:
        fallback = build_skill_map(text)[:max_topics]
        return [
            {
                "topic": str(item.get("topic", "")).strip(),
                "prerequisites": list(item.get("prerequisites", [])),
                "reason": "Fallback heuristic extraction from course text.",
            }
            for item in fallback
            if str(item.get("topic", "")).strip()
        ]

    def _normalize_quiz_questions(
        self,
        generated: List[Dict[str, Any]],
        topics: List[str],
        target_count: int,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen_questions = set()
        topic_set = {topic.strip().lower(): topic.strip() for topic in topics if topic.strip()}

        for item in generated:
            if not isinstance(item, dict):
                continue

            question = str(item.get("question", "")).strip()
            if len(question) < 12:
                continue
            qkey = question.lower()
            if qkey in seen_questions:
                continue
            seen_questions.add(qkey)

            raw_topic = str(item.get("topic", "")).strip()
            topic = topic_set.get(raw_topic.lower(), raw_topic if raw_topic else (topics[0] if topics else "General"))

            raw_options = item.get("options", [])
            options: List[str] = []
            if isinstance(raw_options, list):
                for opt in raw_options:
                    text = str(opt).strip()
                    if text and text.lower() not in [o.lower() for o in options]:
                        options.append(text)
            if len(options) < 4:
                # Skip low-quality items instead of forcing weak distractors.
                continue
            options = options[:4]

            correct = str(item.get("correct_option", "")).strip()
            if not correct or correct.lower() not in [o.lower() for o in options]:
                correct = options[0]
            else:
                for opt in options:
                    if opt.lower() == correct.lower():
                        correct = opt
                        break

            explanation = str(item.get("explanation", "")).strip()
            if len(explanation) < 10:
                explanation = f"This follows directly from the course material on {topic}."

            source_chunk = str(item.get("source_chunk", "")).strip()
            if len(source_chunk) < 12:
                source_chunk = explanation[:220]

            normalized.append(
                {
                    "topic": topic,
                    "question": question,
                    "options": options,
                    "correct_option": correct,
                    "explanation": explanation,
                    "source_chunk": source_chunk[:280],
                }
            )
            if len(normalized) >= target_count:
                break

        return normalized

    def _generate_quiz_mock(self, text: str, topics: List[str], count: int) -> List[Dict[str, Any]]:
        lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 30]
        if len(lines) < 5:
            lines = [
                "A learning objective describes what a student should be able to do after instruction.",
                "Prerequisites should be checked before introducing advanced content.",
                "Frequent low-stakes quizzes help identify gaps early.",
                "Feedback loops improve long-term retention and engagement.",
                "Human-in-the-loop review improves trust and fairness in grading.",
            ]

        generated: List[Dict[str, Any]] = []
        random.seed(7)

        for idx in range(count):
            correct = lines[idx % len(lines)]
            topic = topics[idx % len(topics)] if topics else f"Topic {idx + 1}"
            distractors = random.sample(lines, k=min(3, len(lines)))
            options = distractors + [correct]
            random.shuffle(options)

            generated.append(
                {
                    "topic": topic,
                    "question": f"Which statement is most aligned with {topic}?",
                    "options": options,
                    "correct_option": correct,
                    "explanation": f"The course document explicitly states this for {topic}.",
                    "source_chunk": correct[:220],
                }
            )

        return generated

    def _course_summary_mock(self, text: str, focus_topic: str = "") -> str:
        chunks = split_into_chunks(text, chunk_size=600, overlap=80)
        overview = chunks[0][:520] if chunks else "No course material was available."
        focus = focus_topic.strip() or "Core topics"
        return (
            "1) Course Overview\n"
            f"{overview}\n\n"
            "2) Key Concepts\n"
            f"- {focus}\n"
            "- Foundational definitions and core process flow\n"
            "- Practical application and error patterns\n\n"
            "3) Prerequisites To Review\n"
            "- Fundamental terminology\n"
            "- Prior module assumptions\n\n"
            "4) High-Yield Checklist\n"
            "- Summarize each topic in one sentence\n"
            "- Attempt one quiz round\n"
            "- Review weakest topic immediately\n\n"
            "5) 3 Quick Self-Check Questions\n"
            "1. What is the main objective of this topic?\n"
            "2. Which prerequisite is most critical?\n"
            "3. What common mistake should be avoided?\n"
        )

    def _relearn_concept_mock(self, text: str, concept: str) -> str:
        chunks = split_into_chunks(text, chunk_size=650, overlap=90)
        retriever = LexicalRetriever(chunks) if chunks else None
        excerpt = ""
        if retriever:
            hits = retriever.search(concept, top_k=1)
            excerpt = hits[0].text[:520] if hits else ""
        if not excerpt and chunks:
            excerpt = chunks[0][:520]
        return (
            "1) Concept In Simple Words\n"
            f"{concept} is best understood as a practical mechanism within the course workflow.\n\n"
            "2) Why It Matters\n"
            "This concept affects downstream understanding and quiz performance.\n\n"
            "3) Step-by-Step Intuition\n"
            f"{excerpt or 'Start from the definition, identify inputs/outputs, then trace one worked path.'}\n\n"
            "4) Common Mistakes\n"
            "- Mixing definition with implementation detail\n"
            "- Skipping prerequisite assumptions\n\n"
            "5) Mini Practice Prompt\n"
            f"Explain {concept} in two lines, then solve one small example from memory.\n"
        )

    def _solved_examples_mock(self, text: str, concept: str, count: int) -> str:
        lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 24]
        if not lines:
            lines = [
                "Identify the relevant prerequisite.",
                "Apply the concept in a short reasoning chain.",
                "Check final result against expected behavior.",
            ]
        blocks: List[str] = []
        for i in range(count):
            seed = lines[i % len(lines)]
            blocks.append(
                f"Example {i + 1}\n"
                f"Problem: Solve a {concept} scenario using course logic.\n"
                f"Given: {seed}\n"
                "Steps:\n"
                "1. Identify prerequisite and current objective.\n"
                "2. Apply the core concept step-by-step.\n"
                "3. Validate against expected outcome.\n"
                "Final Answer: The concept is correctly applied with consistent reasoning.\n"
                "Why This Works: It follows the prerequisite -> application -> verification chain."
            )
        return "\n\n".join(blocks)

    def _chat_prompt(self, question: str, chunks: List[RetrievedChunk]) -> str:
        context = "\n\n".join(
            [f"[Chunk {chunk.chunk_id}] {chunk.text[:1200]}" for chunk in chunks]
        )
        return (
            "Answer the student question using only the provided course context. "
            "If unsure, say what is missing. Add references as [Chunk X].\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{context}"
        )

    def _chat_azure(self, question: str, chunks: List[RetrievedChunk]) -> str:
        client = self._azure_client()
        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a grounded teaching assistant."},
                {"role": "user", "content": self._chat_prompt(question, chunks)},
            ],
        )
        return response.choices[0].message.content or "No response generated."

    def _chat_openai(self, question: str, chunks: List[RetrievedChunk]) -> str:
        client = self._openai_client()
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a grounded teaching assistant."},
                {"role": "user", "content": self._chat_prompt(question, chunks)},
            ],
        )
        return response.choices[0].message.content or "No response generated."

    def _chat_hf(self, question: str, chunks: List[RetrievedChunk]) -> str:
        prompt = self._chat_prompt(question, chunks)
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 600,
                "temperature": 0.2,
                "return_full_text": False,
            },
        }
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
        url = f"https://api-inference.huggingface.co/models/{settings.huggingface_model}"

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list) and data and "generated_text" in data[0]:
            return data[0]["generated_text"]
        return self._chat_mock(question, chunks)

    def _chat_mock(self, question: str, chunks: List[RetrievedChunk]) -> str:
        if not chunks:
            return (
                "I could not find relevant course content. Upload a course document and ask again."
            )
        references = " ".join([f"[Chunk {chunk.chunk_id}]" for chunk in chunks[:2]])
        return (
            f"Based on the course document, your question '{question}' is addressed in these sections: "
            f"{references}. Start by reviewing the cited chunks and then attempt one quiz on that topic."
        )
