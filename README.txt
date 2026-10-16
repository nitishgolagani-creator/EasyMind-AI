EASYMIND AI — OFFLINE STARTER
=============================

This starter is a local website connected to LM Studio. It does not require Flask or any Python packages.

WHAT YOU NEED
1. LM Studio installed.
2. At least one local chat model downloaded and loaded in LM Studio.
3. Python installed. Since `py --version` worked on your laptop, use `py app.py` to start the app.
4. For running C/C++: install a C/C++ compiler and make sure `gcc` or `g++` is available in Command Prompt.
5. For running Java: install a JDK and make sure `java` and `javac` are available in Command Prompt.

START THE APP
1. Extract this ZIP to a folder such as Desktop\EasyMind_AI_Offline.
2. Open LM Studio and load your downloaded model.
3. Open the Developer tab in LM Studio and start the local server. Use port 1234.
4. Open the extracted folder in File Explorer.
5. Click the folder address bar, type `cmd`, and press Enter.
6. In Command Prompt, type:
       py app.py
7. Keep that Command Prompt window open.
8. Open a browser and go to:
       http://127.0.0.1:8000

OFFLINE USE
After downloading LM Studio, the model, Python, and any required compilers, the app communicates with LM Studio through your own computer at 127.0.0.1. It does not call a cloud AI service. You can disconnect from the internet to test this.

HOW TO TEST
1. Select Python.
2. Enter: Write a program to add two numbers, 5 and 7.
3. Click Generate code.
4. Click Put answer into editor.
5. Click Run code. If the program asks for input, enter it in the Program input box first.
6. Select HTML and paste HTML, then click Preview HTML/CSS/JS.

IMPORTANT LIMITATIONS
- LM Studio produces AI responses; the local runner produces actual execution results. These are separate.
- HTML/CSS/JavaScript run in the browser preview.
- Python/C/C++/Java/SQL are run locally by this app when their requirements are present.
- SQL uses a temporary in-memory SQLite database. Add CREATE TABLE/INSERT statements before SELECT.
- This is a learning prototype, not a secure production sandbox. Only run code you trust. Running arbitrary programs on your own computer can be dangerous.
- This starter's code runner is intentionally basic; it does not implement advanced file projects, package installation, or multi-file builds.
- The server is bound to 127.0.0.1, so it is intended for this computer only.
- The site is not a single executable. Keep app.py and the static folder together.

TROUBLESHOOTING
- “LM Studio not connected”: load a model and start the local server. Test http://127.0.0.1:1234/v1/models in the browser.
- “Python not found”: open Command Prompt and run `py --version`; start the app using `py app.py`.
- Port 8000 already in use: close another EasyMind instance, then try again.
- Model is slow: use a smaller quantized model that fits your computer's RAM/VRAM.
