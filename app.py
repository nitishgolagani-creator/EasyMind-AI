import os
import re
import sys
import json
import sqlite3
import datetime
import requests
import subprocess
import shutil
import tempfile
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load local environment variables if .env exists
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "database")
GENERATED_CODE_DIR = os.path.join(BASE_DIR, "generated_code")
DB_PATH = os.path.join(DATABASE_DIR, "easymind.db")

# Ensure required directories exist
os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(GENERATED_CODE_DIR, exist_ok=True)

# App Configuration
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "easymind-local-ai-secret-key-2026")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max request size

# LM Studio Configuration (Strictly Local)
DEFAULT_LM_STUDIO_URL = "http://localhost:1234/v1"
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", DEFAULT_LM_STUDIO_URL).rstrip("/")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "").strip()

# Language extension mapping
LANGUAGE_CONFIG = {
    "python": {"name": "Python", "ext": ".py", "icon": "🐍", "runner": "Python 3 Subprocess"},
    "c": {"name": "C", "ext": ".c", "icon": "⚡", "runner": "GCC Native (if installed)"},
    "cpp": {"name": "C++", "ext": ".cpp", "icon": "🚀", "runner": "G++ Native (if installed)"},
    "java": {"name": "Java", "ext": ".java", "icon": "☕", "runner": "JDK Native (if installed)"},
    "javascript": {"name": "JavaScript", "ext": ".js", "icon": "🌐", "runner": "Node.js Subprocess"},
    "html": {"name": "HTML", "ext": ".html", "icon": "📄", "runner": "Live Browser Sandboxed Preview"},
    "css": {"name": "CSS", "ext": ".css", "icon": "🎨", "runner": "Live Browser Sandboxed Preview"},
    "sql": {"name": "SQL", "ext": ".sql", "icon": "🗄️", "runner": "In-Memory SQLite Engine"},
    "any": {"name": "General / Any", "ext": ".txt", "icon": "💡", "runner": "Syntax Highlighter"}
}

# -------------------------------------------------------------
# Database Management
# -------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                language TEXT DEFAULT 'any',
                mode TEXT DEFAULT 'chat',
                model_used TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                language TEXT NOT NULL,
                code TEXT NOT NULL,
                notes TEXT,
                filename TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Seamless column migration if older database exists
        cursor.execute("PRAGMA table_info(saved_snippets)")
        cols = [c[1] for c in cursor.fetchall()]
        if "timestamp" not in cols and "created_at" in cols:
            cursor.execute("ALTER TABLE saved_snippets ADD COLUMN timestamp DATETIME")
            cursor.execute("UPDATE saved_snippets SET timestamp = created_at WHERE timestamp IS NULL")

        cursor.execute("PRAGMA table_info(chat_history)")
        chat_cols = [c[1] for c in cursor.fetchall()]
        if "timestamp" not in chat_cols and "created_at" in chat_cols:
            cursor.execute("ALTER TABLE chat_history ADD COLUMN timestamp DATETIME")
            cursor.execute("UPDATE chat_history SET timestamp = created_at WHERE timestamp IS NULL")

        conn.commit()

init_db()

def get_saved_setting(key, default=None):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
    except Exception:
        pass
    return default

def set_saved_setting(key, value):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
            return True
    except Exception:
        return False

