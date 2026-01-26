#!/bin/bash
#
# QLoRA 학습 패키지 생성 스크립트
# 사용법: ./package_training.sh
#
# 이 스크립트는 학습에 필요한 모든 파일을 tgz로 패키징합니다.
# 생성된 패키지를 sdgx 서버로 전송 후 압축 해제하여 실행할 수 있습니다.
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="/opt/kms"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="qlora_training_${TIMESTAMP}"
PACKAGE_DIR="/tmp/${PACKAGE_NAME}"
OUTPUT_FILE="${PROJECT_ROOT}/data/training/${PACKAGE_NAME}.tgz"

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}  QLoRA 학습 패키지 생성${NC}"
echo -e "${BLUE}=====================================${NC}"
echo ""

# 1. 학습 데이터 확인 (기존 JSON 파일 또는 API 호출)
echo -e "${YELLOW}[1/5] 학습 데이터 확인 중...${NC}"

cd "${PROJECT_ROOT}"

# Python으로 학습 대상 데이터 조회
TRAINING_INFO=$(/opt/kms/venv/bin/python << 'PYEOF'
import os
import sys
import json

# 환경변수 설정
os.chdir('/opt/kms')
sys.path.insert(0, '/opt/kms')

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv('/opt/kms/.env')

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def get_training_data():
    # 데이터베이스 연결
    db_url = os.getenv('DATABASE_URL', '')
    if not db_url:
        postgres_host = os.getenv('POSTGRES_HOST', 'localhost')
        postgres_port = os.getenv('POSTGRES_PORT', '5432')
        postgres_db = os.getenv('POSTGRES_DB', 'kms')
        postgres_user = os.getenv('POSTGRES_USER', 'kms')
        postgres_password = os.getenv('POSTGRES_PASSWORD', '')
        db_url = f"postgresql+asyncpg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 학습 가능한 데이터 조회
        result = await session.execute(text('''
            SELECT id, question, answer, feedback_score, thumbs_up_count, created_at
            FROM verified_knowledge
            WHERE feedback_score >= 0.8
            AND thumbs_up_count >= 1
            AND (training_status IS NULL OR training_status = 'pending')
            ORDER BY feedback_score DESC, thumbs_up_count DESC
            LIMIT 100
        '''))
        rows = result.fetchall()

        data = []
        for row in rows:
            data.append({
                "id": str(row[0]),
                "instruction": row[1] if row[1] else "",
                "input": "",
                "output": row[2] if row[2] else "",
                "metadata": {
                    "feedback_score": float(row[3]) if row[3] else 0,
                    "thumbs_up_count": int(row[4]) if row[4] else 0,
                }
            })

        print(json.dumps({
            "count": len(data),
            "data": data
        }))

    await engine.dispose()

try:
    asyncio.run(get_training_data())
except Exception as e:
    # 에러 발생 시 기존 학습 데이터 파일 사용
    import glob
    json_files = sorted(glob.glob('/opt/kms/data/training/manual_*.json'), reverse=True)
    if json_files:
        with open(json_files[0], 'r') as f:
            existing = json.load(f)
            print(json.dumps({
                "count": len(existing.get('training_data', [])),
                "data": existing.get('training_data', []),
                "source": "existing_file"
            }))
    else:
        print(json.dumps({"count": 0, "data": [], "error": str(e)}))
PYEOF
)

TRAINING_COUNT=$(echo "$TRAINING_INFO" | /opt/kms/venv/bin/python -c "import sys,json; d=json.load(sys.stdin); print(d.get('count', 0))")

if [ "$TRAINING_COUNT" -eq 0 ]; then
    echo -e "${RED}학습 대상 데이터가 없습니다.${NC}"
    echo "조건: feedback_score >= 0.8, thumbs_up_count >= 1"
    exit 1
fi

echo -e "${GREEN}  → 학습 대상: ${TRAINING_COUNT}개 샘플${NC}"

# 2. 패키지 디렉토리 생성
echo -e "${YELLOW}[2/5] 패키지 디렉토리 생성 중...${NC}"
rm -rf "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}/scripts"
mkdir -p "${PACKAGE_DIR}/data"
mkdir -p "${PACKAGE_DIR}/models"
mkdir -p "${PACKAGE_DIR}/logs"

# 3. 필요한 파일 복사
echo -e "${YELLOW}[3/5] 필요한 파일 복사 중...${NC}"

