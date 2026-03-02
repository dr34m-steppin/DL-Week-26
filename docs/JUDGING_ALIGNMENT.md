# Judging Alignment Matrix

## 1) Clarity and Alignment of Solution
How we align:
- The product demonstrates one clear adaptive loop and a broader collaborative platform extension
- Documentation clearly separates implemented features from roadmap items

Evidence:
- Course adaptive loop pages
- Journey and contribution workflows
- Platform discovery/notification/leaderboard pages

## 2) Execution and Completeness
How we align:
- Working full-stack system with role-based workflows and persistent deployment path
- Supports students, professors, and professional profile-based usage

Evidence:
- `/prof/course/{id}` governance workflow
- `/student/course/{id}/dashboard` adaptive loop
- `/journeys`, `/contributions`, `/explore`, `/leaderboard`, `/notifications`
- testbench setup and smoke validation documents

## 3) Impact and Risk Awareness
How we align:
- Learners receive concrete intervention recommendations and mastery deltas
- High-impact AI decisions are reviewable and overridable by humans
- Contribution quality checks include similarity thresholds and human verification

Evidence:
- Risk and grading review panels
- AI pre-verification metrics on contributions
- SnapScore component visibility

## 4) Human-in-the-Loop Integration
How we align:
- Critical decisions are intentionally human-governed
- Review actions support rationale capture and auditability

Implemented HITL checkpoints:
- Skill map validation/editing
- Quiz question approval/editing
- Risk override
- Grade finalization
- Contribution approval/rejection

## 5) Transparency and Interpretability
How we align:
- Tutor outputs are grounded in uploaded content
- Decision support surfaces confidence/rationale fields
- Scoring behavior is formula-driven and inspectable

## 6) Creativity and Innovation
How we align:
- Goes beyond a tutor bot into a collaborative learning and contribution ecosystem
- Connects learning progress with verified outputs and domain reputation
- Converts publications into structured learning outlines and optional courses

## 7) Real-World Applicability
How we align:
- Multi-user, persistent deployment model via Render + Postgres
- Cross-role collaboration between students, professors, and professionals
- Roadmap supports LMS, vector, and graph extensions

## 8) Responsible AI in Education
How we align:
- Explainability and fallback consistency
- Human agency in consequential decisions
- Minimal-data storage footprint with role-based access
- Explicit limitation disclosure to avoid overclaiming