# -------------------------------------------------------------
# Safe Isolated Code Execution Engine
# -------------------------------------------------------------
def execute_code_safely(code: str, language: str, stdin_data: str = ""):
    """Safely executes code in isolated subprocesses with timeout and resource limits."""
    lang = language.lower().strip()
    
    if not code or not code.strip():
        return {
            "success": False,
            "error": "Code cannot be empty.",
            "output": "",
            "execution_time_ms": 0
        }

    start_time = datetime.datetime.now()

    # 1. Python execution via sys.executable (separate subprocess)
    if lang in ["python", "py"]:
        try:
            proc = subprocess.run(
                [sys.executable, "-u", "-c", code],
                input=stdin_data.encode("utf-8"),
                capture_output=True,
                timeout=5
            )
            elapsed = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
            stdout = proc.stdout.decode("utf-8", errors="replace")[:30000]
            stderr = proc.stderr.decode("utf-8", errors="replace")[:30000]
            
            if proc.returncode == 0:
                output = stdout if stdout else "(Code executed successfully with no console output)"
                return {
                    "success": True,
                    "output": output,
                    "stderr": stderr,
                    "exit_code": 0,
                    "execution_time_ms": elapsed
                }
            else:
                return {
                    "success": False,
                    "output": stdout,
                    "error": stderr if stderr else f"Process exited with code {proc.returncode}",
                    "exit_code": proc.returncode,
                    "execution_time_ms": elapsed
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Execution timed out (5-second limit exceeded). Check for infinite loops or blocking calls.",
                "output": "",
                "execution_time_ms": 5000
            }
        except Exception as e:
            return {"success": False, "error": f"Execution error: {str(e)}", "output": "", "execution_time_ms": 0}

    # 2. JavaScript execution via Node.js
    elif lang in ["javascript", "js"]:
        node_bin = shutil.which("node")
        if not node_bin:
            return {
                "success": False,
                "error": "Node.js is not installed or not found on Windows PATH. Please install Node.js to run JavaScript locally.",
                "output": "",
                "execution_time_ms": 0
            }
        try:
            proc = subprocess.run(
                [node_bin, "-e", code],
                input=stdin_data.encode("utf-8"),
                capture_output=True,
                timeout=5
            )
            elapsed = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
            stdout = proc.stdout.decode("utf-8", errors="replace")[:30000]
            stderr = proc.stderr.decode("utf-8", errors="replace")[:30000]
            
            if proc.returncode == 0:
                output = stdout if stdout else "(JavaScript executed successfully with no console output)"
                return {
                    "success": True,
                    "output": output,
                    "stderr": stderr,
                    "exit_code": 0,
                    "execution_time_ms": elapsed
                }
            else:
                return {
                    "success": False,
                    "output": stdout,
                    "error": stderr if stderr else f"Node process exited with code {proc.returncode}",
                    "exit_code": proc.returncode,
                    "execution_time_ms": elapsed
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Execution timed out (5-second limit exceeded). Check for infinite loops.",
                "output": "",
                "execution_time_ms": 5000
            }
        except Exception as e:
            return {"success": False, "error": f"Node execution error: {str(e)}", "output": "", "execution_time_ms": 0}

    # 3. SQL execution via in-memory SQLite
    elif lang == "sql":
        try:
            mem_db = sqlite3.connect(":memory:")
            cursor = mem_db.cursor()
            
            # Execute entire script
            cursor.executescript(code)
            
            output_lines = ["--- In-Memory SQLite Execution Result ---"]
            # Look for SELECT statements to display tabular results
            select_queries = re.findall(r"(SELECT\s+[\s\S]+?;)", code, flags=re.IGNORECASE)
            if not select_queries:
                # Try finding select without semicolon at end
                if "select" in code.lower():
                    select_queries = [code]

            if select_queries:
                for q in select_queries:
                    clean_q = q.strip()
                    try:
                        cursor.execute(clean_q)
                        rows = cursor.fetchall()
                        col_names = [d[0] for d in cursor.description] if cursor.description else []
                        if col_names:
                            header = " | ".join(str(c) for c in col_names)
                            divider = "-+-".join("-" * len(str(c)) for c in col_names)
                            output_lines.append(f"\nQuery: {clean_q}")
                            output_lines.append(header)
                            output_lines.append(divider)
                            for r in rows:
                                output_lines.append(" | ".join(str(val) for val in r))
                            output_lines.append(f"({len(rows)} row(s) returned)\n")
                    except Exception as q_err:
                        output_lines.append(f"Query notice: {q_err}")
            else:
                output_lines.append("DDL / DML statements executed successfully in memory. Database state updated.")
            
            mem_db.close()
            elapsed = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
            return {
                "success": True,
                "output": "\n".join(output_lines),
                "exit_code": 0,
                "execution_time_ms": elapsed
            }
        except Exception as sql_err:
            return {"success": False, "error": f"SQL Error: {str(sql_err)}", "output": "", "execution_time_ms": 0}

    # 4. HTML/CSS: Presentation markup
    elif lang in ["html", "css"]:
        return {
            "success": True,
            "output": "HTML and CSS are presentation markup languages. Use the interactive live browser preview tab to view live rendering.",
            "is_markup": True,
            "execution_time_ms": 0
        }

    # 5. Compiled languages (C, C++, Java)
    elif lang in ["c", "cpp"]:
        compiler_cmd = "gcc" if lang == "c" else "g++"
        compiler_bin = shutil.which(compiler_cmd)
        if not compiler_bin:
            return {
                "success": False,
                "error": f"Local {compiler_cmd.upper()} compiler was not found on your Windows PATH.\nTo compile and run C/C++ natively on Windows 11, install MinGW-w64 or Visual Studio C++ Build Tools.\n\nPython, JavaScript (Node.js), and in-memory SQL execution are fully supported locally.",
                "output": "",
                "execution_time_ms": 0
            }
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                src_ext = ".c" if lang == "c" else ".cpp"
                src_path = os.path.join(tmpdir, f"main{src_ext}")
                exe_path = os.path.join(tmpdir, "main.exe")
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(code)
                comp = subprocess.run([compiler_bin, src_path, "-o", exe_path], capture_output=True, timeout=10)
                if comp.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Compilation Error:\n{comp.stderr.decode('utf-8', errors='replace')}",
                        "output": "",
                        "execution_time_ms": 0
                    }
                run_p = subprocess.run([exe_path], input=stdin_data.encode("utf-8"), capture_output=True, timeout=5)
                elapsed = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
                return {
                    "success": True,
                    "output": run_p.stdout.decode("utf-8", errors="replace"),
                    "stderr": run_p.stderr.decode("utf-8", errors="replace"),
                    "exit_code": run_p.returncode,
                    "execution_time_ms": elapsed
                }
        except Exception as e:
            return {"success": False, "error": f"C/C++ runtime error: {str(e)}", "output": "", "execution_time_ms": 0}

    elif lang == "java":
        javac_bin = shutil.which("javac")
        java_bin = shutil.which("java")
        if not javac_bin or not java_bin:
            return {
                "success": False,
                "error": "Java Development Kit (javac/java) was not found on your Windows PATH.\nTo run Java natively on Windows 11, install OpenJDK or Oracle JDK.\n\nPython, JavaScript (Node.js), and in-memory SQL execution are fully supported locally.",
                "output": "",
                "execution_time_ms": 0
            }
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                match = re.search(r"public\s+class\s+([A-Za-z0-9_]+)", code)
                class_name = match.group(1) if match else "Main"
                java_file = os.path.join(tmpdir, f"{class_name}.java")
                with open(java_file, "w", encoding="utf-8") as f:
                    f.write(code)
                comp = subprocess.run([javac_bin, java_file], capture_output=True, timeout=10)
                if comp.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Java Compilation Error:\n{comp.stderr.decode('utf-8', errors='replace')}",
                        "output": "",
                        "execution_time_ms": 0
                    }
                run_p = subprocess.run([java_bin, "-cp", tmpdir, class_name], input=stdin_data.encode("utf-8"), capture_output=True, timeout=5)
                elapsed = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
                return {
                    "success": True,
                    "output": run_p.stdout.decode("utf-8", errors="replace"),
                    "stderr": run_p.stderr.decode("utf-8", errors="replace"),
                    "exit_code": run_p.returncode,
                    "execution_time_ms": elapsed
                }
        except Exception as e:
            return {"success": False, "error": f"Java runtime error: {str(e)}", "output": "", "execution_time_ms": 0}

    return {"success": False, "error": f"Execution runner not available for '{language}'.", "output": "", "execution_time_ms": 0}

