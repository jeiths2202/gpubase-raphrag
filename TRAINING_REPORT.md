# QLoRA 모델 학습 보고서

> **작성일**: 2026-02-01
> **학습 기간**: 2026-01-30 ~ 2026-02-01
> **작업 디렉토리**: `/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130`

---

## 1. 학습 개요

### 1.1 목적
TmaxSoft 제품군(OpenFrame, Tibero, Tmax)의 일본어 기술 매뉴얼 PDF를 기반으로 QLoRA 파인튜닝을 수행하여, 제품별 기술 지원 어시스턴트 어댑터를 생성합니다.

### 1.2 학습 프레임워크

| 항목 | 설정값 |
|------|--------|
| 기반 모델 | **Qwen/Qwen2.5-7B-Instruct** |
| 학습 기법 | **QLoRA** (4-bit NF4 양자화 + LoRA) |
| 양자화 설정 | 4-bit, NF4, Double Quantization |
| LoRA Rank (r) | 64 |
| LoRA Alpha | 16 |
| LoRA Dropout | 0.1 |
| Target Modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| GPU | NVIDIA A100-SXM4-40GB (GPU 5, 6) |
| Compute Dtype | bfloat16 |

### 1.3 학습 파라미터

| 파라미터 | 값 |
|----------|-----|
| Epochs | 3 |
| Batch Size | 1~2 |
| Gradient Accumulation Steps | 8~16 |
| Learning Rate | 2e-4 |
| Warmup Ratio | 0.03 |
| Weight Decay | 0.001 |
| Max Sequence Length | 1024 |
| Optimizer | paged_adamw_32bit |
| LR Scheduler | cosine |
| Eval Split | 10% |

---

## 2. 학습 데이터

### 2.1 데이터 소스 (PDF 매뉴얼)

| 디렉토리 | 문서 수 | 제품 |
|----------|---------|------|
| `Tmax_6.0_v2.1.1_JP/` | 34개 | Tmax 6.0 일본어 매뉴얼 |
| `Tibero 7 FixSet01 Manual Set v2.1.1_jp/` | 28개 | Tibero 7 일본어 매뉴얼 |
| `XSP_Openframe 7.3_v3.2.1_JP/` | 28개 | XSP OpenFrame 7.3 일본어 매뉴얼 |

### 2.2 학습 데이터 형식 (JSONL)

```json
{
  "instruction": "섹션 제목에 대해 설명해 주세요.",
  "input": "제품: Tibero 7, 문서: Administrator's_Guide",
  "output": "해당 섹션의 상세 내용..."
}
```

### 2.3 데이터 생성 유형

PDF에서 추출한 섹션을 기반으로 다음 유형의 Q&A 쌍을 생성:

1. **섹션 설명** (`section_explanation`): 각 섹션의 내용 설명
2. **설치 가이드** (`installation`): 설치 관련 키워드 포함 섹션
3. **에러/문제해결** (`troubleshooting`): 에러, 문제 관련 섹션
4. **명령어/API** (`command_api`): 명령어, API, 함수 관련 섹션
5. **설정/구성** (`configuration`): 설정, 파라미터 관련 섹션

---

## 3. 학습 결과

### 3.1 OpenFrame MVS 다국어 어댑터

**저장 위치**: `openframe_qlora_adapter/`

| 언어 | 학습 예제 | Train Loss | Eval Loss | 학습 시간 | 완료 시각 |
|------|-----------|------------|-----------|-----------|-----------|
| 한국어 (ko) | 30,388 | 0.394 | 0.233 | 6.2시간 | 1/30 21:21 |
| 일본어 (ja) | 30,388 | 0.398 | 0.233 | 7.8시간 | 1/31 05:20 |
| 영어 (en) | 21,275 | 0.619 | 0.517 | 4.5시간 | 1/31 13:10 |
| **소계** | **82,051** | - | - | **~18.5시간** | - |

**어댑터 경로**:
```
openframe_qlora_adapter/
├── openframe_ko_20260130_150120/  (한국어)
├── openframe_ja_20260130_212422/  (일본어)
└── openframe_en_20260131_083716/  (영어)
```

### 3.2 제품별 QLoRA 어댑터

**저장 위치**: `qlora_adapters/`

