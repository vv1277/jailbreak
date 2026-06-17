import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
LORA_PATH = "./llama8b-lora"

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# 1. tokenizer
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# 2. base model
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float32,
)
base_model.to(DEVICE)

# 3. LoRA adapter load
model = PeftModel.from_pretrained(base_model, LORA_PATH)
model.eval()

# 4. 대화 기록
messages = []

print("대화를 시작합니다. 종료하려면 /exit 입력")

while True:
    user_input = input("\nYou: ").strip()
    if user_input.lower() == "/exit":
        break

    messages.append({"role": "user", "content": user_input})

    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt"
    ).to(DEVICE)

    attention_mask = torch.ones_like(inputs).to(DEVICE)

    # 6. 생성
    with torch.no_grad():
        outputs = model.generate(
            inputs,
            attention_mask=attention_mask,
            max_new_tokens=512,
            min_new_tokens=256,
            do_sample=True,
            temperature=0.9,
            top_p=0.95,
            repetition_penalty=1.1,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id
        )

    input_length = inputs.shape[1]
    answer = tokenizer.decode(
        outputs[0][input_length:],
        skip_special_tokens=True
    ).strip()

    print(f"\nAssistant: {answer}")

    messages.append({"role": "assistant", "content": answer})

# python3 chat_lora_llama8b.py