# -------------------------------------------------------------
# LM Studio Local Service Layer
# -------------------------------------------------------------
def fetch_lm_studio_models():
    """Queries LM Studio for loaded/available models."""
    url = f"{LM_STUDIO_BASE_URL}/models"
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            models = [item.get("id") for item in data.get("data", []) if item.get("id")]
            return {"connected": True, "models": models, "error": None}
        return {
            "connected": False,
            "models": [],
            "error": f"LM Studio responded with HTTP status {response.status_code}"
        }
    except requests.exceptions.ConnectionError:
        return {
            "connected": False,
            "models": [],
            "error": "Cannot connect to LM Studio at http://localhost:1234. Please ensure LM Studio is running and the Local Server is started on port 1234."
        }
    except requests.exceptions.Timeout:
        return {
            "connected": False,
            "models": [],
            "error": "Connection to LM Studio timed out. The local server might be busy or frozen."
        }
    except Exception as e:
        return {
            "connected": False,
            "models": [],
            "error": f"Unexpected error connecting to LM Studio: {str(e)}"
        }

def get_active_model_id():
    """Determines the active model: user selected, configured, or first model returned by LM Studio."""
    saved_model = get_saved_setting("active_model", LM_STUDIO_MODEL)
    status = fetch_lm_studio_models()
    if status["connected"] and status["models"]:
        if saved_model and saved_model in status["models"]:
            return saved_model, None
        return status["models"][0], None
    if not status["connected"]:
        return None, status["error"]
    return None, "LM Studio local server is online, but no model is currently loaded. Please load a model in LM Studio."

def build_system_prompt(language: str, mode: str) -> str:
    lang_info = LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["any"])
    lang_name = lang_info["name"]

    base_instructions = (
        "You are EasyMind AI, an expert, patient, and friendly local programming learning tutor.\n"
        "Your mission is to help developers, students, and engineers understand programming concepts clearly.\n"
        "Follow these strict principles:\n"
        "- Explain concepts in simple, plain, jargon-free English.\n"
        "- When providing code, always wrap it inside standard Markdown fenced code blocks with the exact language identifier (e.g. ```python ... ```).\n"
        "- Code must be clean, robust, well-commented, and safe to inspect.\n"
        "- Always explain WHY the code works, not just WHAT it does.\n"
        f"- Target Programming Language for this session: {lang_name}.\n"
    )

    mode_directives = {
        "generate": (
            "TASK: CODE GENERATION\n"
            "- Write complete, runnable, and syntactically valid code in the specified language.\n"
            "- Include inline comments explaining key logic.\n"
            "- Follow best modern conventions and practices.\n"
            "- After the code block, provide a clear, bulleted summary of how the implementation works in simple English.\n"
        ),
        "explain": (
            "TASK: CODE EXPLANATION IN SIMPLE ENGLISH\n"
            "- Break down the provided code or concept into logical, beginner-friendly steps.\n"
            "- Use clear analogies if helpful.\n"
            "- Explain inputs, processing steps, edge cases, and expected outputs.\n"
            "- Highlight important functions, loops, data structures, or syntax rules.\n"
        ),
        "debug": (
            "TASK: DEBUGGING ASSISTANCE & ROOT CAUSE ANALYSIS\n"
            "- Carefully inspect the user's code or error message.\n"
            "- Clearly identify the bugs, logic flaws, or syntax issues.\n"
            "- Explain WHY the bug happens in plain terms.\n"
            "- Provide the corrected code block.\n"
            "- Give practical tips to prevent this issue in the future.\n"
        ),
        "doctor": (
            "TASK: ERROR DOCTOR & DIAGNOSTIC REPAIR\n"
            "- Carefully analyze the user's error message and the code snippet.\n"
            "- Structure your response with these exact markdown sections:\n"
            "  ### 1. Root Cause\n"
            "  (Explain precisely why the error occurred in simple, plain English without jargon.)\n"
            "  ### 2. Conceptual Explanation\n"
            "  (Explain the underlying concept or language rule that was violated.)\n"
            "  ### 3. Step-by-Step Fix Instructions\n"
            "  (Provide numbered, actionable steps to resolve the issue.)\n"
            "  ### 4. Corrected Code\n"
            "  (Provide the fully corrected, runnable code inside standard Markdown fenced code blocks.)\n"
        ),
        "practice": (
            "TASK: PRACTICE & DEBUG TUTOR\n"
            "- The user has provided a programming question and their attempt/code.\n"
            "- Structure your response with these exact markdown sections:\n"
            "  ### 1. Code Review & Analysis\n"
            "  (Highlight what the user did right and identify any bugs or logic gaps.)\n"
            "  ### 2. Guided Hint\n"
            "  (Offer an intuitive hint to help them think through the solution before revealing all.)\n"
            "  ### 3. Complete Solution\n"
            "  (Provide the complete, clean, well-commented code inside fenced blocks.)\n"
            "  ### 4. Complexity & Best Practices\n"
            "  (Time/Space complexity and tips for mastery.)\n"
        ),
        "testcases": (
            "TASK: CUSTOM QUESTIONS & TEST CASE GENERATOR\n"
            "- Provide a clean, robust, runnable solution in the specified language.\n"
            "- Then provide 3 diverse test cases clearly formatted:\n"
            "  1. Standard/Typical Case\n"
            "  2. Edge Case (empty, boundary, zero, or negative)\n"
            "  3. Large or Tricky Case\n"
            "- Clearly specify the Input and Expected Output for each test case.\n"
        ),
        "guide": (
            "TASK: STEP-BY-STEP PROGRAMMING GUIDANCE\n"
            "- Provide a structured, numbered step-by-step roadmap.\n"
            "- Guide the student from requirements -> logic/algorithm design -> implementation -> testing.\n"
            "- Include small, digestible code examples for each step.\n"
        ),
        "chat": (
            "TASK: PROGRAMMING TUTOR CONVERSATION\n"
            "- Provide thoughtful, accurate, and encouraging programming answers.\n"
            "- Keep answers structured, readable, and focused on learning.\n"
        )
    }

    selected_directive = mode_directives.get(mode, mode_directives["chat"])
    return f"{base_instructions}\n{selected_directive}"