# 학습 스크립트 복사
cp "${SCRIPT_DIR}/qlora_trainer.py" "${PACKAGE_DIR}/scripts/"

# 학습 데이터 저장
echo "$TRAINING_INFO" | /opt/kms/venv/bin/python -c "
import sys, json
data = json.load(sys.stdin)
with open('${PACKAGE_DIR}/data/training_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
"

echo -e "${GREEN}  → qlora_trainer.py 복사 완료${NC}"
echo -e "${GREEN}  → training_data.json 생성 완료 (${TRAINING_COUNT}개 샘플)${NC}"

# 4. 실행 스크립트 생성
echo -e "${YELLOW}[4/5] 실행 스크립트 생성 중...${NC}"

cat > "${PACKAGE_DIR}/run_training.sh" << 'RUNSCRIPT'
#!/bin/bash
#
# QLoRA 학습 실행 스크립트 (GPU 7 전용)
# 사용법: ./run_training.sh
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BATCH_ID="gpu7_${TIMESTAMP}"
LOG_FILE="${SCRIPT_DIR}/logs/training_${BATCH_ID}.log"

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}  QLoRA 학습 실행 (GPU 7)${NC}"
echo -e "${BLUE}=====================================${NC}"
echo ""

mkdir -p "${SCRIPT_DIR}/logs"
mkdir -p "${SCRIPT_DIR}/models"

# GPU 7 확인
echo -e "${YELLOW}[1/4] GPU 7 상태 확인...${NC}"
if ! nvidia-smi -i 7 &>/dev/null; then
    echo -e "${RED}GPU 7을 찾을 수 없습니다.${NC}"
    exit 1
fi

GPU_MEM_FREE=$(nvidia-smi -i 7 --query-gpu=memory.free --format=csv,noheader,nounits)
echo -e "${GREEN}  → GPU 7 여유 메모리: ${GPU_MEM_FREE} MiB${NC}"

if [ "$GPU_MEM_FREE" -lt 8000 ]; then
    echo -e "${RED}GPU 7 메모리 부족 (최소 8GB 필요)${NC}"
    exit 1
fi

# Python 환경 확인
echo -e "${YELLOW}[2/4] Python 환경 확인...${NC}"
PYTHON_PATH=""
if [ -f "/opt/kms/venv/bin/python" ]; then
    PYTHON_PATH="/opt/kms/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_PATH="python3"
else
    echo -e "${RED}Python을 찾을 수 없습니다.${NC}"
    exit 1
fi
echo -e "${GREEN}  → Python: ${PYTHON_PATH}${NC}"

# 필수 패키지 확인
echo -e "${YELLOW}[3/4] 필수 패키지 확인...${NC}"
$PYTHON_PATH -c "import torch, transformers, peft, trl, bitsandbytes" 2>/dev/null || {
    echo -e "${RED}필수 패키지가 설치되어 있지 않습니다.${NC}"
    echo "다음 패키지가 필요합니다: torch, transformers, peft, trl, bitsandbytes"
    exit 1
}
echo -e "${GREEN}  → 모든 패키지 확인 완료${NC}"

# 학습 데이터 확인
TRAINING_DATA="${SCRIPT_DIR}/data/training_data.json"
if [ ! -f "$TRAINING_DATA" ]; then
    echo -e "${RED}학습 데이터 파일을 찾을 수 없습니다: ${TRAINING_DATA}${NC}"
    exit 1
fi

SAMPLE_COUNT=$($PYTHON_PATH -c "import json; d=json.load(open('${TRAINING_DATA}')); print(d['count'])")
echo -e "${GREEN}  → 학습 샘플: ${SAMPLE_COUNT}개${NC}"

# 학습 실행
echo -e "${YELLOW}[4/4] 학습 시작...${NC}"
echo -e "${BLUE}  Batch ID: ${BATCH_ID}${NC}"
echo -e "${BLUE}  Log: ${LOG_FILE}${NC}"
echo ""

OUTPUT_DIR="${SCRIPT_DIR}/models/qlora_${BATCH_ID}"

# GPU 7에서 학습 실행
CUDA_VISIBLE_DEVICES=7 $PYTHON_PATH << TRAINPY
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from trl import SFTTrainer, SFTConfig

