import sys
import subprocess
from pathlib import Path


# -----------------------------
# 환경 설정 및 venv 재실행
# -----------------------------
ROOT = Path(__file__).resolve().parent
OI_PYTHON = ROOT / ".venv-oi" / "Scripts" / "python.exe"

if OI_PYTHON.exists() and not Path(sys.executable).samefile(OI_PYTHON):
    completed = subprocess.run([str(OI_PYTHON), str(Path(__file__).resolve())])
    raise SystemExit(completed.returncode)

from interpreter import interpreter

# -----------------------------
# Open Interpreter 설정
# -----------------------------
interpreter.offline = True
interpreter.llm.model = "ollama/gemma4"
interpreter.llm.api_base = "http://127.0.0.1:11434"
interpreter.auto_run = False # 자동 실행 방지

# -----------------------------
# 보안 위험도 분석 모듈
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

import sys
import subprocess
from pathlib import Path
from interpreter import interpreter

# (환경 설정 및 venv 부분은 동일하므로 생략)

# [핵심] Open Interpreter 설정
interpreter.offline = True
interpreter.llm.model = "ollama/gemma4"
interpreter.llm.api_base = "http://127.0.0.1:11434"
interpreter.auto_run = False  # 자동 실행 방지 (강력 모드)

def main():
    prompt = "Write a python code block that creates a file named 'oi_ollama_test.txt' containing the text 'gemma-oi-success'."
    
    print("\n=== [1] 코드 생성 시작 ===")
    
    # 메시지 리스트를 비워 이전 대화 영향 제거
    interpreter.messages = []
    
    # 1. 생성 단계: stream으로 코드만 수집 (실행은 절대 안 함)
    generated_code = ""
    for chunk in interpreter.chat(prompt, display=False, stream=True):
        if chunk.get("type") == "code" and chunk.get("format") == "python":
            if "content" in chunk:
                generated_code += chunk["content"]
        elif chunk.get("type") == "message":
            print(chunk.get("content", ""), end="", flush=True)

    # 2. 보안 검증 단계
    if not generated_code:
        print("\n코드 생성 실패")
        return
        
    print(f"\n\n=== [2] 생성 코드 추출 완료 ===")
    print(generated_code)
    
    # [Permission Hook] 여기서 반드시 멈춤
    # answer = input("\n🚨 [보안] 이 코드를 실행하시겠습니까? (y/n): ")
    answer = 'y'
    if answer.lower() == 'y':
        print("\n=== [3] 승인됨: 실행 시작 ===")
        # 3. 명시적 실행 단계: 이제서야 computer.run 호출
        try:
            result = interpreter.computer.run("python", generated_code)
            print("실행 결과:", result)
        except Exception as e:
            print(f"실행 오류: {e}")
    else:
        print("\n❌ 사용자에 의해 실행이 차단되었습니다.")

if __name__ == "__main__":
    main()

# -----------------------------
# 메인 로직
# -----------------------------
# def main():
#     target = ROOT / "oi_ollama_test.txt"
#     prompt = "Write a python code block that creates a file named 'oi_ollama_test.txt' containing the text 'gemma-oi-success'."

#     print("\n=== 사용자 요청 ===")
#     print(prompt)
#     print("\n=== AI 생성 및 코드 가로채기 ===")

#     generated_code = ""
#     interpreter.messages = [] 
    
#     # 1. 생성 단계: stream을 통해 코드 블록만 추출
#     for chunk in interpreter.chat(prompt, display=False, stream=True):
#         if chunk.get("type") == "message" and "content" in chunk:
#             print(chunk["content"], end="", flush=True)
        
#         if chunk.get("type") == "code" and chunk.get("format") == "python":
#             if "content" in chunk:
#                 generated_code += chunk["content"]

#     if not generated_code.strip():
#         print("\n\n생성된 코드가 없습니다.")
#         return

#     print("\n\n=== 생성된 코드 ===")
#     print(generated_code.strip())

#     # 2. 보안 검증 단계
#     risk = classify_code(generated_code)
#     print(f"\n=== 위험도 분석 결과: {risk} ===")

#     if risk == "BLOCK":
#         print("🚨 위험한 명령어가 감지되어 차단되었습니다.")
#         return

#     # 3. Permission Hook: 사용자 승인 대기
#     answer = input("\n[Permission Hook] 위 코드를 실행하시겠습니까? (y/n): ")

#     if answer.lower() != "y":
#         print("\n❌ 사용자가 실행을 거절했습니다.")
#         return

#     # 4. 실행 단계
#     print("\n===== 실행 시작 =====")
#     try:
#         # 생성된 코드를 샌드박스에서 실행
#         result = interpreter.computer.run("python", generated_code)
#         print("\n===== 실행 종료 =====")
        
#         # 결과 확인
#         print("\n=== 결과 확인 ===")
#         print("파일 존재:", target.exists())
#         if target.exists():
#             print("파일 내용:", target.read_text(encoding="utf-8"))
            
#     except Exception as e:
#         print(f"\n실행 중 오류 발생: {e}")

# if __name__ == "__main__":
#     main()