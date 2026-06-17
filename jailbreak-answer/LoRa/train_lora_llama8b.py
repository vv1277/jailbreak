import torch
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
from peft import LoraConfig
from trl import SFTTrainer

MODEL_NAME = "meta-llama/Meta-Llama-3.1-8B-Instruct"
DATA_PATH = "train.jsonl"
OUTPUT_DIR = "./llama8b-lora"

# Mac이면 mps, 아니면 cpu
if torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"

print(f"Using device: {DEVICE}")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# MPS에서는 float32가 가장 안전
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float32,
)
model.to(DEVICE)
model.config.use_cache = False

# JSONL 불러오기
dataset = load_dataset("json", data_files=DATA_PATH, split="train")

# instruction/output -> text 변환
def format_example(example):
    prompt = example["instruction"].strip()
    answer = example["output"].strip()

    text = (
        f"<|begin_of_text|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n"
        f"{prompt}"
        f"<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        f"{answer}"
        f"<|eot_id|>"
    )
    return {"text": text}

dataset = dataset.map(format_example, remove_columns=dataset.column_names)

peft_config = LoraConfig(
    r=4,
    lora_alpha=32,
    lora_dropout=0.1,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
)

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=4e-4,
    num_train_epochs=4,
    logging_steps=10,
    save_steps=100,
    save_total_limit=2,
    report_to="none",
    remove_unused_columns=False,
    optim="adamw_torch",
    bf16=False,
    fp16=False,
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    processing_class=tokenizer,
    peft_config=peft_config,
)

trainer.train()
trainer.model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

#python3 train_lora_llama8b.