import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OI_PYTHON = ROOT / ".venv-oi" / "Scripts" / "python.exe"

# Open Interpreter 전용 venv로 재실행
if OI_PYTHON.exists() and not Path(sys.executable).samefile(OI_PYTHON):
    completed = subprocess.run(
        [str(OI_PYTHON), str(Path(__file__).resolve())]
    )
    raise SystemExit(completed.returncode)

from interpreter import interpreter

# -----------------------------
# Open Interpreter 설정
# -----------------------------
interpreter.offline = True

interpreter.llm.model = "ollama/gemma4"
interpreter.llm.api_base = "http://127.0.0.1:11434"

interpreter.llm.max_tokens = 1000
interpreter.llm.context_window = 4000

# 핵심: 자동 실행 잠금
interpreter.auto_run = False


# -----------------------------
# 위험도 분석
# -----------------------------
def classify_code(code: str) -> str:
    code_lower = code.lower()

    if any(x in code_lower for x in ["format", "diskpart", "shutdown", "reg delete"]):
        return "BLOCK"

    if any(x in code_lower for x in ["unlink(", "remove(", "rmtree("]):
        return "HIGH_RISK"

    if any(x in code_lower for x in ["open(", "write(", "mkdir("]):
        return "CONFIRM"

    return "SAFE"


# -----------------------------
# 메인 로직
# -----------------------------
def main():
    target = ROOT / "oi_ollama_test.txt"

    if target.exists():
        target.unlink()

    prompt = (
        "Write a python code block that creates a file named 'oi_ollama_test.txt' "
        "containing the text 'gemma-oi-success'."
    )

    print("\n=== 사용자 요청 ===\n")
    print(prompt)
    print("\n=== Open Interpreter 호출 (스트리밍 및 제어권 가로채기) ===\n")

    try:
        generated_code = ""
        code_block_detected = False

        # 🔥 중요: 내부 메시지 상태를 완전히 초기화하여 KeyError를 방지합니다.
        interpreter.messages = []
        
        # messages 리스트 대신 문자열 prompt를 직접 전달합니다.
        for chunk in interpreter.chat(prompt, display=False, stream=True):
            
            # AI가 말하는 텍스트 내용 실시간 출력
            if chunk.get("type") == "message" and "content" in chunk:
                print(chunk["content"], end="", flush=True)

            # AI가 코드를 작성 중이거나 작성을 완료했을 때
            if chunk.get("type") == "code" and chunk.get("format") == "python":
                if "content" in chunk:
                    # 조각조각 들어오는 소스코드를 합칩니다.
                    generated_code += chunk["content"]
                    code_block_detected = True

        print("\n\n========================\n")
        
        if not code_block_detected or not generated_code.strip():
            print("생성된 코드가 없습니다.")
            return

        print("=== 생성 코드 ===\n")
        print(generated_code.strip())

        # 위험도 분류
        risk = classify_code(generated_code)
        print(f"\n=== 위험도 ===\n{risk}")

        if risk == "BLOCK":
            print("\n🚨 [보안 노티] 위험한 명령어가 감지되어 차단되었습니다.")
            return

        # 사용자 승인 받기
        answer = input("\n위 코드를 내 PC에서 실행하시겠습니까? (y/n): ")

        if answer.lower() != "y":
            print("\n❌ 사용자가 실행을 거절했습니다.")
            return

        print("\n===== 실행 시작 =====")
        
        # Open Interpreter의 자체 샌드박스 커널을 이용해 실행합니다.
        execution_result = interpreter.computer.run("python", generated_code)
        
        print("\n===== 실행 종료 =====")
        
        # 실행 결과 출력 파싱 안정화
        if isinstance(execution_result, list):
            for res in execution_result:
                if isinstance(res, dict) and res.get("type") == "console" and "content" in res:
                    print(f"출력 결과: {res['content'].strip()}")
        elif isinstance(execution_result, str):
            print(f"출력 결과: {execution_result.strip()}")

        # 최종 확인
        print("\n=== 결과 확인 ===")
        print("파일 존재:", target.exists())``
        if target.exists():
            print("파일 내용:", target.read_text(encoding="utf-8"))

    except Exception as e:
        import traceback
        print("\n=== 오류 발생 ===\n")
        traceback.print_exc()
        
if __name__ == "__main__":
    main()
    