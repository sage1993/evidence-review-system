# Offline Execution Boundary

## 보증 수준

이 프로젝트는 다음 두 보증 수준을 구분한다.

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
[ ] OS_ISOLATED를 주장할 경우 별도 운영 증거가 있음
```
