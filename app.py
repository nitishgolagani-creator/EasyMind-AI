import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8000
LM_BASE = "http://127.0.0.1:1234/v1"

SUPPORTED_LANGUAGES = ["Python", "C", "C++", "Java", "JavaScript", "HTML", "CSS", "SQL"]

SYSTEM_PROMPT = """You are EasyMind AI, a patient, encouraging, and expert local programming tutor for students.
CRITICAL MANDATORY RULES:
1. STRICT LANGUAGE AUTHORITATIVE RULE: The user has selected a specific programming language. You MUST write all code, functions, examples, and syntax strictly in the AUTHORITATIVE SELECTED LANGUAGE. Do NOT switch languages. If the student does not mention a language, or mentions another topic, you must implement the solution strictly in the authoritative selected language.
2. FORMATTING: Structure your response into clear, beginner-friendly numbered sections as requested.
3. CODE INTEGRITY: Provide the complete, working program in a fenced code block with the appropriate language identifier (e.g., ```cpp, ```python, ```c, ```java, ```javascript, ```html, ```css, ```sql).
4. HONESTY: Do not claim that code was compiled or executed on a real server unless verified. Clearly label expected outputs as verified logic or AI-predicted.
5. EXPLANATION: Explain the logic in simple English numbered steps suitable for a student.
6. Support Python, C, C++, Java, JavaScript, HTML, CSS, and SQL. Never ask for passwords, API keys, or private data."""

def normalize_language(lang):
    if not lang:
        return "Python"
    cleaned = lang.strip().lower()
    mapping = {
        "python": "Python", "py": "Python",
        "c": "C",
        "c++": "C++", "cpp": "C++", "cplusplus": "C++",
        "java": "Java",
        "javascript": "JavaScript", "js": "JavaScript", "node": "JavaScript", "nodejs": "JavaScript",
        "html": "HTML", "html5": "HTML",
        "css": "CSS", "css3": "CSS",
        "sql": "SQL", "sqlite": "SQL", "mysql": "SQL", "postgres": "SQL"
    }
    return mapping.get(cleaned, "Python")

def detect_explicit_language(text):
    """Detects if student explicitly requested a specific programming language in their prompt."""
    if not text:
        return None
    text_lower = text.lower()
    
    # 1. C++
    if re.search(r'(?:\bc\+\+|\bcpp\b|\bcplusplus\b)', text_lower):
        return "C++"
        
    # 2. JavaScript (before Java)
    if re.search(r'\b(javascript|js|nodejs|node\.js|ecmascript)\b', text_lower):
        return "JavaScript"
        
    # 3. Java (must not be JavaScript)
    if re.search(r'\bjava\b', text_lower):
        return "Java"
        
    # 4. Python
    if re.search(r'\b(python|python3)\b', text_lower):
        return "Python"
        
    # 5. HTML
    if re.search(r'\b(html|html5)\b', text_lower):
        return "HTML"
        
    # 6. CSS
    if re.search(r'\b(css|css3)\b', text_lower):
        return "CSS"
        
    # 7. SQL
    if re.search(r'\b(sql|mysql|postgresql|sqlite|sqlite3|postgres)\b', text_lower):
        return "SQL"
        
    # 8. C (Must not be C++ or C#)
    if not re.search(r'(?:\bc\+\+|\bc#)', text_lower):
        if re.search(r'\b(c\s+(program|programming|code|language|function|compiler|source|script)|in\s+c\b|using\s+c\b|\bc\s+solution)\b', text_lower):
            return "C"
        if re.search(r'\b(write|create|implement|code)\s+(a\s+)?c\s+(program|code|solution|function|project)\b', text_lower):
            return "C"

    return None

def check_language_mismatch(selected_lang, prompt):
    norm_selected = normalize_language(selected_lang)
    req_lang = detect_explicit_language(prompt)
    if req_lang and req_lang.lower() != norm_selected.lower():
        return {
            "mismatch": True,
            "selected_language": norm_selected,
            "requested_language": req_lang,
            "warning": (
                f"⚠️ Language Mismatch Detected:\n\n"
                f"• Currently Selected Language: {norm_selected}\n"
                f"• Explicitly Requested Language: {req_lang}\n\n"
                f"Why the answer was not generated:\n"
                f"EasyMind AI strictly enforces your selected language ({norm_selected}) to prevent generating solutions in the wrong language. "
                f"Your question explicitly asked for {req_lang}, but {norm_selected} is currently active.\n\n"
                f"What you should do:\n"
                f"Please click the \"{req_lang}\" button to switch languages, or update your question to target {norm_selected}."
            )
        }
    return None

