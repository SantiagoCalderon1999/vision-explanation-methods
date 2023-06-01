# Copyright (c) Microsoft Corporation
# Licensed under the MIT License.

"""Defines the Error Labeling Manager class."""

from enum import Enum

import numpy as np
import torchvision
from torch import Tensor

LABELS = 'labels'


class ErrorLabelType(Enum):
    """
    Enum providing types of error labels.

    If none, then the detection is not an error. It is a
    correct prediction.
    """

    # the gt doesn't have a corresponding detection
    MISSING = "missing"

    # the model predicted detections, but there was nothing there
    # this prediction must have a 0 iou score with all gt detections
    BACKGROUND = "background"

    # the predicted class is correct, bounding box is not
    LOCALIZATION = "localization"

    # the predicted class is incorrect, the bounding box is correct
    CLASS_NAME = "class_name"

    # both the predicted class and bounding box are incorrect
    CLASS_LOCALIZATION = "class_localization"

    # the predicted class is correct, the bounding box is correct, but
    # the iou score is lower than another detection
    DUPLICATE_DETECTION = "duplicate_detection"

    MATCH = "match"


class ErrorLabeling():
    """Defines a wrapper class of Error Labeling for vision scenario.

    Only supported for object detection at this point.
    """

    def __init__(self,
                 pred_y: str,
                 true_y: str,
                 iou_threshold: float = 0.5):
        """Create an ErrorLabeling object.

        :param model: The model to explain.
            A model that implements sklearn.predict or sklearn.predict_proba
            or function that accepts a 2d ndarray.
        :type model: object
        :param evaluation_examples: A matrix of feature vector
            examples (# examples x # features) on which to explain the
            model's output, with an additional label column.
        :type evaluation_examples: pandas.DataFrame
        :param target_column: The name of the label column.
        :type target_column: str
        """
        self._is_run = False
        self._is_added = False
        self._pred_y = pred_y
        self._true_y = true_y
        self._iou_threshold = iou_threshold
        self._match_matrix = np.full((len(self._true_y), len(self._pred_y)),
                                     None)

    def compute(self, **kwargs):
        """Compute the error analysis data.

        Note: if a row does not have a match, that means that there is a
        missing gt detection

        :param kwargs: The keyword arguments to pass to the compute method.
            Note that this method does not take any arguments currently.
        :type kwargs: dict
        """
        # save original ordering of predictions
        original_indices = [i for i, _ in sorted(enumerate(self._pred_y),
                                                 key=lambda x: x[1][-1],
                                                 reverse=True)]

        # sort predictions by decreasing conf score
        # this is to stay consistent with NMS and MAP algorithms
        sorted_list = sorted(self._pred_y, key=lambda x: x[-1], reverse=True)

        for gt_index, gt in enumerate(self._true_y):
            for detect_index, detect in enumerate(sorted_list):
                iou_score = torchvision.ops.box_iou(
                    Tensor(detect[1:5]).unsqueeze(0).view(-1, 4),
                    Tensor(gt[1:5]).unsqueeze(0).view(-1, 4))

                if iou_score.item() == 0.0:
                    # if iou is 0, then prediction is detecting the background
                    self._match_matrix[gt_index][detect_index] = (
                        ErrorLabelType.BACKGROUND)
                    continue
                if (self._iou_threshold <= iou_score):
                    # the detection and ground truth bb's are overlapping
                    if detect[0] != gt[0]:
                        # the bb's line up, but labels do not
                        self._match_matrix[gt_index][detect_index] = (
                            ErrorLabelType.CLASS_NAME)
                        continue
                    elif (ErrorLabelType.MATCH in
                          self._match_matrix[gt_index]):
                        # class name and bb correct, but there is already a
                        # match with a higher confidence score (this is why
                        # it was imporant to sort by descending confidence
                        # scores as the first step)
                        self._match_matrix[gt_index][detect_index] = (
                            ErrorLabelType.DUPLICATE_DETECTION)
                        continue
                    else:
                        # this means bbs overlap, class names = (1st time)
                        self._match_matrix[gt_index][detect_index] = (
                            ErrorLabelType.MATCH)
                        continue
                else:
                    if detect[0] != gt[0]:
                        # the bb's don't line up, and labels do not
                        self._match_matrix[gt_index][detect_index] = (
                            ErrorLabelType.CLASS_LOCALIZATION)
                        continue
                    else:
                        # the bb's don't line up, but the labels are correct
                        self._match_matrix[gt_index][detect_index] = (
                            ErrorLabelType.LOCALIZATION)
                        continue

            # resort the columns (so no longer ordered by descending conf
            # scores)
            self._match_matrix[gt_index] = [self._match_matrix[gt_index][i]
                                            for i in original_indices]