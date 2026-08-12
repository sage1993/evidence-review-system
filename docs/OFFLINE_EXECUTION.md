# Offline Execution Boundary

## 보증 수준

이 프로젝트는 오프라인 실행 보증과 사람의 릴리스 승인 보증을 서로 독립된 보증 차원(independent assurance dimensions)으로 구분한다.

### `APPLICATION_OFFLINE_GUARD`

프로젝트가 직접 검증하는 애플리케이션 수준 경계다.

포함되는 제어:

- packaged Python runtime에서 금지된 network client import 탐지
- `subprocess`, `os.system`, `os.popen`, asyncio subprocess API 탐지
- literal `__import__()` 및 `importlib.import_module()`의 금지 모듈 탐지
- Python runtime의 non-loopback `socket.create_connection` 차단
- non-loopback `socket.socket.connect`와 `connect_ex` 차단
- non-loopback UDP `sendto` 차단
- release manifest의 `path`와 `relative_path`가 workspace 밖으로 나가지 않는지 검증
- source scanner parse 실패를 검증 실패로 처리

허용되는 로컬 통신:

- IPv4 loopback `127.0.0.0/8`
- IPv6 loopback `::1`
- `localhost`
- Unix-domain socket과 지원되는 로컬 abstract socket

localhost browser review UI와 동일 프로세스·호스트의 로컬 서비스는 계속 사용할 수 있다.

### `OS_ISOLATED`

운영체제나 컨테이너가 제공하는 별도 격리 수준이다. 애플리케이션 검증만으로는 이 수준을 주장하지 않는다.

예:

- Windows Defender Firewall에서 실행 파일의 outbound 연결 차단
- Docker 또는 Podman `--network none`
- Linux network namespace
- VM 또는 별도 보안정책으로 외부 네트워크 인터페이스 제거

Release report의 기본값은 다음과 같다.

```json
{
  "offline_assurance": "APPLICATION_OFFLINE_GUARD",
  "offline_policy_version": 1,
  "cryptographic_network_isolation_verified": false
}
```

OS 격리를 별도로 적용하더라도 현재 자동 release validator는 해당 host 설정을 증명하지 않는다. 운영 기록에서 방화벽 규칙, container command, namespace 설정 등의 증거를 별도로 보관해야 한다.

### `PROCESS_ATTESTATION`

사람이 특정 release candidate와 final review packet을 검토했다는 내부 절차 기록이다. Canonical contract는 `evidence-review/human-attestation`이고 파일명은 `human-attestation.json`이다.

이 보증은 다음 내용을 확인한다.

- named reviewer ID가 비어 있지 않음
- 검토 시각에 timezone이 포함됨
- `REVIEWED_AND_ACCEPTED_FOR_RELEASE` 문구가 정확함
- release candidate hash가 현재 산출물과 정확히 일치함
- packet hash가 현재 packet과 정확히 일치함
- 필수 checklist 항목이 모두 `PASS`이고 evidence locator를 가짐
- 기록이 append-only 방식으로 생성됨

Release manifest는 사람 절차 보증을 다음과 같이 별도로 기록한다.

```json
{
  "attestation_assurance": "PROCESS_ATTESTATION",
  "cryptographic_identity_verified": false
}
```

`PROCESS_ATTESTATION`은 전자서명이나 신원 인증이 아니다. JSON 파일 보유만으로 reviewer identity가 암호학적으로 증명되지 않는다. 공개키, 인증서, 계정 세션 또는 서명 검증을 수행하지 않으므로 `cryptographic_identity_verified`는 항상 `false`다.

오프라인 보증과 사람 절차 보증은 독립된 값이다. 예를 들어 `APPLICATION_OFFLINE_GUARD`가 통과해도 process attestation이 없으면 release는 `BLOCKED`이며, 유효한 process attestation이 있어도 `OS_ISOLATED`를 주장할 수 없다.

## 애플리케이션 guard가 보장하지 않는 항목

`APPLICATION_OFFLINE_GUARD`는 완전한 보안 sandbox가 아니다.

다음 공격이나 환경은 별도 OS 통제가 필요하다.

- hostile 또는 수정된 Python interpreter
- native extension이나 외부 바이너리의 직접 네트워크 접근
- guard 설치 전에 생성된 연결 또는 file descriptor
- guard 설치 전에 시작된 외부 프로세스
- 다른 사용자나 관리자 권한으로 실행되는 프로세스
- runtime package 밖의 임의 스크립트
- 운영자가 release manifest 검증 이후 파일을 변경하는 경우

## Runtime 정책

CLI는 command dispatch 전에 network guard를 설치한다.

차단 대상:

```text
socket.create_connection(remote)
socket.socket.connect(remote)
socket.socket.connect_ex(remote)
socket.socket.sendto(..., remote)
```

Loopback과 Unix-domain socket은 원래 socket 구현으로 위임한다. DNS를 사용해 hostname을 확인하지 않으며, `localhost` 이외의 hostname은 허용하지 않는다.

