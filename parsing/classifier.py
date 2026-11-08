"""Station 2: raw text -> ReportType.

Input : the raw OCR string from station 1.
Output: ReportType.TYPE_A or ReportType.TYPE_B.

How it decides: every report type has a list of weighted keywords. The classifier adds
up the weight of the keywords it finds, and the type with the highest score wins.
It does not read lines or rows.

Why not rely on one word: OCR can damage any single word. With many keywords, a
damaged word costs a few points, but the winner usually stays the same.
Why it can refuse: if the evidence is weak or the two scores are too close, guessing
would silently produce a wrong report. So it raises ClassificationError instead.
"""
from collections.abc import Mapping

from config.report_keywords import REPORT_KEYWORDS
from config.rules import CLASSIFIER_MIN_MARGIN, CLASSIFIER_MIN_WINNING_SCORE
from domain.exceptions import ClassificationError
from domain.models import ReportType
from parsing.text_tools import flatten_text

Scores = dict[ReportType, int]


class ReportClassifier:
    def __init__(
        self,
        keywords: Mapping[ReportType, Mapping[str, int]] = REPORT_KEYWORDS,
        min_winning_score: int = CLASSIFIER_MIN_WINNING_SCORE,
        min_margin: int = CLASSIFIER_MIN_MARGIN,
    ) -> None:
        # Keywords go through the same cleaning as the text, so they always match.
        self._keywords = {
            report_type: {flatten_text(word): weight for word, weight in words.items()}
            for report_type, words in keywords.items()
        }
        self._min_winning_score = min_winning_score
        self._min_margin = min_margin

    def score(self, raw_text: str) -> Scores:
        """The total weight of the keywords found, for every report type.

        A keyword counts once, however many times it appears. Otherwise a long report
        with many rows would drown out the evidence.
        """
        text = flatten_text(raw_text)
        return {
            report_type: sum(weight for word, weight in words.items() if word in text)
            for report_type, words in self._keywords.items()
        }

    def classify(self, raw_text: str) -> ReportType:
        scores = self.score(raw_text)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_type, best_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0

        if best_score < self._min_winning_score:
            raise ClassificationError(
                f"Not enough evidence to choose a report type (scores: {self._describe(scores)})"
            )
        if best_score - runner_up_score < self._min_margin:
            raise ClassificationError(
                f"The scores are too close to choose a report type (scores: {self._describe(scores)})"
            )
        return best_type

    @staticmethod
    def _describe(scores: Scores) -> str:
        return ", ".join(f"{report_type.name}={score}" for report_type, score in scores.items())
