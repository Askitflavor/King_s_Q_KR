# King's Quest (2015) 한국어 패치

Steam판 **King's Quest (2015)**의 비공식 한국어 패치입니다.

- 배포 버전: `v0.1.0`
- 대상 Steam 앱: `345390`
- 확인 기준 빌드: `1487864`
- 번역 범위: 챕터 1~5 및 에필로그 전체 초벌 번역
- 음성: 영어 유지

아직 전체 플레이 검수를 마친 최종판이 아닙니다. 번역 누락, 오탈자, 문맥 오류, 줄바꿈 문제가 남아 있을 수 있습니다.

## Windows 설치

1. 저장소의 파일을 ZIP으로 내려받아 게임 폴더 밖에 전부 압축 해제합니다.
2. 게임을 완전히 종료합니다.
3. `KingsQuest_KO_Setup.exe`를 실행합니다.
4. 자동으로 확인된 게임 경로를 검토하거나 직접 게임 폴더를 선택합니다.
5. **설치 상태 검사** 후 **한글 패치 설치**를 누릅니다.
6. Steam의 게임 언어를 영어로 두고 실행합니다.
7. 게임 설정에서 자막 표시를 켭니다.

게임 폴더는 `GrahamsGame` 폴더가 들어 있는 상위 폴더를 선택해야 합니다. 설치기는 지원되는 원본 파일의 해시를 검사하며, 버전이 다르거나 필요한 파일이 없으면 덮어쓰지 않습니다.

## 복원

설치 화면의 **원본으로 복원** 기능을 사용합니다. 설치 과정에서 만들어진 게임 폴더의 `.kq-ko-patch` 백업 폴더를 삭제하지 마세요.

설치가 중단되었다면 게임을 실행하기 전에 **중단된 작업 복구**를 사용하세요.

## 명령줄 사용

아래 경로는 실제 설치 위치에 맞게 바꾸세요.

```powershell
.\KingsQuest_KO_CLI.exe verify --game "D:\SteamLibrary\steamapps\common\King's Quest"
.\KingsQuest_KO_CLI.exe install --game "D:\SteamLibrary\steamapps\common\King's Quest"
.\KingsQuest_KO_CLI.exe restore --game "D:\SteamLibrary\steamapps\common\King's Quest"
```

특정 구간만 설치하려면 다음과 같이 지정할 수 있습니다. `6`은 에필로그입니다.

```powershell
.\KingsQuest_KO_CLI.exe install --chapters 1,2,6 --game "D:\SteamLibrary\steamapps\common\King's Quest"
```

## Linux / SteamOS 계열 환경

Python 3.9 이상과 `liblzo2`가 필요합니다. 게임과 배포 파일이 모두 보이는 Linux 환경에서 실행하세요.

```bash
python3 patcher.py verify --game "/실제/SteamLibrary/steamapps/common/King's Quest"
python3 patcher.py install --game "/실제/SteamLibrary/steamapps/common/King's Quest"
python3 patcher.py restore --game "/실제/SteamLibrary/steamapps/common/King's Quest"
python3 patcher.py recover --game "/실제/SteamLibrary/steamapps/common/King's Quest"
```

SteamOS 및 ARM64 환경의 실제 게임 구동은 충분히 검증되지 않았습니다. 원본 게임 파일을 별도로 보관한 뒤 시험하세요.

## 주요 파일

- `KingsQuest_KO_Setup.exe`: Windows 설치·검사·복원 도구
- `KingsQuest_KO_CLI.exe`: Windows 명령줄 도구
- `patcher.py`, `patch_codec.py`: Python 기반 적용 도구
- `manifest.json`, `patch-data.zip`: 지원 원본 정보와 변경 데이터
- `CHECKSUMS.sha256`: 배포 파일 무결성 확인값
- `TEST_REPORT.md`, `VALIDATION.json`: 테스트 및 검증 정보
- `licenses/`: 함께 배포되는 구성 요소의 라이선스 문서

원본 게임 실행 파일, 원본 게임 데이터 전체, 음성 파일은 포함하지 않습니다.

## 문제 제보

문제가 발생하면 다음 정보를 함께 기록해 주세요.

- 발생 챕터와 장면
- 화면에 나온 원문 또는 한국어 문구
- 문제 화면
- 게임 빌드와 실행 환경

게임 업데이트나 Steam 무결성 검사를 수행하면 패치가 원본 상태로 돌아갈 수 있습니다.