def parse_input_tokens(inp):
    if not inp:
        return []
    cleaned = inp.replace(',', ' ').strip()
    return [t for t in cleaned.split() if t]

def calculate_arithmetic_result(q_lower, tokens):
    try:
        nums = [int(t) for t in tokens]
        if 'sum' in q_lower or 'add' in q_lower or 'addition' in q_lower:
            return str(sum(nums))
        if 'largest' in q_lower or 'maximum' in q_lower or 'max' in q_lower or 'greatest' in q_lower:
            return str(max(nums))
        if 'smallest' in q_lower or 'minimum' in q_lower or 'min' in q_lower:
            return str(min(nums))
        if 'difference' in q_lower or 'subtract' in q_lower:
            if len(nums) == 2:
                return str(nums[0] - nums[1])
        if 'product' in q_lower or 'multiply' in q_lower:
            prod = 1
            for n in nums: prod *= n
            return str(prod)
        if 'even' in q_lower and 'odd' in q_lower:
            if len(nums) == 1:
                return "Even" if nums[0] % 2 == 0 else "Odd"
        if 'factorial' in q_lower:
            if len(nums) == 1 and 0 <= nums[0] <= 20:
                import math
                return str(math.factorial(nums[0]))
    except Exception:
        pass
    return None

def validate_question_and_input(question, input_str, code_str, language):
    q_str = (question or "").strip()
    c_str = (code_str or "").strip()
    inp_str = (input_str or "").strip()
    norm_lang = normalize_language(language)

    # 1. Empty check
    if not q_str and not c_str:
        return {
            "valid": False,
            "has_error": True,
            "error": "The question is empty.",
            "location": "Question input field",
            "why": "EasyMind AI needs a question, problem statement, or code snippet to assist you.",
            "suggested_correction": "Type a question, such as 'Find the largest of three numbers', or paste code to inspect.",
            "corrected_question": "Find the largest of three numbers.",
            "corrected_input": None,
            "expected_output": None
        }

    # 2. Check code syntax errors if code provided in Python
    if c_str and norm_lang == "Python":
        try:
            ast.parse(c_str)
        except SyntaxError as syn:
            return {
                "valid": True,  # Code has error, but we want AI debugging to proceed with details!
                "has_error": True,
                "error": f"Python SyntaxError: {syn.msg}",
                "location": f"Line {syn.lineno}, offset {syn.offset}: '{syn.text.strip() if syn.text else ''}'",
                "why": "The code contains invalid Python syntax that prevents it from parsing.",
                "suggested_correction": "Correct the syntax error or let EasyMind fix it.",
                "corrected_question": q_str or "Fix syntax error in Python code",
                "corrected_input": inp_str,
                "expected_output": None
            }

    # 3. Input format & count validation against question
    q_lower = q_str.lower()
    tokens = parse_input_tokens(inp_str)
    
    wants_int = bool(re.search(r'\b(integer|integers)\b', q_lower))
    wants_num = wants_int or bool(re.search(r'\b(number|numbers)\b', q_lower))
    
    expected_count = None
    if re.search(r'\b(two|2)\s+(integers|numbers|values)\b', q_lower):
        expected_count = 2
    elif re.search(r'\b(three|3)\s+(integers|numbers|values)\b', q_lower):
        expected_count = 3
    elif re.search(r'\b(four|4)\s+(integers|numbers|values)\b', q_lower):
        expected_count = 4
    elif re.search(r'\b(a|an|one|1)\s+(integer|number)\b', q_lower):
        expected_count = 1

    ordinals = ["first", "second", "third", "fourth", "fifth"]
    requires_input = bool(re.search(r'\b(read|input|enter|accept|given)\b', q_lower)) or expected_count is not None

    if requires_input and expected_count is not None:
        if not tokens:
            example = " ".join(["10", "20", "30", "40"][:expected_count])
            corr_out = calculate_arithmetic_result(q_lower, example.split())
            return {
                "valid": False,
                "has_error": True,
                "error": f"Missing required input values (expected {expected_count}).",
                "location": "Input field is empty.",
                "why": f"The problem specifies reading or processing {expected_count} {('integers' if wants_int else 'numbers')}.",
                "suggested_correction": f"Enter {expected_count} {('integers' if wants_int else 'numbers')} separated by space, such as \"{example}\".",
                "corrected_question": q_str,
                "corrected_input": example,
                "expected_output": corr_out
            }

        if len(tokens) != expected_count:
            corr_tokens = (tokens + ["20", "30", "40"])[:expected_count]
            corr_inp = " ".join(corr_tokens)
            corr_out = calculate_arithmetic_result(q_lower, corr_tokens)
            return {
                "valid": False,
                "has_error": True,
                "error": f"Wrong number of input values: expected {expected_count}, but received {len(tokens)}.",
                "location": f"Input contains {len(tokens)} value(s): {tokens}",
                "why": f"The problem specifically requires {expected_count} values.",
                "suggested_correction": f"Provide exactly {expected_count} values separated by space (e.g. \"{corr_inp}\").",
                "corrected_question": q_str,
                "corrected_input": corr_inp,
                "expected_output": corr_out
            }

        # Check types
        if wants_num:
            for idx, tok in enumerate(tokens):
                ord_name = ordinals[idx] if idx < len(ordinals) else f"{idx+1}th"
                if wants_int:
                    try:
                        int(tok)
                    except ValueError:
                        suggested_tok = "20" if idx == 1 else "10"
                        corr_tokens = list(tokens)
                        corr_tokens[idx] = suggested_tok
                        corr_inp = " ".join(corr_tokens)
                        corr_out = calculate_arithmetic_result(q_lower, corr_tokens)
                        return {
                            "valid": False,
                            "has_error": True,
                            "error": f"The {ord_name} input value is not an integer.",
                            "location": f"{ord_name.capitalize()} input value, \"{tok}\".",
                            "why": "An integer must consist only of digits (with an optional leading minus sign). Non-digit characters cannot be parsed as integers.",
                            "suggested_correction": f"Enter a valid integer, such as {suggested_tok}.",
                            "corrected_question": q_str,
                            "corrected_input": corr_inp,
                            "expected_output": corr_out
                        }

    # If valid input provided, compute verified output if arithmetic/standard logic
    calc_output = calculate_arithmetic_result(q_lower, tokens) if tokens else None
    return {
        "valid": True,
        "has_error": False,
        "error": None,
        "location": None,
        "why": None,
        "suggested_correction": None,
        "corrected_question": q_str,
        "corrected_input": inp_str,
        "expected_output": calc_output
    }

