# 응답 버킷 2A (생성 + 저장 + 편집기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 인터뷰 가이드의 각 질문에 **응답 버킷(코드북)** 을 붙인다 — 가이드 생성 시 LLM이 질문별 버킷(라벨+정의+캐치올+부정케이스)을 만들고, `GuideRow.questions` JSONB에 중첩 저장하며, 의뢰자 대시보드 가이드 편집기에서 열람·편집한다. (PRD F2.1/F2.3)

**Architecture:** 스키마 변경은 pydantic 모델에만(저장은 이미 JSONB라 **alembic 불필요**). 생성은 기존 `prompts/guide.py` 시스템 프롬프트 + `routers/projects.py`의 구조화 출력 스키마(`_GenGuide`)를 확장하고, 서버에서 캐치올 보장·버킷 id를 결정론으로 채운다(기존 `_split_goal_from_text`·order/id 채우기와 같은 계열). 프론트는 `web/lib/api.ts` 타입 + `guide-panel.tsx` 편집기에 버킷 UI를 얹는다.

**Tech Stack:** FastAPI · pydantic · SQLAlchemy(JSONB) · Next.js14/TS · Tailwind. LLM은 OpenAI 호환 구조화 출력(forced tool_choice) + 자가교정 재시도(기존 `llm_client`).

## Global Constraints

- **브랜치:** 이 계획은 Phase 1(`feat/respondent-ui-redesign`)이 main에 랜딩된 **뒤** `main`에서 새 브랜치 `feat/response-buckets-2a`로 실행한다.
- **불변 계약 준수(CLAUDE.md):** 이번엔 생성/저장/편집만 — **집계·분류는 2B/2C다.** 버킷의 **N수(분포)는 이후 DB 실측으로 센다**(계약 1). 이 계획에서 카운트 로직을 만들지 않는다. PII·NPU 전용·provider 판별 경로는 손대지 않는다.
- **저장은 JSONB 중첩:** `GuideRow.questions`(JSONB)의 각 질문 dict 안에 `response_buckets`를 넣는다. **DB 스키마 마이그레이션을 만들지 않는다.**
- **Qwen3 필드 생략 대비:** 구조화 출력에서 필수 아닌 필드를 통째로 생략하는 실사고가 있다(기존 `_GenQuestion.goal` 승격 사례). 버킷의 `definition`도 생성 스키마에서 **필수로 승격**해 자가교정 재시도가 발동하게 한다.
- **범위 밖(다음 슬라이스로):** MECE 중첩 자동검출(F2.3.1)·유도질문 검출 패스(F2.3.6)·기타 20% 경고(F2.3.3 대시보드)는 Phase 7 evals / 2C. 여기선 **프롬프트 규칙 + 서버 캐치올 보장**까지만.
- **검증:** 백엔드는 `./.venv/Scripts/python.exe -m pytest api/tests -q` (러너 있음, TDD). 프론트는 `cd web && npm run typecheck` + `npm run build`(웹 유닛러너 없음).
- **커밋:** 한국어 현재형 서술.

---

### Task 1: 버킷 pydantic 모델 + GuideQuestion 필드

**Files:**
- Modify: `api/schemas/models.py` (`GuideQuestion` 위에 `ResponseBucket` 추가, `GuideQuestion`에 필드 추가)
- Test: `api/tests/test_response_buckets.py` (신규)

**Interfaces:**
- Produces: `ResponseBucket(id, label, definition, is_catchall, is_negative_case)` · `GuideQuestion.response_buckets: list[ResponseBucket]`

- [ ] **Step 1: 실패 테스트 작성**

Create `api/tests/test_response_buckets.py`:
```python
"""응답 버킷 모델 · 정규화 (2A)."""
from __future__ import annotations

from api.schemas.models import GuideQuestion, InterviewGuide, ResponseBucket


def test_bucket_roundtrips_inside_question():
    q = GuideQuestion(
        id="q1", text="평소 아침은 어떻게 해결하세요?", goal="아침 식사 패턴",
        response_buckets=[
            ResponseBucket(id="q1_b1", label="직접 조리", definition="집에서 밥·반찬을 차려 먹음"),
            ResponseBucket(id="q1_other", label="기타", is_catchall=True),
        ],
    )
    dumped = q.model_dump()
    assert dumped["response_buckets"][0]["label"] == "직접 조리"
    assert dumped["response_buckets"][1]["is_catchall"] is True
    # 가이드 전체 라운드트립
    g = InterviewGuide(questions=[q])
    back = InterviewGuide.model_validate(g.model_dump())
    assert back.questions[0].response_buckets[0].definition == "집에서 밥·반찬을 차려 먹음"


def test_bucket_defaults_empty():
    q = GuideQuestion(id="q1", text="t")
    assert q.response_buckets == []
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_response_buckets.py -q`
Expected: FAIL (`ImportError: cannot import name 'ResponseBucket'`)

