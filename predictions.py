"""Whimsical predictions."""
import random
import re
from typing import List, Dict, Set

class Predictions:
    """Toy class for making randomly-selected predictions."""
    def __init__(self, predictions_file_path: str):
        self.predictions_by_tag: Dict[str, List[str]] = {} # Predictions with tags
        self.generic_predictions: List[str] = [] # Predictions without tags
        self.predictions_file_path: str = predictions_file_path

    def refreshPredictions(self):
        """Refresh predictions from the predictions file, immediately."""
        with open(self.predictions_file_path) as input_file:
            self.setPredictions(input_file.readlines())

    def setPredictions(self, lines: List[str]):
        """Set the predictions immediately, as if the specified lines were from the predictions file."""
        self.generic_predictions.clear()
        self.predictions_by_tag.clear()
        prediction_with_tags_pattern: re.Pattern = re.compile(r'^(?P<prediction_text>[^#]+)(?P<prediction_tags_text>#.*)$')
        lines: List[str] = (line.strip() for line in lines)
        lines: List[str] = filter(lambda line : line and not line.startswith('#'), lines)
        for line in lines:
            match = prediction_with_tags_pattern.match(line)
            if not match:
                # Generic prediction.
                self.generic_predictions.append(line.strip())
            else:
                prediction_text = match.group('prediction_text').strip()
                # Now extract and process the tags.
                raw_tags: List[str] = list(raw.strip() for raw in match.group('prediction_tags_text').lower().split('#')) # Extra tags
                raw_tags = filter(lambda line: line, raw_tags) # Remove blank lines
                normalized_tags: List[str] = list(raw.replace('_', ' ') for raw in raw_tags)
                for tag in normalized_tags:
                    if not tag in self.predictions_by_tag:
                        self.predictions_by_tag[tag]: List[str] = [prediction_text]
                    else:
                        self.predictions_by_tag[tag].append(prediction_text)

    def predict(self, input_text: str=None) -> str:
        """Make a prediction about the specified question/statement.

        The string argument is completely optional. If present, predictions may latch onto words or phrases
        within it to make funnier and/or more ludicrous predictions."""
        if not input_text:
            # Any old prediction will do.
            return self.generic_predictions[random.randint(0, len(self.generic_predictions) - 1)]
        else:
            # Select all the matching tags.
            normalized_text = input_text.lower()
            matching_predictions: Set[str] = set()
            for (tag, prediction_list) in self.predictions_by_tag.items():
                if normalized_text.find(tag) != -1:
                    for prediction in prediction_list:
                        matching_predictions.add(prediction)
            if not matching_predictions:
                # Nothing matched. Fall back to any prediction.
                return self.generic_predictions[random.randint(0, len(self.generic_predictions) - 1)]
            # Else, use one of the matching predictions.
            as_list = list(matching_predictions)
            return as_list[random.randint(0, len(as_list) - 1)]