def lm_request(messages, max_tokens=2600):
    # Discover available model from local LM Studio server
    req = urllib.request.Request(LM_BASE + "/models", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as response:
        models = json.loads(response.read().decode("utf-8")).get("data", [])
    if not models:
        raise RuntimeError("LM Studio server is running, but no model is available. Please load a model in LM Studio.")
    model_id = models[0]["id"]

    payload = {
        "model": model_id,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.15,
        "max_tokens": max_tokens
    }
    request = urllib.request.Request(
        LM_BASE + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    
    choice = result["choices"][0]
    msg = choice.get("message", {})
    content = msg.get("content") or ""
    # Support thinking models where final response is in reasoning_content or content
    if not content.strip():
        content = msg.get("reasoning_content") or ""
    # Strip <think> tags if present
    content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
    return content

def build_prompt_and_sections(language, mode, prompt, code, custom_input, expected_output_provided, val_res):
    norm_lang = normalize_language(language)
    fence_lang = "cpp" if norm_lang == "C++" else norm_lang.lower()

    # Determine input and expected output values
    active_input = custom_input.strip() if custom_input else ""
    detected_err = "None. Input format and question are valid."
    suggested_corr = "None needed."
    corrected_q = prompt
    corrected_inp = active_input
    verified_output = val_res.get("expected_output")

    if val_res.get("has_error"):
        detected_err = f"Error: {val_res.get('error')}\nLocation: {val_res.get('location')}\nReason: {val_res.get('why')}"
        suggested_corr = val_res.get("suggested_correction") or "Please adjust your input format."
        corrected_q = val_res.get("corrected_question") or prompt
        corrected_inp = val_res.get("corrected_input") or active_input

    mode_instructions = {
        "generate": "Generate complete, clean beginner-friendly code in the authoritative language, then explain it.",
        "explain": "Provide a crystal-clear, simple English explanation of the concept and code logic in the authoritative language.",
        "debug": f"Analyze the student's code below and debug it. Identify any errors, provide the corrected {norm_lang} code, and explain the fix.",
        "steps": f"Provide a detailed step-by-step beginner guide explaining the algorithm and logic in {norm_lang}, followed by the complete code.",
        "tutor": f"Act as an interactive, encouraging tutor. Explain the intuition in {norm_lang}, walk through the logic, and provide a helpful understanding check.",
        "custom_input": f"Process the student's custom problem statement and test inputs. Implement the solution strictly in {norm_lang}."
    }

    inst = mode_instructions.get(mode, mode_instructions["generate"])

    user_content = f"""AUTHORITATIVE SELECTED PROGRAMMING LANGUAGE: {norm_lang}
MODE: {mode.upper()}
STUDENT QUESTION / PROBLEM: {prompt}
INPUT PROVIDED: {active_input if active_input else '(None specified by student)'}
STUDENT CODE (IF ANY):
{code if code else '(None provided)'}

TASK INSTRUCTIONS:
{inst}

MANDATORY RULES:
1. Write ALL code STRICTLY in {norm_lang}. Do NOT use Python if {norm_lang} is C++, C, Java, JavaScript, HTML, CSS, or SQL.
2. Structure your response clearly using these 10 distinct markdown headings:

### 1. Selected Language
{norm_lang}

### 2. Original Question
{prompt}

### 3. Input Provided
{active_input if active_input else 'None specified / standard execution'}

### 4. Detected Errors
{detected_err}

### 5. Suggested Correction
{suggested_corr}

### 6. Corrected Question / Input
Question: {corrected_q}
Sample Valid Input: {corrected_inp if corrected_inp else 'N/A'}

### 7. Program Code
(Provide the complete, beginner-friendly program in a ```{fence_lang} fenced code block)

### 8. Expected Output
(Show the expected output. If input '{corrected_inp}' was used, show the exact result: {verified_output if verified_output else 'calculate and explain predicted result'}. Clearly note: [AI-Predicted & Verified Logic — not compiled on server].)

### 9. Simple English Explanation
(Explain how the {norm_lang} program works in numbered steps)

### 10. Suggestions for Testing Other Inputs
(Suggest 2-3 specific test cases or edge cases to try next)
"""
    return user_content

def run_code(language, code, input_text=""):
    lang = language.lower().strip()
    # HTML/CSS/JavaScript are previewed in the browser, not executed on the server.
    if lang in ("html", "css", "javascript", "js"):
        return {"ok": True, "output": "This language runs in the browser preview. Click “Preview HTML/CSS/JS” to view it.", "mode": "preview"}
    
    # Run code only on the user's own computer. A short timeout limits accidental infinite loops.
    with tempfile.TemporaryDirectory(prefix="easymind_") as tmp:
        work = Path(tmp)
        try:
            if lang == "python":
                exe = shutil.which("python") or shutil.which("py")
                if not exe:
                    return {"ok": False, "output": "Python was not found. Install Python 3 and enable it, or use the Windows command `py`.", "mode": "error"}
                file = work / "main.py"
                file.write_text(code, encoding="utf-8")
                cmd = [exe, str(file)]
            elif lang in ("c", "c++", "cpp"):
                compiler = shutil.which("gcc") if lang == "c" else (shutil.which("g++") or shutil.which("clang++"))
                if not compiler:
                    return {"ok": False, "output": "A C/C++ compiler was not found (gcc/g++). Install a compiler such as MinGW-w64 first. Code generation still works without it.", "mode": "error"}
                source = work / ("main.c" if lang == "c" else "main.cpp")
                binary = work / ("main.exe" if os.name == "nt" else "main")
                source.write_text(code, encoding="utf-8")
                compile_result = subprocess.run([compiler, str(source), "-o", str(binary)], cwd=tmp, capture_output=True, text=True, timeout=20)
                if compile_result.returncode != 0:
                    return {"ok": False, "output": (compile_result.stderr or compile_result.stdout or "Compilation failed.")[:12000], "mode": "compile-error"}
                cmd = [str(binary)]
            elif lang == "java":
                javac, java = shutil.which("javac"), shutil.which("java")
                if not javac or not java:
                    return {"ok": False, "output": "Java JDK was not found. Install a JDK and make sure `java` and `javac` work in Command Prompt.", "mode": "error"}
                source = work / "Main.java"
                source.write_text(code, encoding="utf-8")
                compile_result = subprocess.run([javac, str(source)], cwd=tmp, capture_output=True, text=True, timeout=25)
                if compile_result.returncode != 0:
                    return {"ok": False, "output": (compile_result.stderr or compile_result.stdout or "Compilation failed.")[:12000], "mode": "compile-error"}
                cmd = [java, "-cp", tmp, "Main"]
            elif lang == "sql":
                import sqlite3
                db = sqlite3.connect(":memory:")
                try:
                    cursor = db.cursor()
                    cursor.executescript(code)
                    rows = cursor.fetchall() if cursor.description else []
                    return {"ok": True, "output": json.dumps(rows, indent=2, ensure_ascii=False) if rows else "SQL executed successfully. (No result rows returned.)", "mode": "run"}
                finally:
                    db.close()
            else:
                return {"ok": False, "output": "Choose a supported language.", "mode": "error"}
            result = subprocess.run(cmd, input=input_text, cwd=tmp, capture_output=True, text=True, timeout=5)
            out = result.stdout or ""
            if result.stderr:
                out += ("\n" if out else "") + "STDERR:\n" + result.stderr
            if result.returncode != 0:
                out += ("\n" if out else "") + f"\nProgram exited with code {result.returncode}."
            return {"ok": result.returncode == 0, "output": out[:12000] or "(Program finished with no printed output.)", "mode": "run"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "Stopped: the program took longer than the 5-second safety limit.", "mode": "timeout"}
        except Exception as exc:
            return {"ok": False, "output": f"Runner error: {exc}", "mode": "error"}

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, data, content_type="application/json; charset=utf-8"):
        raw = data if isinstance(data, bytes) else data.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/status":
            try:
                req = urllib.request.Request(LM_BASE + "/models")
                with urllib.request.urlopen(req, timeout=3) as response:
                    models = json.loads(response.read().decode("utf-8")).get("data", [])
                self._send(200, json.dumps({
                    "ok": bool(models),
                    "models": [m.get("id", "model") for m in models]
                }))
            except Exception:
                self._send(200, json.dumps({
                    "ok": False,
                    "models": [],
                    "message": "Start the LM Studio local server on port 1234 and load a model."
                }))
            return

        path = "/index.html" if self.path == "/" else self.path.split("?", 1)[0]
        if ".." in path:
            self._send(400, "Invalid path", "text/plain; charset=utf-8")
            return
        target = (ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(ROOT.resolve())) or not target.is_file():
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8"
        self._send(200, target.read_bytes(), content_type)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            self._send(413, json.dumps({"error": "Request too large"}))
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path in ("/api/ask", "/api/check_input"):
                user_text = str(data.get("prompt", "")).strip()
                language = normalize_language(str(data.get("language", "Python")))
                mode = str(data.get("mode", "generate")).strip().lower()
                code = str(data.get("code", ""))
                custom_input = str(data.get("custom_input", data.get("input", ""))).strip()
                expected_output_user = str(data.get("expected_output", "")).strip()

                # Feature 4 Check: Empty Question Check
                if not user_text and not code:
                    self._send(400, json.dumps({
                        "error": "The question is empty. Please enter your programming question or paste your code.",
                        "validation": {
                            "valid": False,
                            "error": "The question is empty.",
                            "location": "Question input field",
                            "why": "EasyMind AI requires a question or problem description to assist you.",
                            "suggested_correction": "Type a clear question such as 'Find the largest of three numbers'."
                        }
                    }))
                    return

                # Feature 2 Check: Language Mismatch
                mismatch_info = check_language_mismatch(language, user_text)
                if mismatch_info:
                    self._send(200, json.dumps(mismatch_info, ensure_ascii=False))
                    return

                # Feature 4 Check: Input Validation & Error Detection
                val_res = validate_question_and_input(user_text, custom_input, code, language)

                # Build prompt with authoritative language and 10 structured sections
                prompt_content = build_prompt_and_sections(
                    language=language,
                    mode=mode,
                    prompt=user_text,
                    code=code,
                    custom_input=custom_input,
                    expected_output_provided=expected_output_user,
                    val_res=val_res
                )

                # Request answer from local LM Studio server
                answer = lm_request([{"role": "user", "content": prompt_content}])

                response_payload = {
                    "answer": answer,
                    "language": language,
                    "validation": val_res,
                    "calculated_output": val_res.get("expected_output"),
                    "mismatch": False
                }
                self._send(200, json.dumps(response_payload, ensure_ascii=False))

            elif self.path == "/api/run":
                result = run_code(str(data.get("language", "Python")), str(data.get("code", "")), str(data.get("input", "")))
                self._send(200, json.dumps(result, ensure_ascii=False))
            else:
                self._send(404, json.dumps({"error": "Unknown API route"}))
        except urllib.error.URLError as exc:
            self._send(503, json.dumps({
                "error": "Could not connect to LM Studio at http://127.0.0.1:1234. Please open LM Studio, load your model (e.g. Qwen3-4B), and start the local server on port 1234.",
                "details": str(exc)
            }))
        except Exception as exc:
            self._send(500, json.dumps({"error": str(exc)}))

    def log_message(self, format, *args):
        print("[EasyMind AI]", format % args)

if __name__ == "__main__":
    print("EasyMind AI is starting...")
    print("Open http://127.0.0.1:8000 in your browser.")
    print("Keep LM Studio running with a model loaded and its local server enabled at port 1234.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
