# Smoke Test Checklist

## 1) Authentication and role experience
- [ ] Register/login works for professor
- [ ] Register/login works for student
- [ ] Account and settings pages load
- [ ] Profile can be saved with domains/goals/user type

## 2) Professor governance workflow
- [ ] Create course
- [ ] Upload multiple documents
- [ ] Delete uploaded document
- [ ] Generate skill map
- [ ] Validate/edit skill entries
- [ ] Generate quiz bank
- [ ] Approve/edit quiz questions

## 3) Student adaptive learning workflow
- [ ] Enroll in course
- [ ] Dashboard loads with adaptive next action state
- [ ] Diagnostic quiz loads and submits
- [ ] Targeted quiz path works
- [ ] Results page shows score + skill impact + recommendations
- [ ] Tutor chat responds with grounded context/citations
- [ ] Learning tools generate content (summary/relearn/examples)

## 4) HITL controls
- [ ] Risk override action works
- [ ] Grade confirmation/override works
- [ ] Decisions persist after refresh

## 5) Journey and collaboration workflow
- [ ] Learning journey generation works
- [ ] Checkpoint update works
- [ ] Final project generation works
- [ ] Report upload works
- [ ] Contribution/publication submission works
- [ ] AI pre-verification fields appear
- [ ] Human review approve/reject works
- [ ] Publication outline generation works (owner)

## 6) Platform intelligence layer
- [ ] Explore search/filter/sort works
- [ ] Leaderboard loads and domain filter changes ranking
- [ ] Tech update publish works
- [ ] Notification broadcast reaches all test-user inboxes

## 7) Reliability and persistence
- [ ] `/health` endpoint returns status
- [ ] Data persists after service restart/redeploy (with Postgres)
