import os
import sys


def resolve_base_dir():
    env_var = os.environ.get("QUEST_PCM_ROOT")
    if env_var and os.path.isdir(env_var):
        print("ENV: QUEST_PCM_ROOT")
        return env_var

    venv_root = os.path.dirname(os.path.dirname(sys.executable))
    candidate = os.path.join(venv_root, "snl_quest_pcm")
    if os.path.isdir(candidate):
        print("CANDIDATE DETECTED")
        return candidate

    print("NO ENV DETECTED")
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