# 로깅
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('${LOG_FILE}'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 설정
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
LORA_R = 64
LORA_ALPHA = 16
LORA_DROPOUT = 0.1
LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
BATCH_SIZE = 1
GRADIENT_ACCUMULATION_STEPS = 4
MAX_SEQ_LENGTH = 2048

def format_instruction(example):
    instruction = example.get("instruction", "")
    input_text = example.get("input", "")
    output = example.get("output", "")
    user_content = f"{instruction}\n{input_text}".strip() if input_text else instruction
    return f"""<|im_start|>system
You are a helpful KMS assistant.<|im_end|>
<|im_start|>user
{user_content}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""

def main():
    logger.info("=" * 50)
    logger.info("QLoRA Training Started (GPU 7)")
    logger.info("=" * 50)

    # 데이터 로드
    with open('${TRAINING_DATA}', 'r', encoding='utf-8') as f:
        info = json.load(f)

    training_data = info['data']
    logger.info(f"Loaded {len(training_data)} samples")

    if not training_data:
        logger.error("No data")
        return

    # 데이터셋
    dataset = Dataset.from_list([{"text": format_instruction(ex)} for ex in training_data])

    # 모델 로드
    logger.info(f"Loading: {BASE_MODEL}")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=True,
        torch_dtype=torch.float16,
        use_cache=False,
    )

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)

    # LoRA
    lora_config = LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
        bias="none", task_type=TaskType.CAUSAL_LM,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    output_dir = Path("${OUTPUT_DIR}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # SFT
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_ratio=0.03,
        weight_decay=0.001,
        logging_steps=10,
        save_steps=100,
        save_total_limit=3,
        fp16=True,
        optim="paged_adamw_32bit",
        lr_scheduler_type="cosine",
        report_to="none",
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,
        dataset_text_field="text",
    )

    logger.info("Starting training...")
    trainer = SFTTrainer(model=model, args=sft_config, train_dataset=dataset, tokenizer=tokenizer)
    result = trainer.train()

    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    logger.info(f"Done! Loss: {result.training_loss:.4f}")
    logger.info(f"Saved: {output_dir}")

    with open(output_dir / "results.json", 'w') as f:
        json.dump({"batch_id": "${BATCH_ID}", "loss": result.training_loss, "samples": len(training_data)}, f, indent=2)

if __name__ == "__main__":
    main()
TRAINPY

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  학습 완료!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo -e "로그: ${LOG_FILE}"
echo -e "어댑터: ${OUTPUT_DIR}/"
RUNSCRIPT

chmod +x "${PACKAGE_DIR}/run_training.sh"
echo -e "${GREEN}  → run_training.sh 생성 완료${NC}"

# README 생성
cat > "${PACKAGE_DIR}/README.md" << 'README'
# QLoRA 학습 패키지

## 사용 방법

### 1. sdgx 서버로 전송
```bash
scp qlora_training_*.tgz ofuser@sdgx:/tmp/
```

### 2. 압축 해제
```bash
cd /tmp && tar -xzf qlora_training_*.tgz && cd qlora_training_*
```

### 3. 학습 실행 (GPU 7)
```bash
./run_training.sh
```

## 필수 패키지
torch, transformers, peft, trl, bitsandbytes, datasets
README

echo -e "${GREEN}  → README.md 생성 완료${NC}"

# 5. tgz 압축
echo -e "${YELLOW}[5/5] 패키지 압축 중...${NC}"
mkdir -p "$(dirname "${OUTPUT_FILE}")"
cd /tmp
tar -czf "${OUTPUT_FILE}" "${PACKAGE_NAME}"
rm -rf "${PACKAGE_DIR}"

FILESIZE=$(du -h "${OUTPUT_FILE}" | cut -f1)

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  패키지 생성 완료!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo -e "패키지: ${BLUE}${OUTPUT_FILE}${NC}"
echo -e "크기: ${BLUE}${FILESIZE}${NC}"
echo -e "샘플: ${BLUE}${TRAINING_COUNT}개${NC}"
echo ""
echo -e "${YELLOW}다음 단계:${NC}"
echo -e "1. scp ${OUTPUT_FILE} ofuser@sdgx:/tmp/"
echo -e "2. ssh ofuser@sdgx"
echo -e "3. cd /tmp && tar -xzf ${PACKAGE_NAME}.tgz && cd ${PACKAGE_NAME}"
echo -e "4. ./run_training.sh"
