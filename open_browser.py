import webbrowser
import time
import sys

URL = "http://127.0.0.1:5000"

def main():
    print(f"Opening EasyMind AI at {URL} in your default browser...")
    webbrowser.open(URL)
    print("Done! If your browser did not open automatically, navigate to http://127.0.0.1:5000")

if __name__ == "__main__":
    main()