def extract_code_blocks(markdown_text: str):
    """Extracts fenced code blocks from markdown."""
    pattern = r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```"
    matches = re.findall(pattern, markdown_text, flags=re.DOTALL)
    blocks = []
    for lang_tag, code in matches:
        blocks.append({
            "language": lang_tag.strip().lower() or "text",
            "code": code.strip()
        })
    return blocks

# -------------------------------------------------------------
# Curated Educational Examples
# -------------------------------------------------------------
def get_curated_examples():
    """Returns curated educational code examples for all 8 supported languages."""
    return {
        "python": [
            {
                "title": "Two Sum (Hash Map Lookup)",
                "difficulty": "Easy / Fundamental",
                "code": (
                    "def two_sum(nums, target):\n"
                    "    \"\"\"Finds indices of two numbers that add up to target in O(N) time.\"\"\"\n"
                    "    seen = {}\n"
                    "    for i, num in enumerate(nums):\n"
                    "        complement = target - num\n"
                    "        if complement in seen:\n"
                    "            return [seen[complement], i]\n"
                    "        seen[num] = i\n"
                    "    return []\n\n"
                    "# Example verification\n"
                    "numbers = [2, 7, 11, 15]\n"
                    "target_sum = 9\n"
                    "result = two_sum(numbers, target_sum)\n"
                    "print(f\"Numbers: {numbers}, Target: {target_sum}\")\n"
                    "print(f\"Indices: {result} (values: {numbers[result[0]]} + {numbers[result[1]]})\")\n"
                ),
                "explanation": "Uses a Python dictionary as a hash map. Instead of checking every pair in O(N^2), we store each visited number and check for its complement in O(1) time.",
                "takeaway": "Hash maps turn nested search loops into single-pass linear scans."
            },
            {
                "title": "Recursive Fibonacci with Memoization",
                "difficulty": "Intermediate",
                "code": (
                    "from functools import lru_cache\n\n"
                    "@lru_cache(maxsize=None)\n"
                    "def fibonacci(n):\n"
                    "    if n < 0:\n"
                    "        raise ValueError(\"n must be non-negative\")\n"
                    "    if n in (0, 1):\n"
                    "        return n\n"
                    "    return fibonacci(n - 1) + fibonacci(n - 2)\n\n"
                    "# Compute first 10 Fibonacci numbers\n"
                    "fib_series = [fibonacci(i) for i in range(10)]\n"
                    "print(\"First 10 Fibonacci numbers:\", fib_series)\n"
                    "print(\"50th Fibonacci number:\", fibonacci(50))\n"
                ),
                "explanation": "Standard recursion for Fibonacci has O(2^N) exponential time. By adding `@lru_cache`, Python remembers previous results, reducing time complexity to O(N).",
                "takeaway": "Memoization prevents repeated recalculation of identical subproblems in dynamic programming."
            }
        ],
        "javascript": [
            {
                "title": "Array Transformations (Map, Filter, Reduce)",
                "difficulty": "Easy / Core",
                "code": (
                    "const products = [\n"
                    "  { id: 1, name: 'Mechanical Keyboard', price: 120, inStock: true },\n"
                    "  { id: 2, name: 'Gaming Mouse', price: 60, inStock: false },\n"
                    "  { id: 3, name: 'Ultrawide Monitor', price: 450, inStock: true },\n"
                    "  { id: 4, name: 'USB-C Cable', price: 15, inStock: true }\n"
                    "];\n\n"
                    "// 1. Filter only in-stock items\n"
                    "const available = products.filter(p => p.inStock);\n\n"
                    "// 2. Map to discounted prices (10% off)\n"
                    "const discounted = available.map(p => ({\n"
                    "  ...p,\n"
                    "  discountedPrice: p.price * 0.9\n"
                    "}));\n\n"
                    "// 3. Reduce to calculate total cart value\n"
                    "const total = discounted.reduce((sum, p) => sum + p.discountedPrice, 0);\n\n"
                    "console.log('Available discounted products:', discounted);\n"
                    "console.log(`Total cart price: $${total.toFixed(2)}`);\n"
                ),
                "explanation": "Demonstrates pure functional array methods in JavaScript without mutating the original dataset.",
                "takeaway": "Chain filter, map, and reduce to process data cleanly and immutably."
            },
            {
                "title": "Debounce Function Implementation",
                "difficulty": "Intermediate",
                "code": (
                    "function debounce(func, delayMs) {\n"
                    "  let timer;\n"
                    "  return function (...args) {\n"
                    "    clearTimeout(timer);\n"
                    "    timer = setTimeout(() => {\n"
                    "      func.apply(this, args);\n"
                    "    }, delayMs);\n"
                    "  };\n"
                    "}\n\n"
                    "// Test simulation\n"
                    "const handleSearch = debounce((query) => {\n"
                    "  console.log(`Searching database for: \"${query}\"`);\n"
                    "}, 300);\n\n"
                    "handleSearch('p');\n"
                    "handleSearch('py');\n"
                    "handleSearch('python'); // Only this final call executes after 300ms\n"
                ),
                "explanation": "Debouncing postpones function execution until a specified delay has elapsed since the last time it was invoked. Crucial for search inputs and resize listeners.",
                "takeaway": "Debouncing prevents spamming network requests or heavy calculations on rapid events."
            }
        ],
        "c": [
            {
                "title": "Safe In-Place String Reversal (Pointers)",
                "difficulty": "Easy / Core",
                "code": (
                    "#include <stdio.h>\n"
                    "#include <string.h>\n\n"
                    "void reverse_string(char *str) {\n"
                    "    if (str == NULL) return;\n"
                    "    char *left = str;\n"
                    "    char *right = str + strlen(str) - 1;\n"
                    "    char temp;\n\n"
                    "    while (left < right) {\n"
                    "        temp = *left;\n"
                    "        *left = *right;\n"
                    "        *right = temp;\n"
                    "        left++;\n"
                    "        right--;\n"
                    "    }\n"
                    "}\n\n"
                    "int main() {\n"
                    "    char message[] = \"EasyMind AI Offline\";\n"
                    "    printf(\"Original: %s\\n\", message);\n"
                    "    reverse_string(message);\n"
                    "    printf(\"Reversed: %s\\n\", message);\n"
                    "    return 0;\n"
                    "}\n"
                ),
                "explanation": "Demonstrates two-pointer traversal in C. Left pointer advances while right pointer decrements, swapping characters in-place without extra heap allocation.",
                "takeaway": "Direct pointer arithmetic is fast, memory efficient, and fundamental to C systems programming."
            }
        ],
        "cpp": [
            {
                "title": "Modern Vector Operations with Custom Lambda",
                "difficulty": "Intermediate",
                "code": (
                    "#include <iostream>\n"
                    "#include <vector>\n"
                    "#include <algorithm>\n"
                    "#include <string>\n\n"
                    "struct Student {\n"
                    "    std::string name;\n"
                    "    double gpa;\n"
                    "};\n\n"
                    "int main() {\n"
                    "    std::vector<Student> students = {\n"
                    "        {\"Alice\", 3.85},\n"
                    "        {\"Bob\", 3.42},\n"
                    "        {\"Charlie\", 3.95},\n"
                    "        {\"Diana\", 3.70}\n"
                    "    };\n\n"
                    "    // Sort descending by GPA using modern C++ lambda\n"
                    "    std::sort(students.begin(), students.end(), [](const Student &a, const Student &b) {\n"
                    "        return a.gpa > b.gpa;\n"
                    "    });\n\n"
                    "    std::cout << \"Honor Roll Ranking:\\n\";\n"
                    "    for (const auto &s : students) {\n"
                    "        std::cout << \"- \" << s.name << \" (GPA: \" << s.gpa << \")\\n\";\n"
                    "    }\n"
                    "    return 0;\n"
                    "}\n"
                ),
                "explanation": "Leverages C++ STL `std::vector`, `std::sort`, and concise anonymous lambda expressions for clean, type-safe custom sorting.",
                "takeaway": "Modern C++ lambdas replace verbose functor structs with expressive inline comparator logic."
            }
        ],
        "java": [
            {
                "title": "Stream API & Custom Object Pipeline",
                "difficulty": "Intermediate",
                "code": (
                    "import java.util.List;\n"
                    "import java.util.Arrays;\n"
                    "import java.util.stream.Collectors;\n\n"
                    "class Book {\n"
                    "    String title;\n"
                    "    int pages;\n"
                    "    Book(String t, int p) { this.title = t; this.pages = p; }\n"
                    "}\n\n"
                    "public class Main {\n"
                    "    public static void main(String[] args) {\n"
                    "        List<Book> library = Arrays.asList(\n"
                    "            new Book(\"Clean Code\", 464),\n"
                    "            new Book(\"The Pragmatic Programmer\", 352),\n"
                    "            new Book(\"Refactoring\", 448),\n"
                    "            new Book(\"Design Patterns\", 395)\n"
                    "        );\n\n"
                    "        // Filter books > 400 pages, sort, and collect titles\n"
                    "        List<String> largeBooks = library.stream()\n"
                    "            .filter(b -> b.pages > 400)\n"
                    "            .map(b -> b.title.toUpperCase() + \" (\" + b.pages + \"p)\")\n"
                    "            .collect(Collectors.toList());\n\n"
                    "        System.out.println(\"Comprehensive Engineering Books:\");\n"
                    "        largeBooks.forEach(System.out::println);\n"
                    "    }\n"
                    "}\n"
                ),
                "explanation": "Illustrates Java 8+ functional streaming pipeline with filter, map, and collector operations.",
                "takeaway": "Streams allow declarative, thread-safe data processing without manual loop index management."
            }
        ],
        "html": [
            {
                "title": "Accessible Semantic Profile Component",
                "difficulty": "Beginner / Core",
                "code": (
                    "<article class=\"profile-card\" aria-labelledby=\"user-heading\">\n"
                    "  <header class=\"card-header\">\n"
                    "    <figure class=\"avatar-wrapper\">\n"
                    "      <div class=\"avatar-badge\">PRO</div>\n"
                    "    </figure>\n"
                    "    <div class=\"user-info\">\n"
                    "      <h2 id=\"user-heading\">Niteesh Developer</h2>\n"
                    "      <p class=\"role-tag\">Full-Stack & Local AI Engineer</p>\n"
                    "    </div>\n"
                    "  </header>\n"
                    "  <section class=\"card-body\">\n"
                    "    <p>Building private, local AI applications running on Windows 11 with LM Studio.</p>\n"
                    "    <ul class=\"skills-list\" aria-label=\"Core Technologies\">\n"
                    "      <li>Python</li>\n"
                    "      <li>Flask</li>\n"
                    "      <li>SQLite</li>\n"
                    "      <li>Vanilla CSS</li>\n"
                    "    </ul>\n"
                    "  </section>\n"
                    "  <footer class=\"card-footer\">\n"
                    "    <button type=\"button\" class=\"btn-connect\">Connect</button>\n"
                    "  </footer>\n"
                    "</article>\n"
                ),
                "explanation": "Uses standard HTML5 semantic elements (`<article>`, `<header>`, `<figure>`, `aria-*`) for accessibility and screen reader friendliness.",
                "takeaway": "Semantic HTML improves SEO, accessibility, and maintenance over generic `<div>` soup."
            }
        ],
        "css": [
            {
                "title": "Modern Glassmorphism Card with Gradient Border",
                "difficulty": "Intermediate",
                "code": (
                    ":root {\n"
                    "  --card-bg: rgba(17, 24, 39, 0.75);\n"
                    "  --card-border: rgba(99, 102, 241, 0.3);\n"
                    "  --accent-glow: rgba(99, 102, 241, 0.15);\n"
                    "}\n\n"
                    ".glass-card {\n"
                    "  position: relative;\n"
                    "  padding: 24px;\n"
                    "  border-radius: 16px;\n"
                    "  background: var(--card-bg);\n"
                    "  backdrop-filter: blur(16px);\n"
                    "  -webkit-backdrop-filter: blur(16px);\n"
                    "  border: 1px solid var(--card-border);\n"
                    "  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37),\n"
                    "              inset 0 1px 0 rgba(255, 255, 255, 0.1);\n"
                    "  transition: transform 0.25s ease, box-shadow 0.25s ease;\n"
                    "}\n\n"
                    ".glass-card:hover {\n"
                    "  transform: translateY(-4px);\n"
                    "  box-shadow: 0 12px 40px 0 var(--accent-glow),\n"
                    "              inset 0 1px 0 rgba(255, 255, 255, 0.2);\n"
                    "  border-color: #6366F1;\n"
                    "}\n"
                ),
                "explanation": "Creates a modern dark glass card with backdrop blur, subtle inner borders, and responsive elevation on hover.",
                "takeaway": "Combining backdrop-filter with subtle inset borders produces clean, state-of-the-art UI elements."
            }
        ],
        "sql": [
            {
                "title": "Aggregation with GROUP BY and HAVING",
                "difficulty": "Beginner / Core",
                "code": (
                    "-- Create table and seed data\n"
                    "CREATE TABLE employees (\n"
                    "    id INTEGER PRIMARY KEY,\n"
                    "    name TEXT,\n"
                    "    department TEXT,\n"
                    "    salary REAL\n"
                    ");\n\n"
                    "INSERT INTO employees VALUES\n"
                    "(1, 'Alice', 'Engineering', 95000),\n"
                    "(2, 'Bob', 'Engineering', 88000),\n"
                    "(3, 'Charlie', 'Design', 72000),\n"
                    "(4, 'Diana', 'Marketing', 68000),\n"
                    "(5, 'Evan', 'Engineering', 105000),\n"
                    "(6, 'Fiona', 'Marketing', 74000);\n\n"
                    "-- Analyze departments with average salary > 70000\n"
                    "SELECT department,\n"
                    "       COUNT(*) AS total_employees,\n"
                    "       ROUND(AVG(salary), 2) AS average_salary,\n"
                    "       MAX(salary) AS highest_salary\n"
                    "FROM employees\n"
                    "GROUP BY department\n"
                    "HAVING AVG(salary) > 70000\n"
                    "ORDER BY average_salary DESC;\n"
                ),
                "explanation": "Groups rows by department, applies aggregate functions (`COUNT`, `AVG`, `MAX`), and filters aggregated groups using `HAVING` rather than `WHERE`.",
                "takeaway": "Use WHERE to filter individual rows before grouping; use HAVING to filter aggregated groups after grouping."
            }
        ]
    }

