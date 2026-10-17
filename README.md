# EasyMind AI 🧠⚡
> **AI-Powered Local Programming Learning Assistant for Windows 11**  
> *100% Private • Offline Capable • Exclusively Powered by LM Studio*

EasyMind AI is an interactive programming tutor designed to run completely offline on Windows 11. It provides intelligent code generation, plain English code explanations, debugging assistance, and step-by-step programming guidance across 8+ major languages without relying on cloud APIs, internet connectivity, or Ollama.

---

## 1. Features

- **Local AI Inference Engine**: Uses **LM Studio** exclusively (`http://localhost:1234/v1`).
- **Comprehensive Language Support**:
  - Python (`.py`)
  - C (`.c`)
  - C++ (`.cpp`)
  - Java (`.java`)
  - JavaScript (`.js`)
  - HTML (`.html`)
  - CSS (`.css`)
  - SQL (`.sql`)
  - General / Any language
- **Four Specialized Learning Modes**:
  1. ⚡ **Generate Code**: Clean, robust, production-ready code with inline comments.
  2. 📖 **Explain in Plain English**: Breakdowns of complex syntax, algorithms, and logic for beginners.
  3. 🐛 **Debug & Fix**: Root-cause analysis, bug detection, and corrected code snippets.
  4. 🪜 **Step-by-Step Guidance**: Pedagogical, numbered roadmaps from design to implementation.
- **Developer Experience**:
  - One-click **Copy Code** button on every generated code block.
  - One-click **Save to File** button saving code both to SQLite and local files in `generated_code/`.
  - Direct file download for saved code files.
  - Live **LM Studio Connection Status** pill with auto-detection of loaded models.
  - Interactive starter cards on the welcome dashboard.
  - Persistent chat history and saved snippets powered by local **SQLite**.
- **100% Offline Integrity**:
  - Zero external CDN dependencies (no unpkg, no cdnjs, no Google Fonts).
  - All styling, SVGs, and fonts are self-contained locally.
  - Strictly no cloud API keys or internet tracking.

---

## 2. Project Structure

```
EasyMindAI/
├── index.html              # Standalone & root dashboard UI (Explorer visible)
├── app.py                  # Flask backend service & LM Studio orchestration
├── Launch_EasyMind_AI.bat  # 1-Click launcher: starts backend & opens browser
├── Launch_EasyMind_AI.url  # Windows Internet Shortcut to http://127.0.0.1:5000
├── open_browser.py         # Python browser launcher script
├── requirements.txt        # Local Python package dependencies
├── .env.example            # Template for environment configuration
├── .env                    # Active local environment settings
├── .gitignore              # Git ignore rules for virtualenvs, caches & SQLite
├── README.md               # Complete setup, offline guide, and documentation
├── templates/
│   └── index.html          # Flask template dashboard UI
├── static/
│   ├── style.css           # Premium dark-mode styling with glassmorphism
│   └── script.js           # Client-side state, API calls & markdown parser
├── database/
│   └── easymind.db         # Persistent SQLite database (auto-created)
└── generated_code/         # Auto-saved user code files (.py, .cpp, .java, etc.)
```

---

## 3. Prerequisites & Installation

### A. Python Environment
Python 3.10+ on Windows 11. On Windows, Python is accessed through the **`py`** launcher:

```powershell
# Verify Python and pip via the 'py' launcher
py --version
py -m pip --version
```

### B. Install Python Dependencies
Run the following command while connected to the internet before going offline:

```powershell
py -m pip install -r requirements.txt
```

*Installed dependencies:*
- `Flask>=3.0.0`: Lightweight, dependable local web framework.
- `requests>=2.31.0`: Synchronous HTTP client to query LM Studio's local OpenAI-compatible endpoint.
- `python-dotenv>=1.0.0`: Reads local `.env` configuration.

---

## 4. Setting Up LM Studio (The Only AI Engine)

> **Important**: EasyMind AI uses LM Studio exclusively. No cloud APIs, and no Ollama.