- [ ] **Step 3: 모델 추가**

`api/schemas/models.py`에서 `class GuideQuestion(BaseModel):` **바로 위**에 추가:
```python
class ResponseBucket(BaseModel):
    """질문별 응답 분류 카테고리(코드북)이자 프로빙 목표 (PRD F2.3).

    id/분포 카운트는 서버가 채운다 — LLM 은 label/definition 만 만든다(계약 1).
    """
    id: str = ""
    label: str
    definition: str = ""              # 1문장 정의. 생성 스키마에서 필수로 승격됨(F2.3.2)
    is_catchall: bool = False         # '기타' 버킷 (F2.3.3)
    is_negative_case: bool = False    # '불편 없음' 류 (F2.3.4)
```
그리고 `GuideQuestion`에 필드 추가(기존 `order: int = 0` 다음 줄):
```python
    response_buckets: list[ResponseBucket] = Field(default_factory=list)
```
(`Field`는 이미 이 파일에서 import 되어 있다 — `InterviewGuide.questions`가 `Field(default_factory=list)`를 쓴다.)

- [ ] **Step 4: 통과 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_response_buckets.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add api/schemas/models.py api/tests/test_response_buckets.py
git commit -m "$(printf '가이드 질문에 응답 버킷 모델을 추가한다\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 2: 생성 시스템 프롬프트에 버킷 규칙 추가

**Files:**
- Modify: `api/prompts/guide.py` (`GUIDE_SYSTEM`)
- Test: `api/tests/test_response_buckets.py` (테스트 추가)

**Interfaces:**
- Consumes: 없음 (문자열 프롬프트)
- Produces: 버킷 생성 규칙이 포함된 `GUIDE_SYSTEM`

- [ ] **Step 1: 실패 테스트 추가**

`api/tests/test_response_buckets.py`에 추가:
```python
from api.prompts.guide import GUIDE_SYSTEM


def test_guide_system_has_bucket_rules():
    assert "response_buckets" in GUIDE_SYSTEM
    assert "definition" in GUIDE_SYSTEM
    assert "상호배타" in GUIDE_SYSTEM        # MECE
    assert "is_catchall" in GUIDE_SYSTEM
    assert "is_negative_case" in GUIDE_SYSTEM
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_response_buckets.py::test_guide_system_has_bucket_rules -q`
Expected: FAIL (assert "response_buckets" in GUIDE_SYSTEM)

- [ ] **Step 3: 프롬프트 규칙 추가**

`api/prompts/guide.py`의 `GUIDE_SYSTEM` 문자열 **맨 끝**(vocabulary 규칙 다음)에 이어 붙인다. 마지막 문자열 조각의 닫는 `)` 앞에 다음을 추가:
```python
    "\n- 각 문항에 response_buckets 를 4~7개 답니다. 이 버킷은 그 질문의 답변이 분류될 "
    "카테고리(코드북)이자 진행자의 프로빙 목표입니다.\n"
    "  · 각 버킷은 label(짧은 이름)과 definition(1문장 정의)을 반드시 가집니다. 정의 없는 라벨은 금지.\n"
    "  · 버킷들은 상호배타적(MECE)이고 합쳐서 답변 공간을 포괄해야 합니다. 의미가 겹치면 합치세요.\n"
    "  · 모든 질문에 is_catchall=true 인 '기타' 버킷을 하나 포함합니다.\n"
    "  · 불만·문제·어려움을 묻는 질문에는 is_negative_case=true 인 '불편 없음/해당 없음' 버킷을 포함합니다.\n"
    "  · 버킷은 분류 라벨이자 프로빙 목표입니다 — 답변이 어떤 버킷에도 안정적으로 들어가지 "
    "않을 만한 경계를 의식해 설계하세요."
```

