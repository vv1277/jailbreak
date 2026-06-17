import json
import gc
from datetime import datetime
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

# ==============================
# model_outputs.jsonl 파일이 만들어지는 구조
# ==============================

BASE_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# 이 파일이 있는 test 폴더
TEST_DIR = Path(__file__).parent.resolve()

# test 폴더의 부모: jailbreak-heck-final
PROJECT_DIR = TEST_DIR.parent

# Desktop 같은 상위 폴더: jailbreak, jailbreak-heck-final, jailbreak-merge, jailbreak-answer가 같이 있는 위치
ROOT_DIR = PROJECT_DIR.parent

# 결과 저장 파일: 항상 test/model_outputs.jsonl에 저장
OUTPUT_PATH = TEST_DIR / "model_outputs.jsonl"


# ==============================
# 네 chat_lora_llama8b.py와 같은 생성 설정
# ==============================

MAX_NEW_TOKENS = 512
MIN_NEW_TOKENS = 256
DO_SAMPLE = True
TEMPERATURE = 0.9
TOP_P = 0.95
REPETITION_PENALTY = 1.1


# ==============================
# 4개 모델 경로
# ==============================
# 현재 코드 위치:
# jailbreak-heck-final/test/make_model_outputs.py
#
# 따라서:
# PROJECT_DIR / "LoRa/llama8b-lora"
#   -> jailbreak-heck-final/LoRa/llama8b-lora
#
# ROOT_DIR / "jailbreak/LoRa/llama8b-lora"
#   -> jailbreak/LoRa/llama8b-lora

MODEL_CONFIGS = [
    {
        "name": "jailbreak_lora",
        "lora_path": ROOT_DIR / "jailbreak" / "LoRa" / "llama8b-lora",
    },
    {
        "name": "jailbreak_heck_final_lora",
        "lora_path": ROOT_DIR / "jailbreak-heck-final" / "LoRa" / "llama8b-lora",
    },
    {
        "name": "jailbreak_merge_lora",
        "lora_path": ROOT_DIR / "jailbreak-merge" / "LoRa" / "llama8b-lora",
    },
    {
        "name": "jailbreak_answer_lora",
        "lora_path": ROOT_DIR / "jailbreak-answer" / "LoRa" / "llama8b-lora",
    },
]


def save_to_jsonl(row: dict):
    with OUTPUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_lora_model(lora_path: Path):
    print(f"[+] Loading tokenizer: {BASE_MODEL}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[+] Loading base model: {BASE_MODEL}")

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,
    )

    base_model.to(DEVICE)

    print(f"[+] Loading LoRA adapter: {lora_path}")

    model = PeftModel.from_pretrained(
        base_model,
        str(lora_path),
    )

    model.to(DEVICE)
    model.eval()

    return tokenizer, model


def generate_answer(tokenizer, model, user_prompt: str) -> str:
    # 네 chat_lora_llama8b.py와 같은 방식
    messages = [
        {
            "role": "user",
            "content": user_prompt,
        }
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt"
    ).to(DEVICE)

    attention_mask = torch.ones_like(inputs).to(DEVICE)

    with torch.no_grad():
        outputs = model.generate(
            inputs,
            attention_mask=attention_mask,
            max_new_tokens=MAX_NEW_TOKENS,
            min_new_tokens=MIN_NEW_TOKENS,
            do_sample=DO_SAMPLE,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repetition_penalty=REPETITION_PENALTY,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id
        )

    input_length = inputs.shape[1]

    answer = tokenizer.decode(
        outputs[0][input_length:],
        skip_special_tokens=True
    ).strip()

    return answer


def cleanup(tokenizer=None, model=None):
    if model is not None:
        del model

    if tokenizer is not None:
        del tokenizer

    gc.collect()

    if DEVICE == "mps":
        torch.mps.empty_cache()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main():
    print("=== 4 Model Output Collector ===")
    print(f"Device: {DEVICE}")
    print(f"Test dir: {TEST_DIR}")
    print(f"Project dir: {PROJECT_DIR}")
    print(f"Root dir: {ROOT_DIR}")
    print(f"Output file: {OUTPUT_PATH}")

    print("\n등록된 모델 경로 확인:")
    for config in MODEL_CONFIGS:
        print(f"- {config['name']}: {config['lora_path']}")

    case_id = input("\ncase_id를 입력해줘. 예: pair_001\n> ").strip()

    if not case_id:
        print("[!] case_id가 비어 있어서 종료함.")
        return

    print("\n모델에게 넣을 질문을 입력해줘.")
    print("여러 줄 입력 가능. 입력을 끝내려면 빈 줄에서 Enter.")

    lines = []

    while True:
        line = input()
        if line == "":
            break
        lines.append(line)

    user_prompt = "\n".join(lines).strip()

    if not user_prompt:
        print("[!] 질문이 비어 있어서 종료함.")
        return

    print("\n=== Generation Start ===")

    for config in MODEL_CONFIGS:
        model_name = config["name"]
        lora_path = config["lora_path"].resolve()

        print("\n" + "=" * 80)
        print(f"[+] Model: {model_name}")
        print(f"[+] LoRA path: {lora_path}")
        print("=" * 80)

        if not lora_path.exists():
            print(f"[!] LoRA 경로 없음. 건너뜀: {model_name}")
            print(f"    확인 필요 경로: {lora_path}")

            row = {
                "case_id": case_id,
                "model": model_name,
                "prompt": user_prompt,
                "answer": "",
                "error": f"LoRA path not found: {lora_path}",
                "timestamp": datetime.now().isoformat(timespec="seconds")
            }
            save_to_jsonl(row)
            continue

        tokenizer = None
        model = None

        try:
            tokenizer, model = load_lora_model(lora_path)

            answer = generate_answer(
                tokenizer=tokenizer,
                model=model,
                user_prompt=user_prompt
            )

            row = {
                "case_id": case_id,
                "model": model_name,
                "prompt": user_prompt,
                "answer": answer,
                "timestamp": datetime.now().isoformat(timespec="seconds")
            }

            save_to_jsonl(row)

            print(f"\n[+] Saved answer from {model_name}")
            print("-" * 80)
            print(answer)
            print("-" * 80)

        except Exception as e:
            row = {
                "case_id": case_id,
                "model": model_name,
                "prompt": user_prompt,
                "answer": "",
                "error": str(e),
                "timestamp": datetime.now().isoformat(timespec="seconds")
            }

            save_to_jsonl(row)

            print(f"\n[!] Error from {model_name}: {e}")

        finally:
            cleanup(tokenizer, model)

    print("\n=== Done ===")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()