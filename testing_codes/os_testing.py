import os 
from pathlib import Path
print(os.path.dirname(os.path.abspath(__file__)))  # Output: /home/runner/work/LLM_Interactor/LLM_Interactor/testing_codes/os_testing.py
print(Path(__file__).parent.parent / "logs")