### Step 1: Download a Compatible Model (While Online)
1. Open **LM Studio** on Windows 11.
2. In the Search tab (magnifying glass icon), search for and download any capable coding or instruction model, for example:
   - `Qwen/Qwen2.5-Coder-7B-Instruct-GGUF` (Recommended for coding)
   - `qwen/qwen3-4b-thinking`
   - `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`
   - `meta-llama/Llama-3.2-3B-Instruct`
3. Wait for the `.gguf` weights to finish downloading.

### Step 2: Start the LM Studio Local Server
1. Click the **Developer / Local Server** tab in LM Studio's left navigation (represented by `<->`).
2. At the top of the window, select your downloaded model from the dropdown to load it into memory / GPU RAM.
3. Verify the **Port** is set to `1234` (Base URL: `http://localhost:1234/v1`).
4. Click the green **"Start Server"** button.
5. You should see `Status: ON` and logs confirming `Local server listening on port 1234`.

---

## 5. Starting EasyMind AI & Opening the Website in Browser

> **Note on Opening in Browser vs. Editor**: In Antigravity IDE, clicking `index.html` opens the file in code view (text editor). To view the actual interactive website interface in a browser, use any of the methods below:

### Method 1: Double-Click `Launch_EasyMind_AI.bat` (Recommended)
Double-click `Launch_EasyMind_AI.bat` in Windows File Explorer:
- Automatically starts the Python backend on port 5000 in the background.
- Opens `http://127.0.0.1:5000` directly in your default web browser (Edge, Chrome, or Firefox).

### Method 2: Double-Click `Launch_EasyMind_AI.url`
If the Python backend is already running:
- Double-click `Launch_EasyMind_AI.url` in Windows File Explorer.
- Windows will immediately launch your default web browser directly to the EasyMind AI web app.

### Method 3: PowerShell / Terminal Command
Run this command in PowerShell to launch your default browser:
```powershell
Start-Process "http://127.0.0.1:5000"
```
Or with Python:
```powershell
py open_browser.py
```

### Method 4: Manual Browser Navigation
1. Start the server: `py app.py`
2. Open any web browser and go to:
   ```
   http://127.0.0.1:5000
   ```
3. You will see the complete dark-themed EasyMind AI assistant interface with all 8 tools and live LM Studio integration.

---

## 6. How to Test Without Wi-Fi (Hackathon Offline Demonstration)

1. Turn off your Wi-Fi or disconnect Ethernet on your Windows 11 computer.
2. Ensure LM Studio server is running on `http://localhost:1234` with your model loaded.
3. Open `http://127.0.0.1:5000`.
4. Verify the status pill in the top navigation displays:  
   `🟢 Online: <your-model-name>`
5. Test Code Generation:
   - Select **Python** and **Generate Code**.
   - Click the starter card: *"Sort & deduplicate list of dictionaries"*.
   - Watch EasyMind AI generate working code locally.
   - Click **Copy Code** or **Save to File** to verify code extraction.
6. Test Code Explanation:
   - Switch mode to **Explain in Plain English**.
   - Select **C++** and ask: *"How do pointers work in simple terms?"*
   - Verify the line-by-line explanation.
7. Test Debugging:
   - Switch mode to **Debug & Fix**.
   - Select **Java** and paste a snippet throwing `NullPointerException`.
   - Verify EasyMind AI diagnoses the bug and gives the corrected code.
8. Inspect `generated_code/` folder:
   - Confirm that saved snippets are stored locally on disk.
9. Inspect `database/easymind.db`:
   - Confirm that chat history and snippets are saved to local SQLite.

---

## 7. Security & Privacy Guarantees

- **No Arbitrary Code Execution**: Generated code is displayed safely with syntax formatting and never executed automatically without explicit user review.
- **Local Isolation**: All requests are routed directly to `127.0.0.1:1234` (LM Studio) and `127.0.0.1:5000` (Flask). No data packets leave the machine.
- **Safe File Writing**: Code saving uses strict filename sanitization and safe directory bounding.