# -------------------------------------------------------------
# Web Routes
# -------------------------------------------------------------
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response

@app.route("/")
@app.route("/index.html")
def index():
    root_index = os.path.join(BASE_DIR, "index.html")
    if os.path.isfile(root_index):
        return send_from_directory(BASE_DIR, "index.html")
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def api_status():
    """Returns local LM Studio connection status, loaded models, and active model."""
    status = fetch_lm_studio_models()
    active_model = None
    saved_model = get_saved_setting("active_model", LM_STUDIO_MODEL)
    if status["connected"] and status["models"]:
        active_model = saved_model if (saved_model and saved_model in status["models"]) else status["models"][0]

    return jsonify({
        "connected": status["connected"],
        "ok": status["connected"],
        "online": status["connected"],
        "status": "success" if status["connected"] else "error",
        "base_url": LM_STUDIO_BASE_URL,
        "models": status["models"],
        "model": active_model,
        "active_model": active_model,
        "error": status["error"],
        "offline_mode": True,
        "inference_engine": "LM Studio",
        "server": "LM Studio"
    })

@app.route("/api/set-model", methods=["POST"])
def api_set_model():
    """Switches the active model for EasyMind AI."""
    data = request.get_json(silent=True) or {}
    model_id = data.get("model", "").strip()
    if not model_id:
        return jsonify({"success": False, "error": "Model ID cannot be empty."}), 400
    
    set_saved_setting("active_model", model_id)
    return jsonify({"success": True, "active_model": model_id})

