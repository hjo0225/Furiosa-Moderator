# n8n — 인터뷰 응답 Discord 알림

`interview-notify.workflow.json` 을 n8n 에 import 하면 아래 흐름이 생긴다.

```
Webhook(POST /mindlens-interview) → Format embed(Code) → Discord webhook(HTTP Request)
```

## 설정

1. n8n → **Import from File** 로 `interview-notify.workflow.json` 을 불러온다.
2. **Webhook** 노드의 **Production URL** 을 복사한다. 이 값을 mindlens api 의
   `N8N_WEBHOOK_URL`(Secret Manager)에 넣는다.
3. Discord 채널 → 채널 설정 → 연동 → **웹후크** 생성 후 URL 복사.
4. n8n 인스턴스 환경변수 `DISCORD_WEBHOOK_URL` 에 그 값을 넣는다
   (또는 **Discord webhook** 노드의 `url` 을 직접 채운다).
5. 워크플로우를 **Activate**.

## mindlens → n8n payload 계약

`api/services/notify.py::_build_payload` 가 보내는 JSON:

| 필드 | 설명 |
|---|---|
| `event` | 항상 `session.completed` |
| `project` | `id` · `title` · `topic` |
| `session` | `id` · `respondent_ref`(해시) · `asked` · `duration_sec` |
| `metrics.emotion` | `{라벨: 수}` |
| `metrics.coverage` | `{covered: [문항id], total: n}` |
| `summary` | 세션 요약(생성 실패 시 `null`) |
| `transcript` | 마스킹된 문답 합본 |
| `dashboard_url` | 대시보드 링크 |

원문 오디오·비마스킹 PII 는 담기지 않는다.

## 보안(현 상태)

HMAC 서명은 생략됐다. Webhook Production URL 자체를 시크릿으로 취급한다.
향후: Webhook 뒤에 정적 토큰/서명 검증 노드를 추가할 수 있다.