| 제품 | 학습 예제 | Train Loss | Eval Loss | 학습 시간 | 완료 시각 |
|------|-----------|------------|-----------|-----------|-----------|
| **Tibero 7** | 35,310 | 0.248 | **0.065** | 8.2시간 | 2/1 03:05 |
| **Tmax 6.0** | 27,897 | 0.231 | **0.052** | 7.0시간 | 2/1 21:00 |
| **XSP OpenFrame 7.3** | 19,323 | 0.295 | 0.077 | 4.4시간 | 2/1 13:50 |
| **MSP OpenFrame 7.3** | 18,990 | 0.299 | 0.074 | 4.3시간 | 1/31 17:33 |
| **VOS3 OpenFrame 2.0** | 5,049 | 0.377 | 0.098 | 1.2시간 | 1/31 18:48 |
| **OpenFrame COBOL 4** | 1,779 | 0.657 | 0.276 | 23분 | 2/1 09:22 |
| **OpenFrame ASM 4** | 378 | 0.945 | 0.431 | 5분 | 2/1 03:11 |
| **소계** | **108,726** | - | - | **~25.5시간** | - |

**어댑터 경로**:
```
qlora_adapters/
├── tibero7/openframe_ko_20260131_184925/
├── tmax/openframe_ko_20260201_135130/
├── xsp_openframe/openframe_ko_20260201_092321/
├── msp_openframe/openframe_ko_20260131_131057/
├── vos3_openframe/openframe_ko_20260131_173439/
├── ofcobol/openframe_ko_20260201_085854/
└── ofasm/openframe_ko_20260201_030623/
```

### 3.3 전체 통계

| 항목 | 값 |
|------|-----|
| **총 학습 예제** | **190,777개** |
| **총 학습 시간** | **~44시간** |
| **학습된 어댑터** | **10개** (MVS 3개 + 제품 7개) |

---

## 4. 학습 스크립트

### 4.1 스크립트 목록

| 스크립트 | 설명 |
|----------|------|
| `train_openframe_qlora.py` | 핵심 QLoRA 학습 스크립트 |
| `generate_all_products_training_data.py` | 7개 제품별 다국어 학습 데이터 생성 |
| `generate_multilang_training_data.py` | MVS용 다국어 학습 데이터 생성 |
| `train_all_products_qlora.sh` | 7개 제품 순차 학습 실행 |
| `run_full_queue_v2.sh` | 전체 학습 큐 실행 (MVS 완료 후 제품별 학습) |
| `run_remaining_training.sh` | 남은 제품 학습 재실행 |
| `validate_all_adapters.py` | 어댑터 검증 및 추론 테스트 |
| `update_docker_compose.py` | docker-compose.yml 어댑터 설정 업데이트 |

### 4.2 주요 스크립트 사용법

#### train_openframe_qlora.py
```bash
# 기본 사용법
python train_openframe_qlora.py --data combined_ko.jsonl --gpu 6

# 전체 옵션
python train_openframe_qlora.py \
    --data training_data_products/tibero7_combined.jsonl \
    --output ./qlora_adapters/tibero7 \
    --gpu 5,6 \
    --epochs 3 \
    --batch_size 1 \
    --gradient_accumulation_steps 16 \
    --language ko \
    --eval_split 0.1
```

#### generate_all_products_training_data.py
```bash
# 모든 제품
python generate_all_products_training_data.py --product all

# 특정 제품
python generate_all_products_training_data.py --product tibero7 --languages ko,ja,en

# 옵션
#   --product: all, msp_openframe, vos3_openframe, tibero7, ofasm, ofcobol, xsp_openframe, tmax
#   --languages: ko,ja,en (쉼표 구분)
#   --output: 출력 디렉토리
```

#### validate_all_adapters.py
```bash
# 파일 검증만
python validate_all_adapters.py

# 추론 테스트 포함
python validate_all_adapters.py --test-inference
```

---

## 5. 학습 환경 설정

### 5.1 환경 변수
```bash
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export CUDA_VISIBLE_DEVICES=5,6
```

### 5.2 Python 환경
```bash
# 가상환경 활성화
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate
```

### 5.3 주요 의존성
- torch
- transformers
- peft
- trl
- bitsandbytes
- datasets
- PyMuPDF (fitz)

---

## 6. 성능 분석