## Static source 정책

Release validator와 runtime source check는 동일한 policy version과 AST scanner를 사용한다.

금지 예:

```python
import requests
import subprocess
from urllib import request
os.system("command")
asyncio.create_subprocess_exec("command")
__import__("httpx")
importlib.import_module("aiohttp")
```

문자열 literal이 아닌 dynamic import는 static scanner가 완전히 판별할 수 없다. 따라서 runtime package는 dynamic import 자체를 최소화하고, OS 격리가 필요한 배포에서는 별도 네트워크 차단을 적용한다.

## Release manifest 경계

Release manifest의 모든 `path`와 `relative_path`는 파일을 읽기 전에 workspace root 아래의 안전한 상대경로인지 확인한다.

거부 예:

```text
../outside.txt
/tmp/outside.txt
C:/outside.txt
nested\file.txt
```

Symlink를 따라 resolve한 결과가 workspace 밖이면 거부한다.

## 최종 릴리스 ZIP 검증

Release builder는 candidate hash와 process attestation을 확인하기 전에 다음 최종 산출물을 다시 연다.

- `codex-workspace.zip`의 `bundle-manifest.json`
- `chatgpt-web-runtime.zip`의 `runtime-manifest.json`

검증기는 ZIP을 **without extracting** 방식으로 처리한다. 파일시스템에 풀지 않고 각각의 고유한 `ZipInfo`를 통해 member bytes를 읽어 내부 manifest의 `path`, `size`, `SHA-256`과 직접 비교한다.

다음 조건은 모두 실패다.

- 출력 디렉터리의 필수 산출물 누락 또는 예상하지 않은 파일
- manifest 누락·중복·잘못된 format/version/files 구조
- manifest에 선언된 파일 누락 또는 선언되지 않은 ZIP member
- ZIP member 또는 manifest entry의 절대경로, `.`·`..`, 빈 경로 요소, 역슬래시, drive-prefixed 경로
- 동일 경로 중복
- Windows에서 같은 파일로 취급될 수 있는 **case-fold collisions**
- 실제 byte size 또는 SHA-256 불일치

오류는 `release-validation.json`의 `release_output`에 기록된다. 하나라도 실패하면 종합 검증 상태는 `FAIL`이고 release reason code에 `RELEASE_OUTPUT_VALIDATION_FAILED`가 추가된다. 유효한 process attestation이 존재하더라도 이 상태에서는 release가 `BLOCKED`이며 tag를 만들 수 없다.

이 검증은 산출물 생성 이후 검증 시점까지의 무결성을 확인한다. 검증 이후 외부 프로세스가 파일을 바꾸는 공격을 막는 배포 서명이나 immutable storage를 제공하지는 않는다.

## Windows OS 격리 예시

관리자 PowerShell에서 실제 배포 executable 또는 Python executable을 대상으로 outbound 차단 규칙을 만든다.

```powershell
New-NetFirewallRule `
  -DisplayName "Evidence Review Offline" `
  -Direction Outbound `
  -Program "C:\path\to\python.exe" `
  -Action Block
```

검증 후 규칙 상태를 기록한다.

```powershell
Get-NetFirewallRule -DisplayName "Evidence Review Offline"
```

로컬 browser UI가 필요하면 프로그램 단위 차단과 localhost 동작을 실제 배포 환경에서 함께 검증해야 한다.

## Container 격리 예시

```bash
docker run --rm --network none \
  -v "$PWD/workspace:/workspace" \
  evidence-review:local \
  evidence-review --help
```

`--network none` 적용 사실과 실행 command를 release 운영 기록에 보관한다.

## 검증 체크리스트

```text
[ ] release report가 APPLICATION_OFFLINE_GUARD를 기록함
[ ] offline_policy_version이 runtime과 validator에서 같음
[ ] source scanner finding이 없음
[ ] non-loopback TCP와 UDP가 차단됨
[ ] localhost review UI가 동작함
[ ] manifest path escape가 거부됨
[ ] bundle-manifest.json과 runtime-manifest.json이 실제 ZIP bytes와 일치함
[ ] ZIP member의 duplicate 및 case-fold collisions가 없음
[ ] release_output 검증 상태가 PASS임
[ ] OS_ISOLATED를 주장할 경우 별도 운영 증거가 있음
[ ] release manifest가 PROCESS_ATTESTATION을 기록함
[ ] release candidate hash와 packet hash가 정확히 일치함
[ ] cryptographic_identity_verified가 false임
```

## Application socket and resolver boundary

The application-level offline guard is not an OS sandbox. It patches outbound socket and resolver capabilities used by the packaged Python runtime:

- DNS and reverse lookup APIs accept only localhost or literal loopback addresses.
- TCP connect, connect_ex, UDP sendto, sendmsg, and connected send/sendall reject non-loopback peers.
- Loopback TCP/UDP and local Unix-domain sockets remain available for the local review server.
- cryptographic_network_isolation_verified remains false; OS firewall, namespace, container, or interpreter isolation must be evidenced separately.