- [ ] **Step 4: 통과 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_guide_prompt.py api/tests/test_response_buckets.py -q`
Expected: PASS (기존 guide_user 테스트 + 새 버킷 규칙 테스트 모두)

- [ ] **Step 5: 커밋**

```bash
git add api/prompts/guide.py api/tests/test_response_buckets.py
git commit -m "$(printf '가이드 생성 프롬프트에 응답 버킷 규칙을 넣는다\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 3: 생성 스키마 확장 + 버킷 정규화(캐치올 보장·id 채우기)

**Files:**
- Modify: `api/routers/projects.py` (`_GenQuestion`/`_GenGuide` 확장, `_normalize_buckets` 추가, `generate_guide` 루프에 배선)
- Test: `api/tests/test_response_buckets.py` (정규화 테스트 추가)

**Interfaces:**
- Consumes: `ResponseBucket`, `GuideQuestion` (Task 1)
- Produces: `_normalize_buckets(q: GuideQuestion) -> None` — 캐치올 보장 + 버킷 id 결정론 채우기. `generate_guide`가 각 질문에 호출.

- [ ] **Step 1: 실패 테스트 추가**

`api/tests/test_response_buckets.py`에 추가:
```python
from api.routers.projects import _normalize_buckets


def test_normalize_adds_catchall_and_ids():
    q = GuideQuestion(id="q2", text="t", response_buckets=[
        ResponseBucket(label="A", definition="a"),
        ResponseBucket(label="B", definition="b"),
    ])
    _normalize_buckets(q)
    ids = [b.id for b in q.response_buckets]
    assert ids[:2] == ["q2_b1", "q2_b2"]        # id 결정론 채움
    assert q.response_buckets[-1].is_catchall    # 캐치올 자동 추가
    assert q.response_buckets[-1].id == "q2_other"


def test_normalize_keeps_existing_catchall():
    q = GuideQuestion(id="q3", text="t", response_buckets=[
        ResponseBucket(label="A", definition="a"),
        ResponseBucket(label="기타", is_catchall=True),
    ])
    _normalize_buckets(q)
    assert sum(1 for b in q.response_buckets if b.is_catchall) == 1  # 중복 추가 안 함


def test_normalize_empty_noop():
    q = GuideQuestion(id="q4", text="t")
    _normalize_buckets(q)
    assert q.response_buckets == []   # 버킷 없으면 강제로 만들지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_response_buckets.py -q`
Expected: FAIL (`ImportError: cannot import name '_normalize_buckets'`)

- [ ] **Step 3: 생성 스키마 확장 + 정규화 구현 + 배선**

`api/routers/projects.py`에서 import에 `ResponseBucket`을 추가(기존 `from ..schemas.models import (... GuideQuestion, ...)`에 `ResponseBucket` 끼워넣기).

`_GenQuestion`/`_GenGuide` 정의(현재 89-101 부근)를 확장 — 버킷을 생성 스키마에서 필수·정의필수로 승격:
```python
class _GenBucket(ResponseBucket):
    """생성 전용 — definition 을 필수로 승격(F2.3.2). Qwen3 가 통째로 생략하는 걸 막는다."""
    definition: str


class _GenQuestion(GuideQuestion):
    """생성 전용 — goal·buckets 를 필수로 승격."""
    goal: str
    response_buckets: list[_GenBucket]


class _GenGuide(InterviewGuide):
    questions: list[_GenQuestion]
```

`_split_goal_from_text` 함수 **아래**에 정규화 함수 추가:
```python
def _normalize_buckets(q: GuideQuestion) -> None:
    """버킷 id 확정 + 캐치올 보장(F2.3.3). order/id 채우기와 같은 결정론 서버 보정.

    LLM 이 id 를 비워 보내거나 캐치올을 빠뜨리는 실사고 대비. 버킷이 아예 없으면 손대지 않는다
    (구가이드 호환).
    """
    if not q.response_buckets:
        return
    for i, b in enumerate(q.response_buckets):
        b.id = b.id or f"{q.id}_b{i + 1}"
    if not any(b.is_catchall for b in q.response_buckets):
        q.response_buckets.append(
            ResponseBucket(id=f"{q.id}_other", label="기타", is_catchall=True)
        )
```

