"""
Evaluation Utilities for NTL Detection.

Provides a single convenience function that computes the full set of
binary-classification metrics used in the NTL detection literature:

    Accuracy, Precision, Recall (TPR), Specificity (TNR),
    F1-Score, Matthews Correlation Coefficient (MCC),
    AUC-ROC, AUC-PR (Average Precision).

Reference metrics align with those reported in:
    Nizar et al. (2006), Glauner et al. (2016),
    Jokar et al. (2016), Pereira et al. (2020).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
    precision_recall_curve,
)
from typing import Optional


def evaluate_detection(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    y_proba: Optional[np.ndarray | pd.Series] = None,
    threshold: float = 0.5,
) -> dict:
    """
    Compute a comprehensive set of NTL detection metrics.

    Parameters
    ----------
    y_true : array-like of {0, 1} or {False, True}
        Ground-truth labels.
    y_pred : array-like of {0, 1}
        Binary predictions from the detector.
    y_proba : array-like of float in [0, 1], optional
        Estimated probability of the positive (NTL) class.  When
        provided, AUC-ROC, AUC-PR and the optimal threshold are also
        computed.
    threshold : float
        Decision threshold used to produce *y_pred* from *y_proba*.
        Only used for reporting purposes.

    Returns
    -------
    dict
        Keys: accuracy, precision, recall, specificity, f1, mcc,
              false_positive_rate, false_negative_rate,
              tp, fp, tn, fn,
              auc_roc (if y_proba provided),
              auc_pr  (if y_proba provided),
              optimal_threshold (if y_proba provided),
              roc_curve (if y_proba provided) – dict with fpr/tpr/thresholds,
              pr_curve  (if y_proba provided) – dict with precision/recall/thresholds.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    mcc = matthews_corrcoef(y_true, y_pred)
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    fpr_val = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr_val = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    results: dict = {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "specificity": float(specificity),
        "f1": float(f1),
        "mcc": float(mcc),
        "false_positive_rate": float(fpr_val),
        "false_negative_rate": float(fnr_val),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }

    if y_proba is not None:
        y_proba = np.asarray(y_proba, dtype=float)
        auc_roc = roc_auc_score(y_true, y_proba)
        auc_pr = average_precision_score(y_true, y_proba)

        fpr_arr, tpr_arr, roc_thresholds = roc_curve(y_true, y_proba)
        prec_arr, rec_arr, pr_thresholds = precision_recall_curve(y_true, y_proba)

        # Youden's J statistic to find optimal threshold
        j_scores = tpr_arr - fpr_arr
        optimal_idx = int(np.argmax(j_scores))
        optimal_threshold = float(roc_thresholds[optimal_idx])

        results.update(
            {
                "auc_roc": float(auc_roc),
                "auc_pr": float(auc_pr),
                "optimal_threshold": optimal_threshold,
                "roc_curve": {
                    "fpr": fpr_arr.tolist(),
                    "tpr": tpr_arr.tolist(),
                    "thresholds": roc_thresholds.tolist(),
                },
                "pr_curve": {
                    "precision": prec_arr.tolist(),
                    "recall": rec_arr.tolist(),
                    "thresholds": pr_thresholds.tolist(),
                },
            }
        )

    return results


def print_evaluation_report(metrics: dict, model_name: str = "NTL Detector") -> None:
    """Pretty-print an evaluation metrics dictionary."""
    print(f"\n{'='*55}")
    print(f"  Evaluation Report: {model_name}")
    print(f"{'='*55}")
    print(f"  Accuracy   : {metrics['accuracy']:.4f}")
    print(f"  Precision  : {metrics['precision']:.4f}")
    print(f"  Recall     : {metrics['recall']:.4f}")
    print(f"  Specificity: {metrics['specificity']:.4f}")
    print(f"  F1-Score   : {metrics['f1']:.4f}")
    print(f"  MCC        : {metrics['mcc']:.4f}")
    print(f"  FPR        : {metrics['false_positive_rate']:.4f}")
    print(f"  FNR        : {metrics['false_negative_rate']:.4f}")
    if "auc_roc" in metrics:
        print(f"  AUC-ROC    : {metrics['auc_roc']:.4f}")
        print(f"  AUC-PR     : {metrics['auc_pr']:.4f}")
        print(f"  Opt. Thresh: {metrics['optimal_threshold']:.4f}")
    print(f"{'─'*55}")
    print(f"  Confusion Matrix:")
    print(f"    TP={metrics['tp']:>5d}  FP={metrics['fp']:>5d}")
    print(f"    FN={metrics['fn']:>5d}  TN={metrics['tn']:>5d}")
    print(f"{'='*55}\n")
