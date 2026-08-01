# Ansim 용도지역 변경 규칙 후보 검토

## 상태

이 문서의 세 규칙은 `rules/candidates/`에만 존재한다. 사람 검토와 승격 전에는 `rules/manifests/active.json`에 포함하지 않으며 승인 규칙으로 실행하지 않는다.

## 적용 범위

세 규칙은 모두 다음 조건이 함께 충족될 때만 해당 기준값을 평가한다.

- 현재 용도지역: `제2종일반주거지역`
- 변경 용도지역: `준주거지역`
- 근거 문서: `LAW1-2025-08-14`
- 근거 페이지: PDF 16쪽

## 검토 후보

| 후보 | 평가 | 경계값 | 후보 SHA-256 |
|---|---|---:|---|
| `ANSIM-ZONING-CHANGE-FAR-MAX-400@1.0.0.json` | 계획 용적률 `≤ 400` | `400` 적합, `401` 부적합 | `64b258161117929afb17a64fbd506957dfa7c4948b32d548da0d40327792e156` |
| `ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15@1.0.0.json` | 계획 공공기여율 `≥ 15` | `15` 적합, `14.9999` 부적합 | `65d4bb4207dd638429bbadb73b7ec73bd283f8d74feb109646c17ce82a9c040c` |
| `ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85@1.0.0.json` | 계획 주거비율 `≥ 85` | `85` 적합, `84.9999` 부적합 | `d8914f72a1cc5579003fcea68ab57d4cacb5ec32f2d4c1782b7e8c44854a5977` |

## 공통 근거

- `EVID-3B4E0412D8ABBE082CD0`: 조항 2-4-1 적용 문맥
- `EVID-854183945912B0BC0216`: 준주거지역으로 변경되는 경우

## 개별 근거

- `EVID-BC6AD0A708A435CE06F4`: 기본용적률 400% 이하
- `EVID-B3705E1179E7F6382060`: 제2종일반주거지역 상향 시 공공기여율 15% 이상
- `EVID-A6FDBC7C26DBB9E5E241`: 주거 비율 85% 이상

모든 citation ID는 reviewer HTML의 조회 계약에 맞게 `CIT-<evidence_id>` 형식을 사용한다.

## 승인 전 필수 확인

1. PDF 16쪽 원문과 각 Evidence 레코드의 페이지·좌표·source SHA-256이 일치한다.
2. 현재·변경 용도지역의 적용 범위가 세 규칙에 모두 포함되어 있다.
3. 용적률은 `lte`, 공공기여율과 주거비율은 `gte` 연산자를 사용한다.
4. 경계값과 바로 바깥값 테스트가 예상 상태를 반환한다.
5. 후보 파일 SHA-256이 위 표와 일치한다.
6. 규칙 결과는 사람의 최종 판정을 대신하지 않으며 `human_decision_required`가 `true`이다.

## 승격 원칙

승격은 이름이 기록된 사람이 직접 수행해야 한다. `promote_candidate`는 후보 원본을 보존하고 승인 사본에 reviewer ID, ISO 날짜, 후보 SHA-256을 기록한 뒤 active manifest를 갱신한다. 자동화 테스트나 에이전트가 사람의 승인 기록을 대신 작성해서는 안 된다.