`generate_guide`의 질문 루프(현재 `for i, q in enumerate(guide.questions):` 안, `q.id = q.id or f"q{i + 1}"` 다음)에 한 줄 추가:
```python
        _normalize_buckets(q)
```
(순서 주의: `q.id`가 먼저 확정된 뒤 `_normalize_buckets`가 그 id 로 버킷 id를 만든다.)

- [ ] **Step 4: 통과 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_response_buckets.py -q`
Expected: PASS

Run(회귀): `./.venv/Scripts/python.exe -m pytest api/tests -q`
Expected: 전체 PASS

- [ ] **Step 5: import 검사**

Run: `./.venv/Scripts/python.exe -c "import api.main; print('routes:', len(api.main.app.routes))"`
Expected: 정상 출력 (순환참조·미해결 import 없음)

- [ ] **Step 6: 커밋**

```bash
git add api/routers/projects.py api/tests/test_response_buckets.py
git commit -m "$(printf '가이드 생성이 질문별 버킷을 만들고 캐치올을 보장하게 한다\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 4: 프론트 타입 + 가이드 편집기 버킷 UI

**Files:**
- Modify: `web/lib/api.ts` (`ResponseBucket` 타입 + `GuideQuestion.response_buckets`)
- Modify: `web/app/projects/[id]/guide-panel.tsx` (질문별 버킷 목록 표시·편집)

**Interfaces:**
- Consumes: 백엔드가 내려주는 `response_buckets`
- Produces: 리서처가 버킷을 열람/추가/수정/삭제하는 편집 UI

- [ ] **Step 1: TS 타입 확장**

`web/lib/api.ts`에서 `GuideQuestion` 타입(현재 33행)을 교체하고 위에 `ResponseBucket` 추가:
```ts
export type ResponseBucket = {
  id: string;
  label: string;
  definition: string;
  is_catchall: boolean;
  is_negative_case: boolean;
};
export type GuideQuestion = {
  id: string;
  text: string;
  goal: string;
  order: number;
  response_buckets: ResponseBucket[];
};
```

- [ ] **Step 2: 편집기에 버킷 핸들러 추가**

`guide-panel.tsx`의 import에 `type ResponseBucket` 추가. `updateQuestion`/`removeQuestion` 근처에 버킷 핸들러 추가:
```tsx
  function updateBucket(qi: number, bi: number, field: "label" | "definition", value: string) {
    patch((g) => ({
      ...g,
      questions: g.questions.map((q, i) =>
        i === qi
          ? { ...q, response_buckets: q.response_buckets.map((b, j) => (j === bi ? { ...b, [field]: value } : b)) }
          : q,
      ),
    }));
  }
  function removeBucket(qi: number, bi: number) {
    patch((g) => ({
      ...g,
      questions: g.questions.map((q, i) =>
        i === qi ? { ...q, response_buckets: q.response_buckets.filter((_, j) => j !== bi) } : q,
      ),
    }));
  }
  function addBucket(qi: number) {
    patch((g) => ({
      ...g,
      questions: g.questions.map((q, i) =>
        i === qi
          ? { ...q, response_buckets: [...q.response_buckets, { id: `${q.id}_b${q.response_buckets.length + 1}`, label: "", definition: "", is_catchall: false, is_negative_case: false }] }
          : q,
      ),
    }));
  }
```

- [ ] **Step 3: `addQuestion` 이 빈 buckets 를 포함하도록**

`addQuestion`의 새 질문 객체에 `response_buckets: []`를 추가(타입 필수 필드):
```tsx
        { id: newQuestionId(), text: "", goal: "", order: g.questions.length, response_buckets: [] },
```

- [ ] **Step 4: 질문 카드 안에 버킷 목록 렌더**

