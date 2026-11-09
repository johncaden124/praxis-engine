"""Challenge 4 — NumPy From Scratch: Yield Regression (Stage 2) → benchmark s2_numpy

Each tile in the 5x5 field has soil quality and rainfall, and a crop yield.
Fit yield ≈ w1*soil + w2*rain + b with *gradient descent written by hand in
NumPy* (no sklearn, no np.linalg.lstsq), then predict yields for test_inputs().
Pass: your test MSE is within 25% of the best possible linear fit.

Useful API: training_data(), test_inputs(), submit_result(...), log(...).
"""
import numpy as np

from station_api import log, submit_result, test_inputs, training_data

X, y = training_data()
X, y = np.array(X), np.array(y)


def predict(X, w, b):
    return X @ w + b


def gd_step(X, y, w, b, lr):
    """Your turn: one step of gradient descent on mean squared error.

    loss = mean((X @ w + b - y) ** 2)
    Return the updated (w, b).
    """
    return w, b


w, b = np.zeros(X.shape[1]), 0.0
for epoch in range(2000):
    w, b = gd_step(X, y, w, b, lr=0.01)
    if epoch % 500 == 0:
        log(f"epoch {epoch}: mse={np.mean((predict(X, w, b) - y) ** 2):.3f}")

preds = predict(np.array(test_inputs()), w, b)
submit_result(weights=w.tolist(), bias=float(b), predictions=preds.tolist())
