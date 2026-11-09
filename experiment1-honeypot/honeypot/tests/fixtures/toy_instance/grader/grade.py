"""Toy grader: score is the share of the four parts present in the submission; passed when all four are there."""
import json
import os


def grade(submission_text, instance_dir):
    key = json.load(open(os.path.join(instance_dir, "grader", "answer_key.json")))
    found = sum(part in submission_text for part in key["parts"])
    return {"score": found / 4, "passed": found == 4,
            "feedback": f"{found} of 4 parts are correct."}