각 질문 `<li>` 안, goal `<input>` 다음(현재 244행 이후)에 버킷 블록을 추가:
```tsx
                  <div className="mt-2 rounded-lg bg-surface p-3 ring-1 ring-line">
                    <p className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-faint">
                      응답 버킷 · {q.response_buckets.length}개
                    </p>
                    <ul className="space-y-1.5">
                      {q.response_buckets.map((b, bi) => (
                        <li key={b.id || bi} className="flex items-start gap-2">
                          <span
                            className={cn(
                              "mt-2 h-2 w-2 shrink-0 rounded-full",
                              b.is_catchall ? "bg-ink-faint" : b.is_negative_case ? "bg-pivot" : "bg-accent-solid",
                            )}
                            aria-hidden
                          />
                          <input
                            value={b.label}
                            onChange={(e) => updateBucket(i, bi, "label", e.target.value)}
                            placeholder="버킷 이름"
                            className={cn(inputCls, "text-meta")}
                          />
                          <input
                            value={b.definition}
                            onChange={(e) => updateBucket(i, bi, "definition", e.target.value)}
                            placeholder="1문장 정의"
                            className={cn(inputCls, "text-meta flex-[2]")}
                          />
                          <button
                            type="button"
                            onClick={() => removeBucket(i, bi)}
                            aria-label="버킷 삭제"
                            className="mt-1 rounded px-2 py-1 text-meta text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                          >
                            ✕
                          </button>
                        </li>
                      ))}
                    </ul>
                    <Button size="sm" variant="ghost" className="mt-1.5" onClick={() => addBucket(i)}>
                      + 버킷 추가
                    </Button>
                  </div>
```
(위 `<input>` 두 개가 한 줄에 나란히 서도록, 이 블록을 감싼 질문 카드의 flex 레이아웃과 충돌하지 않는지 Task 5 시각 확인에서 점검한다. `flex` 부모 안이라면 `flex-wrap`이 필요할 수 있다 — 실제 렌더 보고 조정.)

- [ ] **Step 5: 검증**

Run: `cd web && npm run typecheck`
Expected: PASS (`response_buckets` 필수 필드가 모든 GuideQuestion 생성 지점에 채워짐 — Step 3에서 addQuestion 보강)

Run: `cd web && npm run build`
Expected: 성공

- [ ] **Step 6: 커밋**

```bash
git add web/lib/api.ts web/app/projects/[id]/guide-panel.tsx
git commit -m "$(printf '가이드 편집기에서 질문별 응답 버킷을 열람·편집하게 한다\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 5: 전체 검증 + 실동작 확인

**Files:** 없음(검증)

- [ ] **Step 1: 백엔드 전체 + 프론트 전체**

```bash
./.venv/Scripts/python.exe -m pytest api/tests -q
cd web && npm run typecheck && npm run build && npm run lint
```
Expected: 모두 PASS

- [ ] **Step 2: 실동작(로컬 또는 배포 테스트 프로젝트)**

새 프로젝트로 가이드를 생성 → 각 질문에 버킷 4~7개(+기타)가 붙는지, 편집기에서 버킷을 고치고 저장하면 라운드트립되는지 확인. (헤드리스 `/qa` 또는 로컬 dev.) LLM 생성이라 버킷 품질(MECE 등)은 눈으로 스팟체크 — 자동 MECE 검출은 이번 범위 아님.

- [ ] **Step 3: 필요 시 시각/문구 조정 후 커밋**

```bash
git add api web
git commit -m "$(printf '버킷 2A 검증 피드백을 반영한다\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

- **Spec 커버리지(F2.1/F2.3):** 버킷 생성(Task 2·3)·정의필수(F2.3.2, `_GenBucket` 승격)·캐치올 필수(F2.3.3, `_normalize_buckets`)·부정케이스(F2.3.4, 프롬프트)·4~7개(F2.3.5, 프롬프트)·MECE 규칙(F2.3.1, 프롬프트) 커버. **자동 MECE 중첩검출·유도질문 검출 패스(F2.3.1/F2.3.6 자동화)·기타 20% 경고(F2.3.3 대시보드)는 명시적으로 범위 밖**(Phase 7/2C)으로 이월.
- **플레이스홀더 스캔:** 실제 pydantic/TS/JSX 코드와 정확한 pytest/명령을 담음. Task 4 Step 4에 flex-wrap 조정 여지를 "시각 확인에서" 로 명시(웹 유닛러너 부재).
- **타입 일관성:** `ResponseBucket`(py, Task 1) ↔ `ResponseBucket`(ts, Task 4) 필드 일치(id/label/definition/is_catchall/is_negative_case). `_GenBucket`→`_GenQuestion.response_buckets`(Task 3). `_normalize_buckets(q)`는 Task 3에서 정의·호출·테스트가 이름 일치.
- **가정 확인:** `GuideRow.questions`는 JSONB(`api/services/db.py:70`) → 버킷 중첩에 마이그레이션 불필요. `Field`는 `schemas/models.py`에 이미 import됨. `_GenQuestion`(goal 필수)·`_split_goal_from_text`·generate_guide 루프 구조는 `routers/projects.py` 확인됨.