@app.route("/api/languages", methods=["GET"])
def api_languages():
    """Returns list of supported languages."""
    return jsonify({
        "languages": [
            {"id": k, "name": v["name"], "ext": v["ext"], "icon": v["icon"], "runner": v.get("runner", "")}
            for k, v in LANGUAGE_CONFIG.items()
        ]
    })

@app.route("/api/examples", methods=["GET"])
def api_examples():
    """Returns curated educational code examples for supported languages."""
    lang = request.args.get("language", "").lower()
    examples = get_curated_examples()
    if lang and lang in examples:
        return jsonify({"success": True, "language": lang, "examples": examples[lang]})
    return jsonify({"success": True, "languages": list(examples.keys()), "examples": examples})

@app.route("/api/run-code", methods=["POST"])
def api_run_code():
    """Safely executes code in isolated subprocess or engine."""
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    language = data.get("language", "python")
    stdin_data = data.get("stdin", "")
    res = execute_code_safely(code, language, stdin_data)
    return jsonify(res)

@app.route("/api/run-tests", methods=["POST"])
def api_run_tests():
    """Executes code against multiple test cases and compares actual vs expected outputs."""
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    language = data.get("language", "python")
    test_cases = data.get("test_cases", [])

    if not code or not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty."}), 400

    if not test_cases or not isinstance(test_cases, list):
        return jsonify({"success": False, "error": "Please provide a list of test cases."}), 400

    results = []
    passed_count = 0

    for idx, tc in enumerate(test_cases):
        inp = str(tc.get("input", ""))
        expected = str(tc.get("expected", "")).strip()

        exec_res = execute_code_safely(code, language, inp)
        actual = str(exec_res.get("output", "")).strip()
        err = exec_res.get("error", "")

        norm_actual = "\n".join(line.rstrip() for line in actual.splitlines())
        norm_expected = "\n".join(line.rstrip() for line in expected.splitlines())

        is_passed = (norm_actual == norm_expected) and exec_res.get("success", False)
        if is_passed:
            passed_count += 1

        results.append({
            "id": idx + 1,
            "input": inp,
            "expected": expected,
            "actual": actual if exec_res.get("success", False) else (err or "Runtime Error"),
            "passed": is_passed,
            "error": err,
            "time_ms": exec_res.get("execution_time_ms", 0)
        })

    return jsonify({
        "success": True,
        "results": results,
        "summary": {
            "total": len(test_cases),
            "passed": passed_count,
            "failed": len(test_cases) - passed_count
        }
    })

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Handles chat, code generation, debugging, explanation, and guidance requests."""
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    language = data.get("language", "any").lower()
    mode = data.get("mode", "chat").lower()
    session_id = data.get("session_id", "default_session").strip() or "default_session"
    history = data.get("history", [])

    if not user_message:
        return jsonify({"success": False, "error": "Message prompt cannot be empty."}), 400

    if language not in LANGUAGE_CONFIG:
        language = "any"

    # Verify LM Studio connection and model
    active_model, error_msg = get_active_model_id()
    if error_msg:
        return jsonify({
            "success": False,
            "error": error_msg,
            "connection_help": (
                "To fix this:\n"
                "1. Open LM Studio on your Windows PC.\n"
                "2. Go to the Developer / Local Server tab (<-> icon).\n"
                "3. Ensure a model is loaded in memory.\n"
                "4. Click 'Start Server' on port 1234 (http://localhost:1234).\n"
                "5. Click 'Retry Connection' in EasyMind AI."
            )
        }), 503

    # Build prompt messages
    system_prompt = build_system_prompt(language, mode)
    messages = [{"role": "system", "content": system_prompt}]

    # Append conversational history (up to last 6 messages)
    if isinstance(history, list):
        for msg in history[-6:]:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                role = "assistant" if msg["role"] == "assistant" else "user"
                content = str(msg.get("content", "")).strip()
                if content:
                    messages.append({"role": role, "content": content})

    # Append current user prompt
    messages.append({"role": "user", "content": user_message})

    # Prepare LM Studio payload
    payload = {
        "model": active_model,
        "messages": messages,
        "temperature": 0.3 if mode in ["generate", "debug", "doctor", "testcases"] else 0.7,
        "stream": False
    }

    headers = {"Content-Type": "application/json"}
    chat_url = f"{LM_STUDIO_BASE_URL}/chat/completions"

    try:
        response = requests.post(chat_url, headers=headers, json=payload, timeout=90)
        
        if response.status_code != 200:
            error_details = response.text
            try:
                err_json = response.json()
                if "error" in err_json:
                    error_details = err_json["error"].get("message", error_details)
            except Exception:
                pass
            return jsonify({
                "success": False,
                "error": f"LM Studio API returned error {response.status_code}: {error_details}"
            }), 502

        res_data = response.json()
        choices = res_data.get("choices", [])
        if not choices:
            return jsonify({
                "success": False,
                "error": "LM Studio returned an empty response. Ensure the loaded model is functional."
            }), 502

        choice_msg = choices[0].get("message", {})
        assistant_reply = choice_msg.get("content", "").strip()
        reasoning_reply = choice_msg.get("reasoning_content", "").strip()

        # Seamless reasoning model support (e.g. Qwen3-thinking, DeepSeek-R1)
        # If content is empty or model only produced reasoning, use reasoning as reply
        if not assistant_reply and reasoning_reply:
            assistant_reply = reasoning_reply

        if not assistant_reply:
            assistant_reply = "I analyzed your request, but the local model produced an empty response. Please try rephrasing or using a different prompt."

        # Extract code blocks
        code_blocks = extract_code_blocks(assistant_reply)

        # Store in SQLite database
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chat_history (session_id, role, content, language, mode, model_used)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (session_id, "user", user_message, language, mode, active_model))
                cursor.execute("""
                    INSERT INTO chat_history (session_id, role, content, language, mode, model_used)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (session_id, "assistant", assistant_reply, language, mode, active_model))
                conn.commit()
        except Exception as db_err:
            app.logger.warning(f"Database write error: {db_err}")

        return jsonify({
            "success": True,
            "response": assistant_reply,
            "reasoning": reasoning_reply if (reasoning_reply and reasoning_reply != assistant_reply) else None,
            "model_used": active_model,
            "language": language,
            "mode": mode,
            "code_blocks": code_blocks
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Lost connection to LM Studio while generating response. Please check if LM Studio crashed or ran out of memory."
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Request timed out waiting for LM Studio response. Local inference took longer than 90 seconds. Try a smaller prompt or a quantized/smaller model."
        }), 504
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Internal error during inference request: {str(e)}"
        }), 500

