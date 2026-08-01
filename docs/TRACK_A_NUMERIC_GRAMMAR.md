# Track A Numeric Grammar

## 목적

Track A는 근거와 결정적 계산 결과를 설명하지만 새로운 숫자를 만들거나 표기를 임의로 바꾸지 않는다. 모든 claim의 숫자는 지원 문법에 맞아야 하며, `numeric_tokens` 배열은 claim text에서 추출되는 숫자와 순서·철자까지 정확히 일치해야 한다.

## 허용 형식

지원 문법은 canonical ASCII 숫자만 허용한다.

```text
sign        := "+" | "-"
integer     := digits | grouped_digits
fraction    := "." digits
percent     := "%"
number      := sign? integer fraction? percent?
```

허용 예:

```text
0
-12
+3
1,234
0.5
12.50
9.375%
12.50%
```

규칙:

- 숫자는 ASCII `0`부터 `9`까지만 사용한다.
- 쉼표 표기는 첫 그룹 1~3자리 이후 정확히 3자리 그룹을 사용한다.
- 소수점 앞뒤에 모두 숫자가 있어야 한다.
- 부호와 `%` 기호는 claim text와 `numeric_tokens`에 그대로 유지한다.
- 한글 단위는 숫자 바로 뒤에 올 수 있다. 예: `0.5미터`.
- ASCII 식별자 내부의 숫자(`R1`, `A12B`)는 claim numeric token으로 취급하지 않는다.

## 금지 형식

다음 표기는 `UNSUPPORTED_NUMERIC_SYNTAX`로 거부한다.

```text
1e3
1E-3
.5
1_000
12,34
1,23,456
½
１２３
10²
⑩
```

금지 이유:

- 과학적 표기와 underscore는 허용 문법 밖이다.
- `.5`는 `0.5`로 자동 변환하지 않는다.
- 잘못된 쉼표 그룹은 일부 숫자 token으로 분리해 통과시키지 않는다.
- Unicode 숫자, 분수, 위첨자, 원문자 숫자는 ASCII 숫자로 자동 정규화하지 않는다.

## `numeric_tokens` 일치 규칙

claim text에서 추출한 지원 token과 선언 배열은 다음 항목이 모두 같아야 한다.

- token 개수
- 원문 순서
- 부호
- 쉼표
- 소수점과 뒤쪽 0
- `%` 기호

예:

```json
{
  "text": "접면 비율은 9.375%이다.",
  "numeric_tokens": ["9.375%"]
}
```

다음은 `NUMERIC_TOKEN_MISMATCH`다.

```json
{
  "text": "접면 비율은 9.375%이다.",
  "numeric_tokens": ["9.375"]
}
```

```json
{
  "text": "면적은 1,234이다.",
  "numeric_tokens": ["1234"]
}
```

## Provenance 규칙

지원 문법에 맞는 token도 다음 중 하나에서 정확히 같은 문자열을 찾을 수 있어야 한다.

1. claim이 참조한 evidence excerpt
2. claim이 명시적으로 참조한 `SUCCESS` CalculationResult의 입력, 치환식, raw result, display result 또는 comparison

예를 들어 evidence가 `1,234`라면 Track A는 이를 `1234`로 바꿀 수 없다. Evidence가 `.5`라면 Track A가 임의로 `0.5`를 쓸 수 없다. 먼저 deterministic parser 또는 Math Engine이 `0.5`를 명시적으로 생성해야 한다.

참조하지 않은 CalculationResult의 숫자는 claim에 사용할 수 없다. 실패한 계산도 숫자 권위가 되지 않는다.

## 오류 구분

### `UNSUPPORTED_NUMERIC_SYNTAX`

Claim text에 허용 문법 밖의 숫자 의미가 존재한다. 빈 `numeric_tokens`를 선언해도 우회할 수 없다.

### `NUMERIC_TOKEN_MISMATCH`

Claim text에는 지원 숫자 token이 있지만 `numeric_tokens`가 원문과 정확히 일치하지 않는다.

### `unregistered numeric token`

Claim과 선언은 일치하지만 동일 문자열이 참조 evidence 또는 성공한 참조 계산에 없다.

## 작성 절차

Track A 출력 전 다음 순서로 확인한다.

```text
claim text 작성
-> 허용 ASCII 숫자 형식인지 확인
-> 나타나는 순서대로 numeric_tokens 복사
-> 각 token의 citation 또는 CalculationResult 출처 확인
-> 쉼표·부호·소수점·%가 원문과 같은지 확인
```