### 6.1 우수한 성능 (eval_loss < 0.1)
- **Tmax 6.0**: 0.052 (최고 성능)
- **Tibero 7**: 0.065
- **MSP OpenFrame**: 0.074
- **XSP OpenFrame**: 0.077
- **VOS3 OpenFrame**: 0.098

### 6.2 데이터 부족으로 상대적 저성능
- **OpenFrame ASM**: 378개 예제 → eval_loss 0.431
- **OpenFrame COBOL**: 1,779개 예제 → eval_loss 0.276

### 6.3 개선 방안
1. OpenFrame ASM/COBOL의 학습 데이터 확보
2. Data Augmentation 적용
3. 더 많은 epoch 학습 검토

---

## 7. 어댑터 사용 방법

### 7.1 vLLM --lora-modules 설정

docker-compose.yml의 learning-llm 서비스에 추가:

```yaml
command: >
  --model Qwen/Qwen2.5-7B-Instruct
  --lora-modules
    openframe_mvs=/opt/qlora_adapters/openframe_mvs
    msp_openframe=/opt/qlora_adapters/msp_openframe
    vos3_openframe=/opt/qlora_adapters/vos3_openframe
    tibero7=/opt/qlora_adapters/tibero7
    ofasm=/opt/qlora_adapters/ofasm
    ofcobol=/opt/qlora_adapters/ofcobol
    xsp_openframe=/opt/qlora_adapters/xsp_openframe
    tmax=/opt/qlora_adapters/tmax
```

### 7.2 API 호출 예시

```python
import requests

response = requests.post(
    "http://localhost:12804/v1/chat/completions",
    json={
        "model": "tibero7",  # 어댑터 이름
        "messages": [
            {"role": "user", "content": "Tibero 7의 주요 기능을 설명해 주세요."}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
)
```

---

## 8. 파일 구조

```
test_0130/
├── TRAINING_REPORT.md              # 본 문서
├── train_openframe_qlora.py        # 핵심 학습 스크립트
├── generate_all_products_training_data.py  # 데이터 생성
├── generate_multilang_training_data.py     # MVS 데이터 생성
├── train_all_products_qlora.sh     # 제품별 학습 실행
├── run_full_queue_v2.sh            # 전체 학습 큐
├── run_remaining_training.sh       # 남은 학습 실행
├── validate_all_adapters.py        # 어댑터 검증
├── update_docker_compose.py        # docker 설정 업데이트
├── test_adapter.py                 # 어댑터 테스트
├── test_adapter_v2.py              # 어댑터 테스트 v2
│
├── openframe_qlora_adapter/        # MVS 다국어 어댑터
│   ├── openframe_ko_*/
│   ├── openframe_ja_*/
│   └── openframe_en_*/
│
├── qlora_adapters/                 # 7개 제품별 어댑터
│   ├── msp_openframe/
│   ├── vos3_openframe/
│   ├── tibero7/
│   ├── ofasm/
│   ├── ofcobol/
│   ├── xsp_openframe/
│   └── tmax/
│
├── training_data_multilang/        # MVS 다국어 학습 데이터
│   ├── combined_ko.jsonl
│   ├── combined_ja.jsonl
│   └── combined_en.jsonl
│
├── training_data_products/         # 7개 제품 학습 데이터
│   ├── {product}_ko.jsonl
│   ├── {product}_ja.jsonl
│   ├── {product}_en.jsonl
│   └── {product}_combined.jsonl
│
├── Tmax_6.0_v2.1.1_JP/            # 원본 PDF
├── Tibero 7 FixSet01 Manual Set v2.1.1_jp/
└── XSP_Openframe 7.3_v3.2.1_JP/
```

---

## 9. 로그 파일

| 로그 파일 | 내용 |
|-----------|------|
| `nohup_training.out` | 전체 학습 출력 |
| `training_tmax.log` | Tmax 학습 로그 |
| `training_xsp_openframe.log` | XSP OpenFrame 학습 로그 |
| `training_ofcobol.log` | OFCOBOL 학습 로그 |
| `training_remaining_products.log` | 남은 제품 학습 로그 |

---

## 10. 참고 사항

- 학습 시 `HF_HUB_OFFLINE=1` 설정으로 오프라인 모드 사용 (로컬 캐시된 모델)
- GPU 메모리 최적화를 위해 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 설정
- 학습 데이터는 PDF에서 자동 추출되어 다국어로 생성됨
- 각 어댑터는 독립적으로 로드/언로드 가능