@app.route("/api/save-code", methods=["POST"])
def api_save_code():
    """Saves a code snippet both to SQLite and directly as a file in generated_code/."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip() or "Untitled_Snippet"
    language = data.get("language", "any").lower()
    code = data.get("code", "").strip()
    notes = data.get("notes", "").strip()

    if not code:
        return jsonify({"success": False, "error": "Code cannot be empty."}), 400

    lang_info = LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["any"])
    ext = lang_info["ext"]

    # Sanitize title for filename
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", title).strip("_") or "snippet"
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_base}_{timestamp_str}{ext}"
    file_path = os.path.join(GENERATED_CODE_DIR, filename)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        snippet_id = None
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO saved_snippets (title, language, code, notes, filename)
                VALUES (?, ?, ?, ?, ?)
            """, (title, language, code, notes, filename))
            snippet_id = cursor.lastrowid
            conn.commit()

        return jsonify({
            "success": True,
            "message": f"Successfully saved snippet as '{filename}'",
            "filename": filename,
            "id": snippet_id
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save code: {str(e)}"}), 500

@app.route("/api/saved-code", methods=["GET"])
def api_get_saved_code():
    """Lists all saved snippets from the database."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, language, code, notes, filename, timestamp
                FROM saved_snippets
                ORDER BY timestamp DESC
            """)
            rows = [dict(r) for r in cursor.fetchall()]
        return jsonify({"success": True, "snippets": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete-code/<int:snippet_id>", methods=["DELETE"])
def api_delete_code(snippet_id):
    """Deletes a saved snippet from SQLite and removes file if present."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename FROM saved_snippets WHERE id = ?", (snippet_id,))
            row = cursor.fetchone()
            if row and row["filename"]:
                fpath = os.path.join(GENERATED_CODE_DIR, row["filename"])
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
            cursor.execute("DELETE FROM saved_snippets WHERE id = ?", (snippet_id,))
            conn.commit()
        return jsonify({"success": True, "message": "Snippet deleted successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/download/<filename>", methods=["GET"])
def api_download_file(filename):
    """Safely serves saved code files for direct download."""
    safe_name = secure_filename(filename)
    if not safe_name:
        return "Invalid filename", 400
    file_path = os.path.join(GENERATED_CODE_DIR, safe_name)
    if not os.path.isfile(file_path):
        return "File not found", 404
    return send_from_directory(GENERATED_CODE_DIR, safe_name, as_attachment=True)

@app.route("/api/clear", methods=["POST"])
def api_clear_chat():
    """Clears conversation history for the current session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "default_session")
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
            conn.commit()
        return jsonify({"success": True, "message": "Chat history cleared successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/history", methods=["GET"])
def api_get_history():
    """Retrieves conversation history for current session."""
    session_id = request.args.get("session_id", "default_session")
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, language, mode, model_used, timestamp
                FROM chat_history
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """, (session_id,))
            rows = [dict(r) for r in cursor.fetchall()]
        return jsonify({"success": True, "history": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------------------------------------
# Main Application Launcher
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")
    debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

    print("=" * 60)
    print("  EasyMind AI - Local Programming Learning Assistant")
    print(f"  Inference Engine: LM Studio ({LM_STUDIO_BASE_URL})")
    print(f"  Web Dashboard:   http://{host}:{port}")
    print("  Database:        SQLite (database/easymind.db)")
    print("  Status:          100% Offline Capable & Private")
    print("=" * 60)

    app.run(host=host, port=port, debug=debug)
