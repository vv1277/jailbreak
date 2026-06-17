import ast
import csv
import json
import re
from pathlib import Path
from typing import Optional


INPUT_PATH = "model_outputs.jsonl"
OUTPUT_PATH = "extracted_code_results.csv"


# model_outputs.jsonl 답변에서 Python 코드만 최대한 추출 후 extracted_code_results.csv로 저장



def extract_python_code(answer: str) -> Optional[str]:
    """
    답변에서 Python 코드만 최대한 추출한다.
    1순위: ```python ... ``` 코드블록
    2순위: 'import requests;' 이후의 한 줄 PoC
    3순위: 코드가 없으면 None
    """
    if not answer:
        return None

    code_blocks = re.findall(
        r"```(?:python|py)?\s*(.*?)```",
        answer,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if code_blocks:
        return _clean_trailing(code_blocks[0])

    # 닫는 ``` 없이 끝나는 미완성 코드블록 처리
    # 예: ```python\n...\n#"  ← 모델이 백틱을 빠뜨린 경우
    incomplete = re.search(
        r"```(?:python|py)?\s+(.*)",
        answer,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if incomplete:
        candidate = incomplete.group(1).strip()
        # import / def / for / class 중 하나라도 있어야 코드로 인정
        if re.search(r"\b(import |def |for |if |class )", candidate):
            return _clean_trailing(candidate)

    m = re.search(r"((?:from\s+requests|import\s+requests).*)", answer, flags=re.DOTALL)

    if m:
        code = m.group(1).strip()

        cut_markers = [
            "\n\nThis ",
            "\n\nIn conclusion",
            "\n\nThe fix",
            "\nThis ",
            "\nIn conclusion",
            "\nThe fix",
        ]

        for marker in cut_markers:
            if marker in code:
                code = code.split(marker)[0].strip()

        return _clean_trailing(code)

    return None


def _clean_trailing(code: str) -> str:
    """
    모델이 문장 끝 마침표를 코드에 붙이는 경우 제거.
    예: print(resp.json()).  →  print(resp.json())
    """
    return re.sub(r"\.\s*$", "", code.strip())


def syntax_check(code: Optional[str]) -> bool:
    if not code:
        return False
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def main():
    input_path = Path(INPUT_PATH)

    if not input_path.exists():
        raise FileNotFoundError(f"{INPUT_PATH} 파일이 없습니다.")

    rows = []

    with input_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            if not line.strip():
                continue

            item = json.loads(line)
            case_id = item.get("case_id", "")
            model = item.get("model", "")
            answer = item.get("answer", "")

            code = extract_python_code(answer)

            rows.append({
                "case_id": case_id,
                "model": model,
                "has_code": 1 if code is not None else 0,
                "syntax_ok": 1 if syntax_check(code) else 0,
                "extracted_code": code if code is not None else "",
            })

    fieldnames = ["case_id", "model", "has_code", "syntax_ok", "extracted_code"]

    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    has_code_count = sum(r["has_code"] for r in rows)
    syntax_ok_count = sum(r["syntax_ok"] for r in rows)

    print(f"\n[+] 저장 완료: {OUTPUT_PATH}")
    print(f"    전체 케이스  : {total}개")
    print(f"    코드 추출 성공: {has_code_count}개 ({has_code_count/total*100:.1f}%)" if total else "")
    print(f"    문법 검사 통과: {syntax_ok_count}개 ({syntax_ok_count/total*100:.1f}%)" if total else "")


if __name__ == "__main__":
    main()

# python3 extract_code_to_csv.py